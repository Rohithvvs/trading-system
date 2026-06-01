import pytest
from app.db.scan_store import save_latest_scan, load_latest_scan, get_last_scan_time

@pytest.mark.asyncio
async def test_scan_cache_atomic_upsert():
    payload1 = {"items": [{"symbol": "RELIANCE", "matched": True}], "metadata": "run1"}
    await save_latest_scan(payload1)
    
    data1 = await load_latest_scan()
    assert data1 is not None
    assert data1["metadata"] == "run1"
    
    time1 = await get_last_scan_time()
    assert time1 is not None
    
    payload2 = {"items": [{"symbol": "TCS", "matched": True}], "metadata": "run2"}
    await save_latest_scan(payload2)
    
    data2 = await load_latest_scan()
    assert data2["metadata"] == "run2"
    assert data2["items"][0]["symbol"] == "TCS"
    
    time2 = await get_last_scan_time()
    assert time2 >= time1
