import asyncio
import os
import sys

# Add current directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./tests/artifacts/e2e_app.db"
os.environ["SYNC_DATABASE_URL"] = "sqlite:///./tests/artifacts/e2e_app.db"

from backend.app.db.session import engine
from backend.app.db.base import Base

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("Test Database initialized successfully.")

if __name__ == "__main__":
    asyncio.run(init_db())
