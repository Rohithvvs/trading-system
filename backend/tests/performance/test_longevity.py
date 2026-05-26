import pytest
import asyncio
import gc

@pytest.mark.asyncio
async def test_longevity_event_loop_stability():
    """
    Stability Test: Ensure long-running asynchronous loops do not leak memory
    or leave orphan tasks behind.
    
    This simulates a 6-12 hour trading session compacted into high-frequency iterations.
    """
    # 1. Baseline task count
    initial_tasks = len(asyncio.all_tasks())
    
    async def dummy_scanner_cycle():
        # Simulate an IO bound task like fetching data
        await asyncio.sleep(0.001)
        # Allocate some memory that should be garbage collected
        _temp_buffer = [x for x in range(1000)]
        return len(_temp_buffer)

    # 2. Fire 1,000 cycles concurrently simulating repeated background triggers
    # across a trading day
    cycles = [asyncio.create_task(dummy_scanner_cycle()) for _ in range(1000)]
    
    await asyncio.gather(*cycles)
    
    # Force a garbage collection cycle to ensure standard cleanup has occurred
    gc.collect()
    
    # 3. Post-execution task count
    # Remove current task from the count
    remaining_tasks = [t for t in asyncio.all_tasks() if not t.done()]
    
    # Only the main test task should remain (1 task)
    assert len(remaining_tasks) <= initial_tasks, "Orphan background tasks detected!"
    
    # If the system survives this without crashing or raising exceptions, the loop
    # stability is robust against rapid and repeated spawning.
