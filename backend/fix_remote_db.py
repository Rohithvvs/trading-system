import asyncio
import asyncpg
from app.config.settings import settings

async def fix():
    url = settings.database_url.replace("+asyncpg", "")
    print("Connecting to", url)
    conn = await asyncpg.connect(url)
    await conn.execute("UPDATE alembic_version SET version_num = '761f3802942c'")
    await conn.close()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(fix())
