from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Generator
import logging
import re
import shutil
from datetime import datetime

import pytest


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "tests" / "artifacts" / "backend"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
# Legacy shared path (kept for artifact hooks / env default before per-test rebind)
TEST_DB_PATH = ARTIFACT_DIR / "test_app_v2.db"
# Active per-test SQLite file used by test_engine + rebinding of AsyncSessionLocal
CURRENT_TEST_DB_PATH: Path | None = None

# Export artifact dir and RUN_ID early so the application picks them up when imported
RUN_ID = os.environ.get("RUN_ID") or datetime.utcnow().strftime("%Y%m%dT%H%M%S")
os.environ.setdefault("RUN_ID", RUN_ID)
os.environ.setdefault("TEST_ARTIFACT_DIR", str(ARTIFACT_DIR))

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB_PATH}")
os.environ.setdefault("NIFTY500_SYMBOLS", "INFY-EQ,TCS-EQ,RELIANCE-EQ")
os.environ.setdefault("FYERS_ACCESS_TOKEN", "")
# Snapshot for restoring process-wide engine after per-test rebinds
_DEFAULT_TEST_DATABASE_URL = os.environ["DATABASE_URL"]


from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine
import sqlalchemy.pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID, ARRAY  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

# SQLite cannot render PostgreSQL JSONB/UUID/ARRAY natively. Register compilers early so
# fixture create_all() works without relying on app lifespan hooks.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "CHAR(36)"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "TEXT"



# Support both `pytest` from repo root and from backend/ with PYTHONPATH=.
try:
    from app.config import settings  # noqa: E402
    from app.db.base import Base  # noqa: E402
    from app.db.session import get_db  # noqa: E402
    from app.main import app  # noqa: E402
    from app.models import *  # noqa: F401,F403,E402
except ModuleNotFoundError:
    from backend.app.config import settings  # noqa: E402
    from backend.app.db.base import Base  # noqa: E402
    from backend.app.db.session import get_db  # noqa: E402
    from backend.app.main import app  # noqa: E402
    from backend.app.models import *  # noqa: F401,F403,E402


def _session_modules() -> list[Any]:
    """Return all loaded session modules (app.* and backend.app.* may both exist)."""
    mods: list[Any] = []
    seen: set[int] = set()
    for name in ("app.db.session", "backend.app.db.session"):
        mod = sys.modules.get(name)
        if mod is not None and id(mod) not in seen:
            mods.append(mod)
            seen.add(id(mod))
    if mods:
        return mods
    # Force-import whichever import path works in this process
    try:
        from app.db import session as session_mod  # type: ignore
        return [session_mod]
    except ModuleNotFoundError:
        from backend.app.db import session as session_mod  # type: ignore
        return [session_mod]


def _sqlite_async_url(sync_or_async_url: str) -> str:
    if sync_or_async_url.startswith("sqlite:///") and "+aiosqlite" not in sync_or_async_url:
        return sync_or_async_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return sync_or_async_url


def _rebind_sync_sqlite(db_path: Path) -> None:
    """Point process-wide SessionLocal / get_sync_db at the per-test SQLite file.

    Complements async rebind so paper-trading and other sync FastAPI deps see the
    same schema/file as ``db_session`` and ``AsyncSessionLocal``.
    """
    sync_url = f"sqlite:///{db_path.as_posix()}"
    for sm in _session_modules():
        if not hasattr(sm, "SessionLocal"):
            continue
        new_engine = create_engine(
            sync_url,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        old = getattr(sm, "sync_engine", None)
        sm.sync_engine = new_engine
        sm.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=new_engine,
            expire_on_commit=False,
        )
        if old is not None:
            try:
                old.dispose(close=True)
            except TypeError:
                try:
                    old.dispose()
                except Exception:
                    pass
            except Exception:
                pass


