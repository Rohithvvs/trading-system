"""Alembic environment.

Uses a *synchronous* SQLAlchemy engine for online migrations. Async/asyncpg is
intentionally avoided here: Neon/PgBouncer poolers frequently raise
InvalidCachedStatementError after DDL on alembic_version, which breaks
`alembic current` / `upgrade` even when statement_cache_size=0 is set via
SQLAlchemy's async dialect. Sync psycopg2 is the stable path for migration
commands while the app continues to use asyncpg at runtime.
"""

from __future__ import annotations

from logging.config import fileConfig
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import engine_from_config, pool

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
from app.models import analysis  # noqa: F401
from app.models import paper_trading  # noqa: F401
from app.models import stock  # noqa: F401
from app.models import fyers_token  # noqa: F401
from app.models import workstation  # noqa: F401
from app.models import market_data  # noqa: F401
from app.models import system_log  # noqa: F401
from app.models import infrastructure  # noqa: F401
from app.models import research  # noqa: F401
from app.models import auth  # noqa: F401  # users / sessions / audit_logs
from app.models import feature_permission  # noqa: F401  # Sprint 3 feature_permissions


def _sync_database_url(raw_database_url: str) -> str:
    """Convert app DATABASE_URL to a sync SQLAlchemy URL for Alembic.

    - postgresql+asyncpg → postgresql+psycopg2 (or plain postgresql)
    - strip channel_binding (not accepted by psycopg2)
    - preserve sslmode for Neon
    """
    parsed = urlsplit(raw_database_url)
    scheme = parsed.scheme

    if scheme == "sqlite" or scheme.startswith("sqlite+"):
        # Offline/local sqlite — keep as-is (sync)
        return raw_database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)

    if scheme in {"postgresql+asyncpg", "postgres", "postgresql"}:
        scheme = "postgresql+psycopg2"
    elif scheme == "postgresql+psycopg2":
        pass
    # else leave custom schemes alone

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    filtered: list[tuple[str, str]] = []
    for key, value in query_pairs:
        if key == "channel_binding":
            continue
        filtered.append((key, value))

    return urlunsplit(
        (
            scheme,
            parsed.netloc,
            parsed.path,
            urlencode(filtered, doseq=True),
            parsed.fragment,
        )
    )


database_url = _sync_database_url(settings.database_url)
# configparser interpolates '%' — escape for set_main_option
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a sync engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
