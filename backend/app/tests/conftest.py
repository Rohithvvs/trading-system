import json
import os
import tempfile
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
import gc
from pathlib import Path

from app.main import app
from app.db.session import AsyncSessionLocal, engine, Base

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
async def initialize_db():
    from alembic.config import Config
    from alembic import command
    from app.config import settings
    from app.config.settings import ROOT_DIR

    db_url = (getattr(settings, "database_url", None) or os.environ.get("DATABASE_URL") or "")
    # When the root tests/conftest forces a shared SQLite file, tables are often
    # already created via Base.metadata.create_all / per-test engines. Running the
    # full Alembic baseline there collides ("table already exists"). Postgres CI
    # still runs migrations normally.
    if "sqlite" in db_url:
        yield
        return

    # Alembic relies on env.py, which uses settings.database_url natively.
    alembic_cfg = Config(str(ROOT_DIR / "backend" / "alembic.ini"))

    # Run migrations synchronously in a thread
    import asyncio
    import logging

    try:
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    except Exception as exc:
        # Do not abort the whole suite when local DB history is incomplete, but
        # never swallow silently (regression R3).
        logging.getLogger("app.tests.conftest").warning(
            "Alembic upgrade head failed (continuing tests): %s", exc
        )

    yield
    # We do not drop tables because some tests might expect persistent data or we drop them if needed

def _is_db_unavailable_error(exc: BaseException) -> bool:
    """True when the failure is environmental (quota/connectivity), not app logic."""
    name = type(exc).__name__
    msg = str(exc).lower()
    needles = (
        "quota",
        "insufficientresources",
        "connection refused",
        "could not connect",
        "timeout",
        "name or service not known",
        "network is unreachable",
        "ssl connection has been closed",
        "too many connections",
        "server closed the connection",
    )
    if any(n in name.lower() for n in ("insufficient", "operationalerror", "interfaceerror")):
        if any(n in msg for n in needles) or "quota" in msg:
            return True
    return any(n in msg for n in needles)


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a live async session, or skip when the database is environmentally unavailable.

    Integration tests that need Postgres must not fail CI red when Neon/local DB
    is down or over quota — that is not an application regression.
    """
    from sqlalchemy import text

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            yield session
    except Exception as exc:
        if _is_db_unavailable_error(exc):
            pytest.skip(f"Database unavailable for integration test: {exc}")
        raise

@pytest.fixture
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

@pytest.fixture(autouse=True)
async def check_leaks(request):
    """Strictly assert no leaked tasks or sessions after every test."""
    yield
    # Force GC to clean up unreferenced sessions
    gc.collect()
    
    # Check for leaked tasks
    pending_tasks = [t for t in asyncio.all_tasks() if not t.done() and t != asyncio.current_task()]
    if pending_tasks:
        pytest.fail(f"Test leaked {len(pending_tasks)} background tasks: {pending_tasks}")


# ---- Tempfile fixtures for JSONL and audit stores ----


@pytest.fixture
def temp_dir() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def jsonl_store(temp_dir: Path):
    from app.core.jsonl_store import JsonlStore

    store = JsonlStore(base_dir=temp_dir, category="test")
    yield store


@pytest.fixture
def audit_store(temp_dir: Path):
    from app.core.audit_store import AuditStore

    store = AuditStore(file_path=temp_dir / "audit.jsonl")
    yield store


@pytest.fixture
def sample_log_event() -> dict:
    return {
        "uuid": "123e4567-e89b-12d3-a456-426614174000",
        "timestamp": "2026-07-16T10:00:00Z",
        "level": "info",
        "source": "test",
        "message": "Test log event",
    }


@pytest.fixture
def sample_metric_observation() -> dict:
    from datetime import datetime, timezone

    return {
        "uuid": "223e4567-e89b-12d3-a456-426614174001",
        "experiment_id": None,
        "name": "cpu_usage",
        "value": 45.2,
        "unit": "%",
        "tags": {"host": "test-server"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
