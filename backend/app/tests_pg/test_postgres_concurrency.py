import pytest
import asyncio
from sqlalchemy import text
from backend.app.db.session import AsyncSessionLocal

@pytest.fixture(autouse=True)
async def setup_concurrency(db):
    await db.execute(text("TRUNCATE paper_trading_trade_history, paper_trading_transactions, paper_trading_positions, paper_trading_orders, paper_trading_accounts, migration_checkpoints CASCADE"))
    await db.execute(
        text("""
            INSERT INTO paper_trading_accounts (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
            VALUES (400, 'Concurrency Target', 'USD', 1000.0, 1000.0, 0.02, NOW(), NOW())
        """)
    )
    await db.commit()

@pytest.mark.asyncio
async def test_postgres_concurrent_pool_exhaustion_safety():
    """
    Verify 50+ concurrent async requests can successfully share the connection pool natively without starvation or leaks.
    """
    # Fire 50 concurrent transactions that perform a SELECT and short sleep
    async def run_query(idx):
        async with AsyncSessionLocal() as session:
            # We don't use FOR UPDATE here as we just test pool checkout contention
            res = await session.execute(text("SELECT id FROM paper_trading_accounts WHERE id=400"))
            assert res.scalar() == 400
            await asyncio.sleep(0.01)
            
    tasks = [asyncio.create_task(run_query(i)) for i in range(50)]
    
    # gather will wait for all tasks to complete; any unhandled exceptions (e.g. timeout) will be raised.
    await asyncio.gather(*tasks)

@pytest.mark.asyncio
async def test_postgres_concurrent_deadlock_avoidance():
    """
    Verify 50 concurrent transactions performing simple read/writes avoid deadlocks using pg defaults.
    """
    async def write_query(idx):
        async with AsyncSessionLocal() as session:
            # Simple point-update
            # In PostgreSQL, updating the same row concurrently blocks but should not deadlock 
            # if order is preserved (we are only updating one row, so no circular waits)
            await session.execute(
                text("UPDATE paper_trading_accounts SET cash_balance = cash_balance + 1 WHERE id = 400")
            )
            await session.commit()
            
    tasks = [asyncio.create_task(write_query(i)) for i in range(50)]
    
    await asyncio.gather(*tasks)
    
    # Verify exactly 50 updates were applied
    async with AsyncSessionLocal() as session:
        res = await session.execute(text("SELECT cash_balance FROM paper_trading_accounts WHERE id=400"))
        assert res.scalar() == 1050.0  # 1000 + (50 * 1)
