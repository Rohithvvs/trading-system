import pytest
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError, DBAPIError

from backend.app.db.session import AsyncSessionLocal

@pytest.fixture(autouse=True)
async def cleanup_failures(db: AsyncSession):
    await db.execute(text("TRUNCATE paper_trading_trade_history, paper_trading_transactions, paper_trading_positions, paper_trading_orders, paper_trading_accounts, migration_checkpoints CASCADE"))
    await db.execute(
        text("""
            INSERT INTO paper_trading_accounts (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
            VALUES (601, 'Fail 1', 'USD', 1000, 1000, 0.02, NOW(), NOW()),
                   (602, 'Fail 2', 'USD', 1000, 1000, 0.02, NOW(), NOW())
        """)
    )
    await db.commit()

@pytest.mark.asyncio
async def test_postgres_deadlock_simulation():
    """
    Verify PostgreSQL automatically detects and terminates deadlocks, preventing infinite hangs.
    """
    # A standard deadlock:
    # Tx1 locks row A, then tries to lock row B
    # Tx2 locks row B, then tries to lock row A
    
    event_1 = asyncio.Event()
    event_2 = asyncio.Event()
    
    async def worker_1():
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT * FROM paper_trading_accounts WHERE id=601 FOR UPDATE"))
            event_1.set()
            await event_2.wait()
            try:
                # This will cause a deadlock because worker_2 holds the lock on 602
                await db.execute(text("SELECT * FROM paper_trading_accounts WHERE id=602 FOR UPDATE"))
                await db.commit()
            except (OperationalError, DBAPIError) as e:
                assert "deadlock detected" in str(e).lower()
                await db.rollback()

    async def worker_2():
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT * FROM paper_trading_accounts WHERE id=602 FOR UPDATE"))
            event_2.set()
            await event_1.wait()
            try:
                # This will cause a deadlock because worker_1 holds the lock on 601
                await db.execute(text("SELECT * FROM paper_trading_accounts WHERE id=601 FOR UPDATE"))
                await db.commit()
            except (OperationalError, DBAPIError) as e:
                assert "deadlock detected" in str(e).lower()
                await db.rollback()

    tasks = [asyncio.create_task(worker_1()), asyncio.create_task(worker_2())]
    # One of them will throw a deadlock detected exception and rollback, the other will succeed.
    # The exceptions are caught inside the workers.
    await asyncio.gather(*tasks)

@pytest.mark.asyncio
async def test_postgres_connection_drop_simulation():
    """
    Verify application handles unexpected database connection drops (e.g., pg_terminate_backend).
    """
    async with AsyncSessionLocal() as db:
        # Start a transaction
        await db.execute(text("UPDATE paper_trading_accounts SET cash_balance = 500 WHERE id = 601"))
        
        try:
            # Terminate our own connection natively to simulate network drop / DB restart
            await db.execute(text("SELECT pg_terminate_backend(pg_backend_pid())"))
        except (OperationalError, DBAPIError, ConnectionError) as e:
            # Expected! The connection was dropped!
            pass
            
    # Open a new connection and verify the uncommitted transaction was fully rolled back
    async with AsyncSessionLocal() as db2:
        res = await db2.execute(text("SELECT cash_balance FROM paper_trading_accounts WHERE id=601"))
        # It should remain 1000, not 500.
        assert res.scalar() == 1000.0

@pytest.mark.asyncio
async def test_postgres_rollback_recovery(db: AsyncSession):
    """
    Verify that an application can successfully recover and issue new commands after a transaction error.
    """
    try:
        # Cause a deliberate syntax error to abort the transaction
        await db.execute(text("SELECT * FROM table_that_does_not_exist"))
    except Exception:
        pass
        
    # The transaction is now in an aborted state natively in Postgres
    with pytest.raises(Exception) as exc:
        # Subsequent queries should fail until rolled back
        await db.execute(text("SELECT * FROM paper_trading_accounts"))
    
    assert "current transaction is aborted" in str(exc.value).lower() or "transaction is aborted" in str(exc.value).lower()
    
    # Rollback to recover
    await db.rollback()
    
    # New queries succeed
    res = await db.execute(text("SELECT COUNT(*) FROM paper_trading_accounts"))
    assert res.scalar() >= 0
