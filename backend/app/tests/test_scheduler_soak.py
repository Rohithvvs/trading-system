import pytest
import asyncio
import os
import tempfile
import gc
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.market_data import Base, SystemLock, HistoricalCandle
from app.services.lock_service import DistributedLockService, LockAcquisitionError
from app.services.candle_reconciliation_service import CandleReconciliationService

import uuid
test_db_path = os.path.join(tempfile.gettempdir(), f"test_scheduler_soak_{uuid.uuid4().hex}.db")

if os.path.exists(test_db_path):
    os.remove(test_db_path)

engine = create_engine(
    f"sqlite:///{test_db_path}", connect_args={"check_same_thread": False, "timeout": 15}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

@pytest.fixture(autouse=True)
def setup_db():
    with patch("app.services.candle_reconciliation_service.SessionLocal", new=TestingSessionLocal):
        with patch("app.services.lock_service.SessionLocal", new=TestingSessionLocal):
            with patch("app.services.market_data_service.SessionLocal", new=TestingSessionLocal):
                with TestingSessionLocal() as db:
                    db.query(SystemLock).delete()
                    db.commit()
            
                yield
            
            with TestingSessionLocal() as db:
                db.query(SystemLock).delete()
                db.commit()

@pytest.mark.soak
@pytest.mark.asyncio
async def test_scheduler_overlap_contention_and_memory():
    """
    Simulate multiple background scheduler ticks overlapping.
    Validate memory doesn't leak asyncio tasks and lock strictly isolates.
    """
    initial_tasks = len(asyncio.all_tasks())
    barrier = asyncio.Barrier(5)
    successful_acquires = 0
    lock_errors = 0
    
    async def overlapping_scheduler_tick():
        nonlocal successful_acquires, lock_errors
        await barrier.wait()
        
        try:
            # Recreate lock instance to simulate different workers grabbing it
            async with DistributedLockService("reconciliation_job", ttl_seconds=2) as lock:
                successful_acquires += 1
                # Pretend to work
                await asyncio.sleep(0.5)
        except LockAcquisitionError:
            lock_errors += 1

    with patch.object(DistributedLockService, "acquire", autospec=True) as mock_acquire:
        def acquire_fast(self, *args, **kwargs):
            return self._try_acquire()
        mock_acquire.side_effect = acquire_fast

        # Fire 5 ticks instantly
        tasks = [asyncio.create_task(overlapping_scheduler_tick()) for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                raise r
    
    # 1 should succeed, 4 should fail due to lock contention
    assert successful_acquires == 1
    assert lock_errors == 4
    
    # Force garbage collection to clean up closed tasks
    gc.collect()
    
    # Check for memory leaks (task orphaned by lock heartbeats)
    # Give the heartbeat task a moment to fully shut down
    await asyncio.sleep(0.2)
    final_tasks = len(asyncio.all_tasks())
    
    # The heartbeat task should be cancelled and cleaned up.
    # Current tasks should equal initial tasks (just the main test task + pytest overhead).
    assert final_tasks <= initial_tasks + 1

@pytest.mark.soak
@pytest.mark.asyncio
async def test_api_circuit_breaker_recovery():
    """
    Injects simulated API 429 errors 5 times to trip the breaker.
    Verifies that the job immediately aborts until the TTL expires.
    """
    service = CandleReconciliationService()
    
    # Mock the fyers service to crash
    with patch.object(service.fyers_service, "_request_history_with_retries", side_effect=Exception("API Down!")):
        with patch.object(service, "detect_gaps", return_value=[{"symbol": "TCS", "gap_start": "2023-01-04", "gap_end": "2023-01-06", "days_diff": 2}]):
            
            # Hit it 5 times (Max circuit breaker limit is 5)
            for _ in range(5):
                await service.reconciliation_job(["TCS"])
                
            assert service.circuit_breaker_failures == 5
            assert service.circuit_breaker_tripped_until is not None
            
            # 6th time should immediately skip without grabbing the lock or calling API
            with patch.object(service.fyers_service, "_request_history_with_retries") as mock_fetch:
                with patch("app.services.candle_reconciliation_service.logger") as mock_logger:
                    await service.reconciliation_job(["TCS"])
                    
                    mock_fetch.assert_not_called()
                    mock_logger.warning.assert_called()
                    assert mock_logger.warning.call_args[0][0] == "reconciliation_circuit_breaker_active"
