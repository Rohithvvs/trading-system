import pytest
from sqlalchemy import text
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.partition_manager import verify_and_create_partitions

@pytest.mark.asyncio
async def test_partition_auto_creation():
    # Execute the manager
    await verify_and_create_partitions()
    
    # Verify tables exist
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='market_data'")
        )
        tables = [row[0] for row in res.fetchall()]
        
    assert "candles_1d" in tables or any(t.startswith("candles_1d_y") for t in tables)
    assert any(t.startswith("candles_15m_y") for t in tables)
    assert any(t.startswith("candles_1m_y") for t in tables)
