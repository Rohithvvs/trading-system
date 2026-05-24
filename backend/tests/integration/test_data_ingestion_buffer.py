import pytest
import time
from backend.app.services.market_engine_service import market_engine

def test_data_ingestion_throughput():
    """
    Assert that the incoming market engine processes ticks smoothly 
    without a buildup backlog or blocking event loops.
    """
    # Simulate a burst of 100 fast ticks for a mock symbol
    start_time = time.perf_counter()
    
    ticks_to_process = 100
    for i in range(ticks_to_process):
        # We call _on_tick directly to bypass the network/websocket layer
        # and test the engine's ingestion speed and DB blocking time.
        market_engine._on_tick("RELIANCE", 2500.0 + i)
        
    end_time = time.perf_counter()
    elapsed = end_time - start_time
    
    # 100 ticks should process reasonably fast.
    # We use 25.0s because SQLite fsync can take ~150ms per commit on Windows.
    assert elapsed < 25.0, f"Ingestion too slow: {elapsed}s for {ticks_to_process} ticks"
    
    # Verify the latest state
    assert market_engine.latest_ltp["RELIANCE"] == 2500.0 + ticks_to_process - 1
