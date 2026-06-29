import asyncio
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text
from datetime import datetime, timedelta

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT symbol, MAX(timestamp) FROM historical_candles GROUP BY symbol ORDER BY MAX(timestamp) DESC LIMIT 5"))
        print('Top 5 max timestamps:')
        for r in res.fetchall():
            print(f'  {r[0]}: {r[1]}')
            
asyncio.run(main())
