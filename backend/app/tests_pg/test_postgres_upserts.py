import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.fixture(autouse=True)
async def cleanup_upserts(db: AsyncSession):
    await db.execute(text("TRUNCATE paper_trading_trade_history, paper_trading_transactions, paper_trading_positions, paper_trading_orders, paper_trading_accounts, migration_checkpoints CASCADE"))
    await db.commit()

@pytest.mark.asyncio
async def test_postgres_on_conflict_do_update_idempotent_replay(db: AsyncSession):
    """
    Verify PostgreSQL native INSERT ... ON CONFLICT DO UPDATE handles idempotent replays cleanly.
    """
    # Using the migration_checkpoints table we just modified as it is native to the system
    # Wait, we can use paper_trading_orders idempotency_key since there is a unique index on it!
    # The unique index is on `idempotency_key`
    
    # Insert first time
    await db.execute(text("INSERT INTO paper_trading_accounts (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at) VALUES (500, 'Upsert Test', 'USD', 1000, 1000, 0.02, NOW(), NOW())"))
    
    upsert_query = text("""
        INSERT INTO paper_trading_orders 
        (id, account_id, symbol, side, order_type, qty, order_price, status, idempotency_key, created_at, updated_at, lifecycle_state, product_type)
        VALUES (501, 500, 'ETH-USD', 'BUY', 'LIMIT', 1.0, 3000.0, 'PENDING', 'upsert-key-1', NOW(), NOW(), 'PENDING_ENTRY', 'CNC')
        ON CONFLICT (idempotency_key) DO UPDATE SET 
        status = EXCLUDED.status,
        updated_at = EXCLUDED.updated_at
    """)
    
    # Execute first time - INSERT
    await db.execute(upsert_query)
    
    res = await db.execute(text("SELECT status FROM paper_trading_orders WHERE idempotency_key = 'upsert-key-1'"))
    assert res.scalar() == 'PENDING'
    
    # Execute second time - UPDATE (replay)
    upsert_query_2 = text("""
        INSERT INTO paper_trading_orders 
        (id, account_id, symbol, side, order_type, qty, order_price, status, idempotency_key, created_at, updated_at, lifecycle_state, product_type)
        VALUES (502, 500, 'ETH-USD', 'BUY', 'LIMIT', 1.0, 3000.0, 'FILLED', 'upsert-key-1', NOW(), NOW(), 'PENDING_ENTRY', 'CNC')
        ON CONFLICT (idempotency_key) DO UPDATE SET 
        status = EXCLUDED.status,
        updated_at = EXCLUDED.updated_at
    """)
    
    # It should not insert a new row, but update the existing one
    await db.execute(upsert_query_2)
    
    # Verify count is still 1
    res = await db.execute(text("SELECT COUNT(*) FROM paper_trading_orders WHERE idempotency_key = 'upsert-key-1'"))
    assert res.scalar() == 1
    
    # Verify status was updated
    res = await db.execute(text("SELECT status FROM paper_trading_orders WHERE idempotency_key = 'upsert-key-1'"))
    assert res.scalar() == 'FILLED'
