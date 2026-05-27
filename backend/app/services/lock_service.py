import time
import os
import socket
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update, insert, delete
from sqlalchemy.exc import IntegrityError
from ..db.session import SessionLocal
from ..models.market_data import SystemLock
from ..utils import get_logger

logger = get_logger("app.lock_service")

class LockAcquisitionError(Exception):
    pass

class DistributedLockService:
    def __init__(self, lock_name: str, ttl_seconds: int = 3600):
        self.lock_name = lock_name
        self.ttl_seconds = ttl_seconds
        import uuid
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._heartbeat_task = None
        self._is_locked = False

    def acquire(self, timeout_seconds: int = 60, retry_delay: float = 1.0) -> bool:
        """
        Attempts to acquire the lock. Waits up to `timeout_seconds`.
        """
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout_seconds:
            if self._try_acquire():
                self._is_locked = True
                logger.info("lock_acquired", extra={"lock_name": self.lock_name, "worker_id": self.worker_id})
                return True
            time.sleep(retry_delay)
            
        logger.warning("lock_timeout", extra={"lock_name": self.lock_name, "timeout_seconds": timeout_seconds})
        return False

    def _try_acquire(self) -> bool:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = now + timedelta(seconds=self.ttl_seconds)

        with SessionLocal() as db:
            # First, try to insert if not exists
            try:
                stmt = insert(SystemLock).values(
                    lock_name=self.lock_name,
                    locked_by=self.worker_id,
                    locked_at=now,
                    expires_at=expires_at,
                    heartbeat_at=now
                )
                db.execute(stmt)
                db.commit()
                return True
            except IntegrityError:
                db.rollback()
                pass  # Lock row exists

            # Try to update if existing lock is stale
            # A lock is considered stale if BOTH expires_at AND heartbeat_at have lapsed
            # Heartbeat is expected every ttl/2. If no heartbeat in ttl, it's dead.
            stmt = select(SystemLock).where(SystemLock.lock_name == self.lock_name)
            existing = db.execute(stmt).scalar_one_or_none()
            
            if existing:
                if existing.locked_by == self.worker_id:
                    # We already own it, just extend
                    self.heartbeat()
                    return True
                    
                # Check for stale lock
                stale_threshold = now - timedelta(seconds=self.ttl_seconds)
                if existing.expires_at < now and existing.heartbeat_at < stale_threshold:
                    logger.warning("stale_lock_detected", extra={
                        "lock_name": self.lock_name,
                        "old_owner": existing.locked_by,
                        "expires_at": existing.expires_at.isoformat()
                    })
                    
                    # Atomic steal: UPDATE where locked_by = existing.locked_by
                    update_stmt = update(SystemLock).where(
                        SystemLock.lock_name == self.lock_name,
                        SystemLock.locked_by == existing.locked_by
                    ).values(
                        locked_by=self.worker_id,
                        locked_at=now,
                        expires_at=expires_at,
                        heartbeat_at=now
                    )
                    res = db.execute(update_stmt)
                    db.commit()
                    if res.rowcount > 0:
                        logger.info("stale_lock_recovered", extra={"lock_name": self.lock_name, "new_owner": self.worker_id})
                        return True
            return False

    def release(self):
        if not self._is_locked:
            return
        self.stop_heartbeat()
        with SessionLocal() as db:
            stmt = delete(SystemLock).where(
                SystemLock.lock_name == self.lock_name,
                SystemLock.locked_by == self.worker_id
            )
            db.execute(stmt)
            db.commit()
        self._is_locked = False
        logger.info("lock_released", extra={"lock_name": self.lock_name, "worker_id": self.worker_id})

    def heartbeat(self):
        """Refresh the lock expiration and heartbeat timestamp."""
        if not self._is_locked:
            return
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = now + timedelta(seconds=self.ttl_seconds)
        with SessionLocal() as db:
            stmt = update(SystemLock).where(
                SystemLock.lock_name == self.lock_name,
                SystemLock.locked_by == self.worker_id
            ).values(
                expires_at=expires_at,
                heartbeat_at=now
            )
            db.execute(stmt)
            db.commit()
            
    async def _heartbeat_loop(self):
        sleep_interval = self.ttl_seconds / 3.0
        while self._is_locked:
            await asyncio.sleep(sleep_interval)
            try:
                # We offload to thread because heartbeat uses sync SQLAlchemy
                await asyncio.to_thread(self.heartbeat)
                logger.debug("lock_heartbeat", extra={"lock_name": self.lock_name})
            except Exception as e:
                logger.error("Heartbeat failed", extra={"error": str(e)})

    def start_heartbeat(self):
        if self._is_locked and self._heartbeat_task is None:
            # We must be running in an event loop
            try:
                loop = asyncio.get_running_loop()
                self._heartbeat_task = loop.create_task(self._heartbeat_loop())
            except RuntimeError:
                logger.warning("No running event loop to start heartbeat for lock")

    def stop_heartbeat(self):
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def __aenter__(self):
        # Async context manager to avoid blocking event loop
        acquired = await asyncio.to_thread(self.acquire)
        if not acquired:
            raise LockAcquisitionError(f"Failed to acquire lock {self.lock_name}")
        self.start_heartbeat()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await asyncio.to_thread(self.release)
