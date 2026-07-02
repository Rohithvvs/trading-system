from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event, text
import asyncio
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..config import settings
from .base import Base


connect_args = {}
pool_kwargs = {"pool_pre_ping": True}

def _prepare_asyncpg_url(raw_database_url: str) -> tuple[str, dict[str, object]]:
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

    async_connect_args: dict[str, object] = {}
    if sslmode and sslmode != "disable":
        async_connect_args["ssl"] = True

    async_database_url = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(filtered_pairs, doseq=True),
            parsed.fragment,
        )
    )
    return async_database_url, async_connect_args


database_url, ssl_connect_args = _prepare_asyncpg_url(settings.database_url)
connect_args.update(ssl_connect_args)

# Increase connection timeout to 120s to allow Render free tier Postgres to wake up
if database_url.startswith("postgresql"):
    connect_args["command_timeout"] = 120

# Connection Pooling Limits for Postgres
pool_kwargs["pool_size"] = 20
pool_kwargs["max_overflow"] = 10

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

# ---------------------------------------------------------------------------
# DB POOL FORENSICS — passive observers, no business logic changes
# ---------------------------------------------------------------------------
import logging as _db_logging
_db_forensics_logger = _db_logging.getLogger("app.db_forensics")

@event.listens_for(engine.sync_engine, "checkout")
def _log_pool_checkout(dbapi_connection, connection_record, connection_proxy):
    """Log DB_POOL_STATUS on every connection checkout for pool exhaustion forensics."""
    try:
        pool = engine.pool
        _db_forensics_logger.info(
            "DB_POOL_STATUS | pool_size=%s | checked_out=%s | overflow=%s | checkedin=%s",
            pool.size(), pool.checkedout(), pool.overflow(), pool.checkedin(),
        )
    except Exception:
        pass  # pool status is best-effort diagnostic

@event.listens_for(engine.sync_engine, "invalidate")
def _log_pool_invalidate(dbapi_connection, connection_record, exception):
    """Log DB_RECONNECT when a connection is invalidated (disconnect detected)."""
    _db_forensics_logger.warning(
        "DB_RECONNECT | reason=connection_invalidated | exception=%s",
        str(exception)[:200] if exception else "unknown",
    )

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

sync_database_url = settings.database_url.replace(
    "postgresql+asyncpg",
    "postgresql+psycopg2"
).replace(
    "sqlite+aiosqlite",
    "sqlite"
)
sync_connect_args = {}
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
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event, text
import asyncio
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..config import settings
from .base import Base


connect_args = {}
pool_kwargs = {"pool_pre_ping": True}

def _prepare_asyncpg_url(raw_database_url: str) -> tuple[str, dict[str, object]]:
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

    async_connect_args: dict[str, object] = {}
    if sslmode and sslmode != "disable":
        async_connect_args["ssl"] = True

    async_database_url = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(filtered_pairs, doseq=True),
            parsed.fragment,
        )
    )
    return async_database_url, async_connect_args


database_url, ssl_connect_args = _prepare_asyncpg_url(settings.database_url)
connect_args.update(ssl_connect_args)

# Increase connection timeout to 120s to allow Render free tier Postgres to wake up
if database_url.startswith("postgresql"):
    connect_args["command_timeout"] = 120

# Connection Pooling Limits for Postgres
pool_kwargs["pool_size"] = 20
pool_kwargs["max_overflow"] = 10

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

sync_database_url = settings.database_url.replace(
    "postgresql+asyncpg",
    "postgresql+psycopg2"
).replace(
    "sqlite+aiosqlite",
    "sqlite"
)
sync_connect_args = {}
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
    import logging
    import time
    from pathlib import Path
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy.exc import OperationalError
    
    logger = logging.getLogger("app.db")
    
    # Use absolute path to alembic.ini to avoid working directory issues
    root_dir = Path(__file__).resolve().parents[3]
    alembic_ini_path = root_dir / "backend" / "alembic.ini"
    
    if not alembic_ini_path.exists():
        logger.critical("STARTUP STEP FAILED: alembic.ini not found at %s", alembic_ini_path)
        raise FileNotFoundError(f"Missing alembic.ini at {alembic_ini_path}")
        
    alembic_cfg = Config(str(alembic_ini_path))
    script = ScriptDirectory.from_config(alembic_cfg)
    
    # Support multiple heads in case of branch merges
    expected_heads = set(script.get_heads())
    
    logger.info("STARTUP STEP: DATABASE CONNECTIVITY")
    
    # Transient connection retry loop for database availability
    max_retries = 5
    connection = None
    for attempt in range(max_retries):
        try:
            connection = sync_engine.connect()
            break
        except OperationalError as e:
            if attempt == max_retries - 1:
                logger.critical("STARTUP STEP FAILED: Database unavailable after %d attempts. %s", max_retries, e)
                raise
            logger.warning("Database unavailable, retrying in 2 seconds... (Attempt %d/%d)", attempt + 1, max_retries)
            time.sleep(2)
            
    try:
        with connection:
            logger.info("STARTUP STEP: ALEMBIC VALIDATION")
            context = MigrationContext.configure(connection)
            
            # Fetch current database heads gracefully
            try:
                current_heads = set(context.get_current_heads())
            except Exception as e:
                # Fallback for completely empty databases or unsupported dialects
                logger.warning("Could not fetch current heads from alembic_version: %s", e)
                current_heads = set()
                
            logger.info("STARTUP STEP: EXPECTED REVISION (Heads: %s)", list(expected_heads))
            logger.info("STARTUP STEP: CURRENT REVISION (Heads: %s)", list(current_heads))
            logger.info("STARTUP STEP: MIGRATION STATUS (Expected: %s, Current: %s)", expected_heads, current_heads)
            
            if expected_heads != current_heads:
                error_msg = (
                    f"\nSCHEMA VALIDATION FAILED\n"
                    f"Database Revision: {list(current_heads)}\n"
                    f"Expected Revision: {list(expected_heads)}\n\n"
                    f"Refusing startup.\n"
                    f"Application must terminate.\n"
                )
                logger.critical(error_msg)
                raise RuntimeError(error_msg)
                
            logger.info("STARTUP STEP: APPLICATION READY")
    except Exception as e:
        if not isinstance(e, RuntimeError):
            logger.critical("STARTUP STEP FAILED: Could not validate schema: %s", e)
        raise
