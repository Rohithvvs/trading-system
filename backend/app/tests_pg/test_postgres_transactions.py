import pytest
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DBAPIError, OperationalError

@pytest.fixture(autouse=True)
async def cleanup_transactions(db: AsyncSession):
    await db.execute(text("TRUNCATE paper_trading_trade_history, paper_trading_transactions, paper_trading_positions, paper_trading_orders, paper_trading_accounts, migration_checkpoints CASCADE"))
    await db.commit()

@pytest.mark.asyncio
async def test_postgres_transaction_rollback(db: AsyncSession):
    """
    Verify asyncpg transaction rollback behavior native to postgres.
    """
    await db.execute(
        text("""
            INSERT INTO paper_trading_accounts (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
            VALUES (999, 'Rollback Test', 'USD', 1000.00, 1000.00, 0.02, NOW(), NOW())
        """)
    )
    # Validate it exists in the current uncommitted transaction
    res = await db.execute(text("SELECT name FROM paper_trading_accounts WHERE id=999"))
    assert res.scalar() == 'Rollback Test'

    # Rollback
    await db.rollback()

    # Verify rollback successfully removed data natively
    res = await db.execute(text("SELECT COUNT(*) FROM paper_trading_accounts WHERE id=999"))
    assert res.scalar() == 0

@pytest.mark.asyncio
async def test_postgres_nested_transaction_savepoints(db: AsyncSession):
    """
    Verify PostgreSQL SAVEPOINT logic behavior using async session nested transactions.
    """
    await db.execute(
        text("""
            INSERT INTO paper_trading_accounts (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
            VALUES (888, 'Outer Account', 'USD', 1000.00, 1000.00, 0.02, NOW(), NOW())
        """)
    )
    
    try:
        # Enter nested transaction (creates a SAVEPOINT in postgres)
        async with db.begin_nested():
            await db.execute(
                text("""
                    INSERT INTO paper_trading_accounts (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
                    VALUES (777, 'Inner Account', 'USD', 1000.00, 1000.00, 0.02, NOW(), NOW())
                """)
            )
            # Force a rollback of just the inner transaction by raising an exception
            raise RuntimeError("Trigger savepoint rollback")
    except RuntimeError:
        pass
    # The outer transaction should still be active and uncommitted
    res1 = await db.execute(text("SELECT COUNT(*) FROM paper_trading_accounts WHERE id=888"))
    assert res1.scalar() == 1
    
    res2 = await db.execute(text("SELECT COUNT(*) FROM paper_trading_accounts WHERE id=777"))
    assert res2.scalar() == 0
    
    await db.commit()

@pytest.mark.asyncio
async def test_postgres_statement_timeout(db: AsyncSession):
    """
    Verify PostgreSQL statement timeout enforcement prevents rogue queries.
    """
    await db.execute(text("SET statement_timeout = '100ms'"))
    
    with pytest.raises((DBAPIError, OperationalError)) as exc:
        # Simulate a slow query using pg_sleep
        await db.execute(text("SELECT pg_sleep(0.5)"))
        
    assert "canceling statement due to statement timeout" in str(exc.value).lower() or "timeout" in str(exc.value).lower()
    await db.rollback() # Reset transaction state after error
