import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
import gc

from backend.app.main import app
from backend.app.db.session import AsyncSessionLocal, engine, Base
from backend.app.config import settings

# Verify we are running against PostgreSQL
if "sqlite" in settings.database_url:
    pytest.exit("FATAL: tests_pg must run against PostgreSQL, but sqlite was detected in settings.database_url")

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
async def initialize_db():
    from alembic.config import Config
    from alembic import command
    from backend.app.config import settings
    from backend.app.config.settings import ROOT_DIR
    
    alembic_cfg = Config(str(ROOT_DIR / "backend" / "alembic.ini"))
    import asyncio
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    yield

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
    yield
    gc.collect()
    pending_tasks = [t for t in asyncio.all_tasks() if not t.done() and t != asyncio.current_task()]
    if pending_tasks:
        pytest.fail(f"Test leaked {len(pending_tasks)} background tasks: {pending_tasks}")
