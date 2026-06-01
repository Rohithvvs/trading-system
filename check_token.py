
import asyncio
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text('SELECT access_token, is_active FROM fyers_tokens'))
        print('Tokens:', res.fetchall())

asyncio.run(main())

