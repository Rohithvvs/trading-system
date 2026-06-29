import asyncio
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def check():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT scan_id, scan_timestamp FROM scan_snapshots ORDER BY scan_timestamp DESC LIMIT 1"))
        row = res.fetchone()
        print('Latest scan:', row)
        
        if row:
            res2 = await db.execute(text(f"SELECT count(1) FROM scan_snapshot_records WHERE scan_id='{row[0]}'"))
            print('Records count:', res2.scalar())

if __name__ == "__main__":
    asyncio.run(check())
