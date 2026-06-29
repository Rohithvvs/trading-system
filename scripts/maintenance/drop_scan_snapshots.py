import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from backend.app.config import settings
from sqlalchemy import text

async def drop():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        print("Dropping scan_snapshots...")
        await conn.execute(text("DROP TABLE IF EXISTS scan_snapshots CASCADE"))
    print("Done")

if __name__ == "__main__":
    asyncio.run(drop())
