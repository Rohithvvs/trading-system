import asyncio
import asyncpg
from app.config import settings

async def main():
    url = settings.database_url.replace("+asyncpg", "")
    conn = await asyncpg.connect(url)
    await conn.execute("DELETE FROM system_locks WHERE lock_name = 'scan_execution'")
    print("Lock released successfully")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
