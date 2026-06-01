import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.services.candle_reconciliation_service import CandleReconciliationService

@pytest.mark.asyncio
async def test_empty_gap_cache_unlogged_persistence():
    # Insert a fake empty gap directly or via service
    async with AsyncSessionLocal() as db:
        await db.execute(text("TRUNCATE TABLE market_data.empty_gaps"))
        await db.commit()
        
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        await db.execute(
            text("""
                INSERT INTO market_data.empty_gaps (symbol, gap_date, expires_at)
                VALUES ('TEST', '2026-01-01', :ea)
            """),
            {"ea": expires_at}
        )
        await db.commit()
        
        res = await db.execute(text("SELECT COUNT(*) FROM market_data.empty_gaps"))
        count = res.scalar()
        assert count == 1
        
        # Test cleanup
        await db.execute(text("UPDATE market_data.empty_gaps SET expires_at = NOW() - INTERVAL '1 day'"))
        await db.commit()
        
        # Call cleanup
        await db.execute(text("DELETE FROM market_data.empty_gaps WHERE expires_at < NOW()"))
        await db.commit()
        
        res2 = await db.execute(text("SELECT COUNT(*) FROM market_data.empty_gaps"))
        count2 = res2.scalar()
        assert count2 == 0
