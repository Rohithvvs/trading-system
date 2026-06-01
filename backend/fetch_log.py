import asyncio
import sys
sys.path.append('F:/trading system01/trading system/backend')
from app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT message, traceback FROM system_logs WHERE level='ERROR' ORDER BY id DESC LIMIT 1;"))
        row = res.fetchone()
        if row:
            print("Message:", row[0])
            print("Traceback:")
            print(row[1])

if __name__ == "__main__":
    asyncio.run(main())
