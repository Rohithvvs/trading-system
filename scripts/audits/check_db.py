
import asyncio
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text('SELECT COUNT(*) FROM scanned_candidates'))
        print('scanned_candidates count:', res.scalar())

asyncio.run(main())

