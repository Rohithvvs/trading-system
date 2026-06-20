import asyncio
import asyncpg
from app.config import settings

async def main():
    url = settings.database_url.replace("+asyncpg", "")
    conn = await asyncpg.connect(url)
    rows = await conn.fetch("SELECT * FROM system_locks")
    for r in rows:
        print(dict(r))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
