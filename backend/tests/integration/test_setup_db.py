import os
import pytest
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./tests/artifacts/e2e_app.db"
os.environ["SYNC_DATABASE_URL"] = "sqlite:///./tests/artifacts/e2e_app.db"

from backend.app.db.session import engine
from backend.app.db.base import Base

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@pytest.mark.asyncio
async def test_init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
