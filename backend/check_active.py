import asyncio
from app.db.session import AsyncSessionLocal
from app.models.stock import StockMaster
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        res1 = await db.scalars(select(StockMaster).where(StockMaster.universe == "NIFTY500"))
        all_nifty = res1.all()
        print("Total NIFTY500 rows:", len(all_nifty))

        res2 = await db.scalars(select(StockMaster).where(StockMaster.universe == "NIFTY500").where(StockMaster.is_active == True))
        active_nifty = res2.all()
        print("Active NIFTY500 rows:", len(active_nifty))

asyncio.run(main())
