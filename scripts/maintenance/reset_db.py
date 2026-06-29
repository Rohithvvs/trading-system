import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from backend.app.config import settings
from sqlalchemy import text

async def reset_db():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        print("Truncating tables...")
        await conn.execute(text("TRUNCATE TABLE paper_trading_orders CASCADE"))
        await conn.execute(text("TRUNCATE TABLE paper_trading_positions CASCADE"))
        await conn.execute(text("TRUNCATE TABLE paper_trading_trade_history CASCADE"))
        await conn.execute(text("TRUNCATE TABLE paper_trading_transactions CASCADE"))
        await conn.execute(text("UPDATE paper_trading_accounts SET cash_balance = starting_balance"))
    print("Done")

if __name__ == "__main__":
    asyncio.run(reset_db())
