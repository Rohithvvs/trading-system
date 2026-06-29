import pytest
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.fixture(autouse=True)
async def cleanup_precision(db: AsyncSession):
    await db.execute(text("TRUNCATE paper_trading_trade_history, paper_trading_transactions, paper_trading_positions, paper_trading_orders, paper_trading_accounts, migration_checkpoints CASCADE"))
    await db.commit()

@pytest.mark.asyncio
async def test_postgres_decimal_18_8_precision(db: AsyncSession):
    """
    Verify PostgreSQL retains exact Decimal(18,8) precision without floating point drift.
    """
    # Insert order with highly precise numbers
    qty = Decimal("12345.67890123")
    price = Decimal("0.00000001")
    
    await db.execute(
        text("""
            INSERT INTO paper_trading_accounts (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
            VALUES (1, 'Precision Test', 'USD', 1000.0, 1000.0, 0.02, NOW(), NOW())
        """)
    )
    
    await db.execute(
        text("""
            INSERT INTO paper_trading_orders 
            (id, account_id, symbol, side, order_type, qty, order_price, status, idempotency_key, created_at, updated_at, lifecycle_state, product_type)
            VALUES (101, 1, 'BTC-USD', 'BUY', 'LIMIT', :q, :p, 'PENDING', 'test-precision-1', NOW(), NOW(), 'PENDING_ENTRY', 'CNC')
        """),
        {"q": qty, "p": price}
    )
    
    # Retrieve
    res = await db.execute(text("SELECT qty, order_price FROM paper_trading_orders WHERE id = 101"))
    row = res.fetchone()
    
    assert isinstance(row[0], Decimal)
    assert isinstance(row[1], Decimal)
    assert row[0] == qty
    assert row[1] == price

@pytest.mark.asyncio
async def test_postgres_decimal_18_2_financial_sums(db: AsyncSession):
    """
    Verify PostgreSQL retains Decimal(18,2) precision for balances and computes sums natively without drift.
    """
    # Insert multiple accounts with balances
    await db.execute(
        text("""
            INSERT INTO paper_trading_accounts (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
            VALUES 
            (201, 'Acct 1', 'USD', 100.01, 100.01, 0.02, NOW(), NOW()),
            (202, 'Acct 2', 'USD', 200.02, 200.02, 0.02, NOW(), NOW()),
            (203, 'Acct 3', 'USD', 300.03, 300.03, 0.02, NOW(), NOW())
        """)
    )
    
    # Sum natively in PG
    res = await db.execute(text("SELECT SUM(cash_balance) FROM paper_trading_accounts WHERE id IN (201, 202, 203)"))
    total = res.scalar()
    
    assert isinstance(total, Decimal)
    assert total == Decimal("600.06")
