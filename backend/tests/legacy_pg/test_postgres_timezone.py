import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.fixture(autouse=True)
async def cleanup_timezone(db: AsyncSession):
    await db.execute(text("TRUNCATE paper_trading_trade_history, paper_trading_transactions, paper_trading_positions, paper_trading_orders, paper_trading_accounts, migration_checkpoints CASCADE"))
    await db.commit()

@pytest.mark.asyncio
async def test_postgres_timezone_utc_normalization(db: AsyncSession):
    """
    Verify PostgreSQL normalizes non-UTC timezone-aware datetimes to UTC.
    """
    # Create a datetime in EST (UTC-5)
    est = timezone(timedelta(hours=-5))
    dt_est = datetime(2026, 5, 29, 12, 0, 0, tzinfo=est)
    
    await db.execute(
        text("""
            INSERT INTO paper_trading_accounts 
            (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
            VALUES (301, 'TZ Test', 'USD', 100.0, 100.0, 0.02, :created, :updated)
        """),
        {"created": dt_est, "updated": dt_est}
    )
    
    # Retrieve it natively
    res = await db.execute(text("SELECT created_at FROM paper_trading_accounts WHERE id = 301"))
    row = res.fetchone()
    
    dt_db: datetime = row[0]
    
    # Verify it is timezone-aware and matches the equivalent UTC time (17:00:00)
    assert dt_db.tzinfo is not None
    assert dt_db == dt_est
    assert dt_db.astimezone(timezone.utc).hour == 17

@pytest.mark.asyncio
async def test_postgres_timezone_roundtrip_serialization(db: AsyncSession):
    """
    Verify Python datetime.now(timezone.utc) round-trips exactly to PostgreSQL without precision loss.
    """
    dt_utc = datetime.now(timezone.utc)
    
    await db.execute(
        text("""
            INSERT INTO paper_trading_accounts 
            (id, name, base_currency, starting_balance, cash_balance, max_risk_per_trade, created_at, updated_at)
            VALUES (302, 'TZ Roundtrip', 'USD', 100.0, 100.0, 0.02, :dt, :dt)
        """),
        {"dt": dt_utc}
    )
    
    res = await db.execute(text("SELECT created_at FROM paper_trading_accounts WHERE id = 302"))
    dt_db = res.scalar()
    
    # asyncpg natively retains microseconds if they fit in 64-bit float/int
    assert dt_db == dt_utc
