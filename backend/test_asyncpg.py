import asyncio
import asyncpg
from app.config import settings

async def main():
    # settings.database_url is in format "postgresql+asyncpg://user:pass@host/db"
    # asyncpg expects "postgresql://user:pass@host/db"
    url = settings.database_url.replace("+asyncpg", "")
    conn = await asyncpg.connect(url)
    rows = await conn.fetch("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'scan_snapshots'")
    for r in rows:
        print(dict(r))
    await conn.close()

asyncio.run(main())
