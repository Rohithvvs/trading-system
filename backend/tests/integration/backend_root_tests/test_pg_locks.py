import asyncio
import pprint
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT query, state FROM pg_stat_activity WHERE state = 'active'"))
        pprint.pprint(res.fetchall())

if __name__ == "__main__":
    asyncio.run(main())
