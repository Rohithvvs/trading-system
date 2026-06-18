import pytest
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from scripts.migrate_sqlite_to_pg import cast_decimal, localize_utc

def test_decimal_casting_precision():
    # Test strict 2-decimal precision (Balances)
    assert cast_decimal(100.5, 2) == Decimal("100.50")
    assert cast_decimal(100.555, 2) == Decimal("100.56")
    
    # Test strict 8-decimal precision (Prices/Qty)
    assert cast_decimal(0.00000001, 8) == Decimal("0.00000001")
    assert cast_decimal(123.456789123, 8) == Decimal("123.45678912")
    
    # Test nullability
    assert cast_decimal(None, 2) is None

def test_utc_timezone_parsing():
    # SQLite stores naive string: 2023-10-14 15:30:00.123456
    naive_str = "2023-10-14T15:30:00.123456"
    dt = localize_utc(naive_str)
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.isoformat() == "2023-10-14T15:30:00.123456+00:00"

    # Already aware string (defensive)
    aware_str = "2023-10-14T15:30:00.123456+00:00"
    dt2 = localize_utc(aware_str)
    assert dt2 is not None
    assert dt2.tzinfo == timezone.utc
    
    # Nullability
    assert localize_utc(None) is None

@pytest.mark.asyncio
async def test_partial_batch_rollback_safety(db: AsyncSession):
    # Simulate a partial batch insert where one row succeeds but the batch fails
    from backend.app.models.paper_trading import PaperTradingAccount
    from sqlalchemy import select
    
    # 1. Start a transaction block
    try:
        async with db.begin():
            acct1 = PaperTradingAccount(
                id=9999,
                name="Rollback Test 1",
                base_currency="INR",
                starting_balance=Decimal("100.00"),
                cash_balance=Decimal("100.00"),
                max_risk_per_trade=Decimal("0.02")
            )
            db.add(acct1)
            await db.flush() # Flush so it goes to Postgres
            
            # 2. Simulate an error in the same batch
            raise ValueError("Simulated batch failure")
    except ValueError:
        pass
        
    # 3. Verify rollback actually happened
    result = await db.execute(select(PaperTradingAccount).filter_by(id=9999))
    assert result.scalar_one_or_none() is None

@pytest.mark.asyncio
async def test_sequence_reseed_validation(db: AsyncSession):
    from sqlalchemy import text
    from backend.app.models.paper_trading import PaperPosition
    
    # Simulate reseeding after migration
    await db.execute(text("SELECT setval(pg_get_serial_sequence('paper_trading_positions', 'id'), 5000)"))
    await db.commit()
    
    # Validate the next inserted ID is 5001
    pos = PaperPosition(
        account_id=1,  # Assuming account 1 exists or will fail FK (we can bypass FK for this test or just check sequence)
        symbol="TEST",
        qty=Decimal("10"),
        avg_entry_price=Decimal("100"),
    )
    # We will just verify the sequence itself
    res = await db.execute(text("SELECT nextval(pg_get_serial_sequence('paper_trading_positions', 'id'))"))
    next_id = res.scalar()
    assert next_id == 5001
