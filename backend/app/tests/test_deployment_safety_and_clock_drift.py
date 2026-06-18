import pytest
import asyncio
import os
import uuid
import time
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.lock_service import DistributedLockService, LockAcquisitionError
from backend.app.models.market_data import SystemLock

@pytest.fixture(scope="function")
def isolated_db():
    db_fd, db_path = tempfile.mkstemp(suffix=f"_{uuid.uuid4().hex[:8]}.db")
    os.close(db_fd)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 15})
    
    from backend.app.db.session import init_db
    with patch("app.db.session.engine", engine):
        with patch("app.db.session.settings.database_url", f"sqlite:///{db_path}"):
            init_db()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield TestingSessionLocal, engine
    
    engine.dispose()
    try:
        os.remove(db_path)
    except OSError:
        pass


@pytest.mark.recovery
@pytest.mark.asyncio
async def test_rolling_deployment_overlap(isolated_db):
    TestingSessionLocal, engine = isolated_db
    
    with patch("app.services.lock_service.SessionLocal", TestingSessionLocal):
        # Two workers trying to acquire simultaneously
        lock1 = DistributedLockService("deploy_job", ttl_seconds=2)
        lock2 = DistributedLockService("deploy_job", ttl_seconds=2)
        
        # Override the acquire timeout so they don't block
        with patch.object(DistributedLockService, "acquire", autospec=True) as mock_acquire:
            def acquire_fast(self, *args, **kwargs):
                return self._try_acquire()
            mock_acquire.side_effect = acquire_fast
            
            barrier = asyncio.Barrier(2)
            
            async def worker_1():
                await barrier.wait()
                try:
                    async with lock1:
                        await asyncio.sleep(0.5)
                        return True
                except LockAcquisitionError:
                    return False
                    
            async def worker_2():
                await barrier.wait()
                try:
                    async with lock2:
                        await asyncio.sleep(0.5)
                        return True
                except LockAcquisitionError:
                    return False

            tasks = [asyncio.create_task(worker_1()), asyncio.create_task(worker_2())]
            results = await asyncio.gather(*tasks)
            
            # Exactly 1 True, 1 False
            assert results.count(True) == 1
            assert results.count(False) == 1


@pytest.mark.recovery
@pytest.mark.asyncio
async def test_clock_drift_and_heartbeat_delay(isolated_db):
    TestingSessionLocal, engine = isolated_db
    
    with patch("app.services.lock_service.SessionLocal", TestingSessionLocal):
        # 1. Worker 1 acquires lock
        lock1 = DistributedLockService("skew_job", ttl_seconds=2)
        
        # Mock the heartbeat loop to fail/delay
        original_heartbeat = lock1.heartbeat
        
        # We start the lock manually to control the timeline
        acquired = await asyncio.to_thread(lock1.acquire, timeout_seconds=2)
        assert acquired is True
        
        # Worker 1 gets heavily CPU bound / blocked and misses heartbeat entirely
        # We fast forward time by modifying the DB to simulate clock drift
        with TestingSessionLocal() as db:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            lock_row = db.query(SystemLock).filter_by(lock_name="skew_job").first()
            
            # Simulate Worker 1's clock is running SLOW compared to DB
            # DB says it expired 5 seconds ago
            lock_row.expires_at = now - timedelta(seconds=5)
            lock_row.heartbeat_at = now - timedelta(seconds=10)
            db.commit()

        # 2. Worker 2 comes online, with correct clock
        lock2 = DistributedLockService("skew_job", ttl_seconds=2)
        
        # It should successfully steal the lock
        acquired2 = await asyncio.to_thread(lock2.acquire, timeout_seconds=2)
        assert acquired2 is True
        
        # 3. Worker 1 wakes up and tries to heartbeat (late!)
        lock1.heartbeat() # This should silently fail because it no longer owns the lock
        
        with TestingSessionLocal() as db:
            lock_row = db.query(SystemLock).filter_by(lock_name="skew_job").first()
            assert lock_row.locked_by == lock2.worker_id
            
        await asyncio.to_thread(lock1.release) # Should gracefully do nothing
        await asyncio.to_thread(lock2.release) # Should release properly
