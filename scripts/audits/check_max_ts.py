import asyncio
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text
from datetime import datetime, timedelta

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT MAX(timestamp) FROM historical_candles"))
        max_ts = res.scalar()
        print('Max timestamp:', max_ts)
        
        # also count how many symbols have this max timestamp
        if max_ts:
            res = await db.execute(text(f"SELECT COUNT(DISTINCT symbol) FROM historical_candles WHERE timestamp = '{max_ts}'"))
            print('Symbols with max timestamp:', res.scalar())
            
asyncio.run(main())
