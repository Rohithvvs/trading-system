import asyncio
from logging.config import fileConfig
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import os
import sys

# Add the backend directory to sys.path so 'app' can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import Base
from app.config import settings

# Import models to ensure they are registered with Base.metadata
from app.models import analysis
from app.models import paper_trading
from app.models import stock
from app.models import fyers_token
from app.models import workstation
from app.models import market_data
from app.models import system_log
from app.models import infrastructure
from app.models import research
from app.models import auth  # users / sessions / audit_logs
from app.models import feature_permission  # Sprint 3 feature_permissions

def _prepare_asyncpg_url(raw_database_url: str) -> tuple[str, dict[str, object]]:
    """Normalize DB URL for async engines (mirrors app.db.session helper).

    SQLite sync URLs must become sqlite+aiosqlite for create_async_engine /
    async_engine_from_config, otherwise SQLAlchemy raises:
    "The asyncio extension requires an async driver... pysqlite is not async".
    """
    parsed = urlsplit(raw_database_url)
    if parsed.scheme == "sqlite":
        return raw_database_url.replace("sqlite://", "sqlite+aiosqlite://", 1), {}
    if parsed.scheme != "postgresql+asyncpg":
        return raw_database_url, {}

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_pairs: list[tuple[str, str]] = []
    sslmode: str | None = None

    for key, value in query_pairs:
        if key == "sslmode":
            sslmode = value.lower()
            continue
        if key == "channel_binding":
            continue
        filtered_pairs.append((key, value))

    connect_args: dict[str, object] = {}
    if sslmode and sslmode != "disable":
        connect_args["ssl"] = True

    database_url = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(filtered_pairs, doseq=True),
            parsed.fragment,
        )
    )
    return database_url, connect_args


database_url, connect_args = _prepare_asyncpg_url(settings.database_url)
config.set_main_option("sqlalchemy.url", database_url)
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
