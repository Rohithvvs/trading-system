import asyncio
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT * FROM scan_history_snapshots ORDER BY created_at DESC LIMIT 1"))
        snap = res.mappings().fetchone()
        if snap:
            print("Snapshot:", dict(snap))
        else:
            print("No snapshot")
            
        res = await db.execute(text("SELECT * FROM saved_scans ORDER BY created_at DESC LIMIT 1"))
        saved = res.mappings().fetchone()
        if saved:
            print("Saved scan:", dict(saved))
        else:
            print("No saved scan")
            
asyncio.run(main())
