import asyncio
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text
import time

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT symbol, ltp, updated_at FROM market_data.ltp_cache"))
        rows = res.mappings().all()
        for r in rows:
            print(dict(r))

asyncio.run(main())
