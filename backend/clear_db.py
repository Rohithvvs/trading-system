import asyncio
from backend.app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def clear():
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM paper_trading_execution_events"))
        await db.execute(text("DELETE FROM paper_trading_trade_history"))
        await db.execute(text("DELETE FROM paper_trading_positions"))
        await db.execute(text("DELETE FROM paper_trading_orders"))
        await db.commit()
        print('Cleared')

if __name__ == '__main__':
    asyncio.run(clear())
