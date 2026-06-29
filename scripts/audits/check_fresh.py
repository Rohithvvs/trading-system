import asyncio
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text
from datetime import datetime, timedelta

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT symbol, MAX(timestamp) FROM historical_candles GROUP BY symbol HAVING MAX(timestamp) >= NOW() - INTERVAL '2 days'"))
        fresh_symbols = res.fetchall()
        print('Symbols with fresh cache:', len(fresh_symbols))
        for r in fresh_symbols:
            print(f'  {r[0]}: {r[1]}')
            
asyncio.run(main())
