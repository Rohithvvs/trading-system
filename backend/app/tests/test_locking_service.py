import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from backend.app.services.lock_service import DistributedLockService, LockAcquisitionError
from backend.app.models.market_data import Base, SystemLock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os

test_db_path = os.path.join(tempfile.gettempdir(), "test_locks.db")
if os.path.exists(test_db_path):
    os.remove(test_db_path)

engine = create_engine(
    f"sqlite:///{test_db_path}", connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from alembic.config import Config
from alembic import command
from backend.app.config import settings
from backend.app.config.settings import ROOT_DIR
alembic_cfg = Config(str(ROOT_DIR / "backend" / "alembic.ini"))
alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{test_db_path}")
command.upgrade(alembic_cfg, "head")

@pytest.fixture(autouse=True)
def setup_db():
    with patch("app.services.lock_service.SessionLocal", new=TestingSessionLocal):
        yield
        # Cleanup locks between tests
        with TestingSessionLocal() as db:
            db.query(SystemLock).delete()
            db.commit()

@pytest.mark.asyncio
async def test_acquire_and_release():
    lock = DistributedLockService("test_lock", ttl_seconds=10)
    
    # Context manager acquire
    async with lock as acquired_lock:
        assert lock._is_locked is True
        assert lock._heartbeat_task is not None
        
        # Verify in DB
        with TestingSessionLocal() as db:
            db_lock = db.query(SystemLock).filter_by(lock_name="test_lock").first()
            assert db_lock is not None
            assert db_lock.locked_by == lock.worker_id

    # Exited context, should be released
    assert lock._is_locked is False
    assert lock._heartbeat_task is None
    with TestingSessionLocal() as db:
        db_lock = db.query(SystemLock).filter_by(lock_name="test_lock").first()
        assert db_lock is None

@pytest.mark.asyncio
async def test_mutual_exclusion():
    lock1 = DistributedLockService("shared_lock", ttl_seconds=10)
    lock1.worker_id = "worker-1"
    
    lock2 = DistributedLockService("shared_lock", ttl_seconds=10)
    lock2.worker_id = "worker-2"
    
    async with lock1:
        # Lock2 should fail to acquire since Lock1 holds it
        acquired = await asyncio.to_thread(lock2.acquire, timeout_seconds=1, retry_delay=0.1)
        assert acquired is False

@pytest.mark.asyncio
async def test_stale_lock_recovery():
    # Insert a stale lock artificially
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_time = now - timedelta(seconds=20)
    
    with TestingSessionLocal() as db:
        stale_lock = SystemLock(
            lock_name="stale_lock",
            locked_by="dead_worker",
            locked_at=stale_time,
            expires_at=stale_time,
            heartbeat_at=stale_time
        )
        db.add(stale_lock)
        db.commit()
        
    lock = DistributedLockService("stale_lock", ttl_seconds=10)
    lock.worker_id = "new_worker"
    
    # Should successfully steal the stale lock immediately
    acquired = await asyncio.to_thread(lock.acquire, timeout_seconds=1)
    assert acquired is True
    
    with TestingSessionLocal() as db:
        db_lock = db.query(SystemLock).filter_by(lock_name="stale_lock").first()
        assert db_lock.locked_by == "new_worker"
        
    lock.release()
