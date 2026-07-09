import pytest
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.services.candle_store import store_candles, load_candles, get_candle_count
import pandas as pd
from datetime import datetime, timezone
from app.services.partition_manager import verify_and_create_partitions

@pytest.mark.asyncio
async def test_candle_cache_consolidation():
    await verify_and_create_partitions()
    # Store some candles
    data = [
        {"date": "2026-05-01", "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1000},
        {"date": "2026-05-02", "open": 102.0, "high": 108.0, "low": 100.0, "close": 107.0, "volume": 1500},
    ]
    df = pd.DataFrame(data)
    
    symbol = "TESTCACHE"
    await store_candles(symbol, df, "1D")
    
    count = await get_candle_count(symbol, "1D")
    assert count == 2
    
    loaded_df = await load_candles(symbol, resolution="1D")
    assert not loaded_df.empty
    assert len(loaded_df) == 2
    
    # Test ON CONFLICT DO UPDATE
    data_update = [
        {"date": "2026-05-01", "open": 100.0, "high": 110.0, "low": 95.0, "close": 108.0, "volume": 2000},
    ]
    df_update = pd.DataFrame(data_update)
    await store_candles(symbol, df_update, "1D")
    
    count_after = await get_candle_count(symbol, "1D")
    assert count_after == 2  # Should not increase
    
    loaded_df_after = await load_candles(symbol, resolution="1D")
    updated_row = loaded_df_after[loaded_df_after["date"] == "2026-05-01"].iloc[0]
    assert updated_row["high"] == 110.0
    assert updated_row["close"] == 108.0
    
    # Cleanup
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM market_data.candles WHERE symbol = 'TESTCACHE'"))
        await db.commit()
