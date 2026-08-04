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
    # Disable asyncpg prepared-statement LRU cache.
    # After ALTER TABLE / migrations (and with Neon / PgBouncer poolers), cached plans
    # raise InvalidCachedStatementError and fail the request unless we retry or disable.
    # statement_cache_size=0 is the stable fix; small CPU tradeoff for reliability.
    connect_args["statement_cache_size"] = 0

# Connection Pooling Limits for Postgres / Neon
# pool_pre_ping keeps connections warm and detects drops without full reconnect every request
pool_kwargs["pool_size"] = 20
pool_kwargs["max_overflow"] = 10
# Recycle before Neon/proxy idle kills (typically ~5 min); 4 min keeps pool warm
pool_kwargs["pool_recycle"] = 240

engine = create_async_engine(
    database_url,
    connect_args=connect_args,
    **pool_kwargs
)

# ---------------------------------------------------------------------------
# DB POOL FORENSICS — passive observers, no business logic changes
# ---------------------------------------------------------------------------
import logging as _db_logging

_db_forensics_logger = _db_logging.getLogger("app.db_forensics")


class RebindableAsyncSessionLocal:
    """Callable session factory whose underlying maker can be swapped in tests.

    Modules that ``from app.db.session import AsyncSessionLocal`` keep a reference
    to this proxy object. Rebinding updates ``_factory`` so all importers open
    sessions against the current engine (prevents shared-file SQLite leakage).
    """

    __slots__ = ("_factory",)

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    def rebind(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    def __call__(self, *args, **kwargs):
        return self._factory(*args, **kwargs)

    def configure(self, **kwargs):
        return self._factory.configure(**kwargs)


def is_stale_prepared_plan_error(exc: BaseException) -> bool:
    """True when asyncpg/SQLAlchemy rejects a cached plan after schema change."""
    name = type(exc).__name__
    if "InvalidCachedStatement" in name:
        return True
    msg = str(exc)
    return "InvalidCachedStatement" in msg or "cached statement plan is invalid" in msg


def is_db_connection_error(exc: BaseException) -> bool:
    """True when the underlying DB connection is dead or unusable.

    Covers asyncpg/SQLAlchemy ``InterfaceError`` / ``OperationalError`` cases such as
    ``connection is closed``, server-side idle kills, and pooler disconnects.
    Callers should open a *fresh* session (and optionally dispose the pool) and retry.
    """
    name = type(exc).__name__
    if name in {"InterfaceError", "OperationalError", "DBAPIError"}:
        # Narrow DBAPIError to connection-class messages only.
        pass
    msg = str(exc).lower()
    needles = (
        "connection is closed",
        "connection was closed",
        "connection does not exist",
        "server closed the connection",
        "connection reset",
        "broken pipe",
        "terminating connection",
        "ssl connection has been closed",
        "could not connect",
        "connection refused",
        "too many connections",
    )
    if any(n in msg for n in needles):
        return True
    # Walk cause chain (SQLAlchemy wraps asyncpg errors).
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return is_db_connection_error(cause)
    orig = getattr(exc, "orig", None)
    if orig is not None and orig is not exc:
        return is_db_connection_error(orig)
    return False


async def dispose_async_pool(reason: str = "manual") -> None:
    """Drop all pooled async connections (e.g. after DDL or stale plan errors)."""
    try:
        await engine.dispose()
        _db_forensics_logger.warning("DB_POOL_DISPOSED | reason=%s", reason)
    except Exception as exc:  # pragma: no cover
        _db_forensics_logger.warning("DB_POOL_DISPOSE_FAILED | reason=%s | err=%s", reason, exc)


def rebind_async_engine(new_engine) -> None:
    """Replace the process-wide async engine and session factory (test isolation)."""
    global engine
    old_engine = engine
    engine = new_engine
    new_factory = async_sessionmaker(
        bind=new_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    AsyncSessionLocal.rebind(new_factory)
    try:
        old_engine.sync_engine.dispose(close=True)
    except Exception:
        pass
    _attach_engine_listeners(engine)


def _attach_engine_listeners(target_engine) -> None:
    """Idempotent-ish attach of pool forensics listeners to the active engine."""
    sync_eng = target_engine.sync_engine

    # Avoid duplicate handlers when rebinding frequently in tests
    if getattr(sync_eng, "_ts_forensics_attached", False):
        return

    @event.listens_for(sync_eng, "connect")
    def set_postgres_timeouts(dbapi_connection, connection_record):  # noqa: ANN001
        if target_engine.name != "postgresql":
            return
        cursor = dbapi_connection.cursor()
        cursor.execute("SET statement_timeout = '30s'")
        cursor.execute("SET lock_timeout = '5s'")
        cursor.execute("SET idle_in_transaction_session_timeout = '30s'")
        cursor.close()

    @event.listens_for(sync_eng, "checkout")
    def _log_pool_checkout(dbapi_connection, connection_record, connection_proxy):  # noqa: ANN001
        try:
            pool = target_engine.pool
            _db_forensics_logger.info(
                "DB_POOL_STATUS | pool_size=%s | checked_out=%s | overflow=%s | checkedin=%s",
                pool.size(),
                pool.checkedout(),
                pool.overflow(),
                pool.checkedin(),
            )
        except Exception:
            pass

    @event.listens_for(sync_eng, "invalidate")
    def _log_pool_invalidate(dbapi_connection, connection_record, exception):  # noqa: ANN001
        _db_forensics_logger.warning(
            "DB_RECONNECT | reason=connection_invalidated | exception=%s",
            str(exception)[:200] if exception else "unknown",
        )

    sync_eng._ts_forensics_attached = True  # type: ignore[attr-defined]


_attach_engine_listeners(engine)

AsyncSessionLocal = RebindableAsyncSessionLocal(
    async_sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )
)

main_event_loop = None

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    db = AsyncSessionLocal()
    try:
        yield db
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        # One-shot pool recovery for post-migration prepared-plan invalidation.
        # Route handlers that catch exceptions still need their own retry; this
        # ensures uncaught cases invalidate the pool for subsequent requests.
        if is_stale_prepared_plan_error(exc):
            await dispose_async_pool(reason="stale_prepared_plan")
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
    """Validate schema lineage; auto-upgrade when ALEMBIC_AUTO_UPGRADE is enabled.

    Delegates to :mod:`app.db.bootstrap`. Never stamps head on an empty database.
    """
    from .bootstrap import check_or_upgrade_schema

    check_or_upgrade_schema(auto_upgrade=None)
