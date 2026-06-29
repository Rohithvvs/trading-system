import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from backend.app.db.base import Base
from backend.app.config import settings

# Import all models to ensure they are registered with Base.metadata
from backend.app.models import analysis, fyers_token, market_data, paper_trading, stock, system_log, workstation

async def create_tables():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        print("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
    print("Done")

if __name__ == "__main__":
    asyncio.run(create_tables())
