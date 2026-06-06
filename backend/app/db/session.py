from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event, text
import asyncio

from ..config import settings
from .base import Base


connect_args = {}
pool_kwargs = {"pool_pre_ping": True}

database_url = settings.database_url

# Handle Render PostgreSQL sslmode=require for asyncpg
if "sslmode=require" in database_url:
    database_url = database_url.replace("?sslmode=require", "")
    database_url = database_url.replace("&sslmode=require", "")
    connect_args["ssl"] = True

# Increase connection timeout to 120s to allow Render free tier Postgres to wake up
if database_url.startswith("postgresql"):
    connect_args["command_timeout"] = 120

# Connection Pooling Limits for Postgres
pool_kwargs["pool_size"] = 20
pool_kwargs["max_overflow"] = 10

print(f"Database SSL Enabled: {connect_args.get('ssl', False)}")
print("Database Driver: asyncpg")

engine = create_async_engine(
    database_url,
    connect_args=connect_args,
    **pool_kwargs
)

@event.listens_for(engine.sync_engine, "connect")
def set_postgres_timeouts(dbapi_connection, connection_record):
    if engine.name != "postgresql":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("SET statement_timeout = '30s'")
    cursor.execute("SET lock_timeout = '5s'")
    cursor.execute("SET idle_in_transaction_session_timeout = '30s'")
    cursor.close()

AsyncSessionLocal = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=AsyncSession)

main_event_loop = None

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    db = AsyncSessionLocal()
    try:
        yield db
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()

sync_database_url = database_url.replace(
    "postgresql+asyncpg",
    "postgresql"
)
sync_connect_args = connect_args.copy()
sync_connect_args.pop("command_timeout", None)
sync_pool_kwargs = pool_kwargs.copy()
sync_pool_kwargs["pool_size"] = 80
sync_pool_kwargs["max_overflow"] = 20
sync_engine = create_engine(sync_database_url, connect_args=sync_connect_args, **sync_pool_kwargs)

@event.listens_for(sync_engine, "connect")
def set_postgres_timeouts_sync(dbapi_connection, connection_record):
    if sync_engine.name != "postgresql":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("SET statement_timeout = '30s'")
    cursor.execute("SET lock_timeout = '5s'")
    cursor.execute("SET idle_in_transaction_session_timeout = '30s'")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine, expire_on_commit=False)

def get_sync_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

async def init_db() -> None:
    # Deprecated: Database initialization is now strictly managed by Alembic.
    # The application will fail-fast on startup if migrations are not up-to-date.
    pass

def check_alembic_head() -> None:
    pass