def _rebind_async_sqlite(db_path: Path) -> None:
    """Point process-wide AsyncSessionLocal at the per-test SQLite file (NullPool).

    Rebinds every loaded session module so dual import paths (app vs backend.app)
    cannot keep writing into a stale shared DB (regression R1/R2).
    """
    global CURRENT_TEST_DB_PATH
    CURRENT_TEST_DB_PATH = db_path

    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    for sm in _session_modules():
        new_engine = create_async_engine(
            async_url,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        if hasattr(sm, "rebind_async_engine"):
            sm.rebind_async_engine(new_engine)
        else:
            # Fallback for older session modules
            try:
                sm.engine.sync_engine.dispose(close=True)
            except Exception:
                pass
            sm.engine = new_engine
            sm.AsyncSessionLocal = async_sessionmaker(
                bind=new_engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
                class_=AsyncSession,
            )

    # Keep sync form for Alembic/settings; env.py converts to aiosqlite for async
    sync_url = f"sqlite:///{db_path.as_posix()}"
    os.environ["DATABASE_URL"] = sync_url
    try:
        settings.database_url = sync_url
    except Exception:
        pass

    # Sync SessionLocal must track the same file as async + db_session
    _rebind_sync_sqlite(db_path)


def _dispose_async_sqlite() -> None:
    for sm in _session_modules():
        try:
            sm.engine.sync_engine.dispose(close=True)
        except Exception:
            pass


def _restore_default_async_engine() -> None:
    """Restore process-wide async + sync engines after per-test rebind teardown."""
    global CURRENT_TEST_DB_PATH
    CURRENT_TEST_DB_PATH = None
    sync_url = _DEFAULT_TEST_DATABASE_URL
    os.environ["DATABASE_URL"] = sync_url
    try:
        settings.database_url = sync_url
    except Exception:
        pass
    async_url = _sqlite_async_url(sync_url)
    for sm in _session_modules():
        new_engine = create_async_engine(
            async_url,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        if hasattr(sm, "rebind_async_engine"):
            sm.rebind_async_engine(new_engine)
        else:
            try:
                sm.engine.sync_engine.dispose(close=True)
            except Exception:
                pass
            sm.engine = new_engine
            sm.AsyncSessionLocal = async_sessionmaker(
                bind=new_engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
                class_=AsyncSession,
            )
    # Restore sync SessionLocal to the default test DATABASE_URL
    try:
        default_path = Path(sync_url.replace("sqlite:///", "", 1))
        if default_path.suffix or "sqlite" in sync_url:
            _rebind_sync_sqlite(default_path)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def test_settings() -> Generator[None, None, None]:
    settings.app_env = "test"
    settings.nifty500_symbols = ["INFY-EQ", "TCS-EQ", "RELIANCE-EQ"]
    yield


@pytest.fixture()
def test_engine():
    """Fresh per-test SQLite DB shared by sync engine and app AsyncSessionLocal."""
    global CURRENT_TEST_DB_PATH
    db_path = ARTIFACT_DIR / f"test_{uuid.uuid4().hex}.db"
    CURRENT_TEST_DB_PATH = db_path

    if db_path.exists():
        try:
            db_path.unlink()
        except OSError:
            pass

    # Dispose any prior async pool before creating a new file path
    _dispose_async_sqlite()

    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )

    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("PRAGMA journal_mode=WAL"))
        conn.execute(sqlalchemy.text("PRAGMA synchronous=NORMAL"))
        conn.commit()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Ensure services that open AsyncSessionLocal see the same schema/file
    _rebind_async_sqlite(db_path)

    yield engine

    _dispose_async_sqlite()
    engine.dispose()
    if db_path.exists():
        try:
            db_path.unlink()
        except OSError:
            pass
    # Restore default engine so subsequent suites (e.g. app/tests) are not left
    # with a disposed/deleted SQLite file binding.
    _restore_default_async_engine()


@pytest.fixture()
def db_session(test_engine) -> Generator[Session, None, None]:
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, class_=Session)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
async def async_db_session():
    """Async SQLite session for MarketEngineService paths that await AsyncSession APIs.

    In-memory only. Engine helpers that open a separate sync ``SessionLocal`` for
    notifications are stubbed in market-engine tests to avoid cross-engine locks.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.fixture()
def client(test_engine) -> Generator[TestClient, None, None]:
    """HTTP client against the per-test DB using real async/sync session factories.

    Do **not** override ``get_db`` with a sync ``Session``: FastAPI async routes
    call ``await db.execute`` and fail with ChunkedIteratorResult errors when a
    sync session is injected. ``test_engine`` rebinds ``AsyncSessionLocal`` and
    ``SessionLocal`` to the same SQLite file used by ``db_session``.

    Prefer ``db_session.commit()`` before API reads when seeding via the sync
    fixture so the async path observes committed rows.
    """
    # Clear any leftover overrides from other fixtures
    app.dependency_overrides.pop(get_db, None)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def artifact_dir() -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACT_DIR


@pytest.fixture()
def write_artifact(artifact_dir: Path):
    def _write(name: str, payload: Any) -> Path:
        path = artifact_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, (dict, list)):
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        else:
            path.write_text(str(payload), encoding="utf-8")
        return path

    return _write


@pytest.fixture(autouse=True)
def per_test_log(request, artifact_dir: Path):
    """Attach a per-test file handler so each test gets its own log file.

    Files are written to `tests/artifacts/backend/logs/<sanitized_test_name>.log`.
    """
    test_name = request.node.nodeid
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", test_name)
    path = artifact_dir / "logs" / f"{sanitized}.log"
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(path, encoding="utf-8", mode="w")
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        yield
    finally:
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.failed:
        # Copy the active per-test sqlite DB file for offline inspection
        try:
            src = CURRENT_TEST_DB_PATH if CURRENT_TEST_DB_PATH and CURRENT_TEST_DB_PATH.exists() else None
            if src is None and TEST_DB_PATH.exists():
                src = TEST_DB_PATH
            if src is not None:
                dst = ARTIFACT_DIR / "db" / f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', rep.nodeid)}.db"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        except Exception as e:
            try:
                (ARTIFACT_DIR / "db" / f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', rep.nodeid)}_db_error.txt").write_text(str(e))
            except Exception:
                pass


@pytest.fixture(autouse=True)
def reset_rule_manager():
    """Reset the RuleManager singleton before and after each test."""
    try:
        from app.governance.rule_manager import RuleManager
        RuleManager.reset_instance()
    except ImportError:
        pass
    yield
    try:
        from app.governance.rule_manager import RuleManager
        RuleManager.reset_instance()
    except ImportError:
        pass

