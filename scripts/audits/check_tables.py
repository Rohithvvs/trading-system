import asyncio
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        tables = [row[0] for row in res]
        print("Tables in public schema:")
        for t in tables:
            print("-", t)
        
        if "historical_candle" in tables:
            print("historical_candle count:", (await db.execute(text("SELECT COUNT(*) FROM historical_candle"))).scalar())
        if "historical_candles" in tables:
            print("historical_candles count:", (await db.execute(text("SELECT COUNT(*) FROM historical_candles"))).scalar())

asyncio.run(main())
