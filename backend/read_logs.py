import asyncio
from app.db import AsyncSessionLocal
from sqlalchemy import text

async def get_logs():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT * FROM system_logs ORDER BY id DESC LIMIT 5"))
        for row in res.mappings().all():
            print(f"[{row['level']}] {row['module']} - {row['message']}")
            if row['traceback']:
                print(row['traceback'])
            print("-" * 50)

if __name__ == "__main__":
    asyncio.run(get_logs())
