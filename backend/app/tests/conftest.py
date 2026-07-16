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
    
    # Alembic relies on env.py, which uses settings.database_url natively.
    alembic_cfg = Config(str(ROOT_DIR / "backend" / "alembic.ini"))
    
    # Run migrations synchronously in a thread
    import asyncio
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    
    yield
    # We do not drop tables because some tests might expect persistent data or we drop them if needed

@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

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
