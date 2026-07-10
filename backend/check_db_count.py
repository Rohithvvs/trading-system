import asyncio
from app.db.session import AsyncSessionLocal
from app.models.stock import StockMaster
from sqlalchemy import select, text

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.scalar(text("SELECT count(*) FROM stocks_master"))
        print("Total rows:", res)
        
        res = await db.scalars(select(StockMaster.symbol))
        print("Symbols:", len(list(res.all())))

        res = await db.scalars(select(StockMaster.symbol).where(StockMaster.is_active == True))
        print("Active symbols:", len(list(res.all())))

asyncio.run(main())
