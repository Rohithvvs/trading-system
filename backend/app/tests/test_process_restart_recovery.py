import pytest
import asyncio
import os
import uuid
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.models.paper_trading import PaperTradingAccount, PaperOrder, PaperPosition, MarketEngineSession
from backend.app.models.market_data import SystemLock
from backend.app.services.market_engine_service import MarketEngineService
from backend.app.services.lock_service import DistributedLockService

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
    
    with TestingSessionLocal() as db:
        account = PaperTradingAccount(starting_balance=100000.0, cash_balance=100000.0)
        db.add(account)
        db.commit()

    yield TestingSessionLocal, engine
    
    engine.dispose()
    try:
        os.remove(db_path)
    except OSError:
        pass


@pytest.mark.recovery
@pytest.mark.asyncio
async def test_stale_lock_steal_and_heartbeat_leak(isolated_db):
    TestingSessionLocal, engine = isolated_db
    
    initial_tasks = len(asyncio.all_tasks())
    
    # 1. Simulate a worker that acquired the lock but crashed (left a row in DB)
    with TestingSessionLocal() as db:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stale_lock = SystemLock(
            lock_name="reconciliation_job",
            locked_by="crashed_worker-1234",
            locked_at=now - timedelta(minutes=5),
            expires_at=now - timedelta(minutes=4),  # Expired 4 mins ago!
            heartbeat_at=now - timedelta(minutes=5)
        )
        db.add(stale_lock)
        db.commit()

    # 2. Start a new worker
    with patch("app.services.lock_service.SessionLocal", TestingSessionLocal):
        lock_svc = DistributedLockService("reconciliation_job", ttl_seconds=2)
        acquired = await asyncio.to_thread(lock_svc.acquire, timeout_seconds=2)
        assert acquired is True
        lock_svc.start_heartbeat()
        
        # Verify it successfully stole the lock
        with TestingSessionLocal() as db:
            current_lock = db.scalar(select(SystemLock).where(SystemLock.lock_name == "reconciliation_job"))
            assert current_lock is not None
            assert current_lock.locked_by == lock_svc.worker_id
            
        # Verify heartbeat task is running
        assert lock_svc._heartbeat_task is not None
        assert not lock_svc._heartbeat_task.done()
        
        # 3. Simulate releasing the lock (graceful shutdown)
        await asyncio.to_thread(lock_svc.release)
        
        # Verify lock is removed
        with TestingSessionLocal() as db:
            current_lock = db.scalar(select(SystemLock).where(SystemLock.lock_name == "reconciliation_job"))
            assert current_lock is None

        # Give asyncio loop a moment to clean up cancelled task
        await asyncio.sleep(0.1)
        
        # 4. Verify no heartbeat tasks leaked
        final_tasks = len(asyncio.all_tasks())
        assert final_tasks <= initial_tasks + 1  # allowing 1 for current test wrapper variance


@pytest.mark.recovery
@pytest.mark.asyncio
async def test_engine_startup_reconciliation(isolated_db):
    TestingSessionLocal, engine = isolated_db
    
    with patch("app.services.market_engine_service.SessionLocal", TestingSessionLocal):
        
        # 1. Simulate a crash state where orders/positions were ERROR_RETRYING
        with TestingSessionLocal() as db:
            account = db.query(PaperTradingAccount).first()
            # Order stranded in ERROR_RETRYING
            order = PaperOrder(
                account_id=account.id,
                symbol="RELIANCE",
                side="BUY",
                order_type="LIMIT",
                product_type="CNC",
                qty=10,
                order_price=2500.0,
                status="PENDING",
                lifecycle_state="ERROR_RETRYING",
                monitor_enabled=True,
                paused_reason="WEBSOCKET_DISCONNECTED"
            )
            # Position stranded in MARKET_CLOSED_WAITING (from Friday crash)
            pos = PaperPosition(
                account_id=account.id,
                symbol="TCS",
                qty=10,
                avg_entry_price=2500.0,
                status="OPEN",
                lifecycle_state="MARKET_CLOSED_WAITING",
                monitor_enabled=True
            )
            # Session stranded
            sess = MarketEngineSession(
                trading_date=datetime.now().date().isoformat(),
                status="ERROR_RETRYING",
                websocket_connected=False
            )
            db.add_all([order, pos, sess])
            db.commit()

        # 2. Restart engine
        engine_svc = MarketEngineService()
        
        # Mock fetch_ltp and market hours so it proceeds with reconcile
        with patch.object(engine_svc.fyers, "fetch_ltp", return_value=2505.0):
            with patch.object(engine_svc, "is_market_hours", return_value=True):
                # Trigger a single loop run
                with TestingSessionLocal() as db:
                    sess = engine_svc._get_or_create_session(db)
                    await engine_svc._reconcile_session(db, sess)
                    db.commit()

        # 3. Assert states are fully recovered
        with TestingSessionLocal() as db:
            sess = db.query(MarketEngineSession).first()
            assert sess.status == "RUNNING"
            assert sess.websocket_connected is False # We didn't start the feed task, but status is RUNNING
            
            order = db.query(PaperOrder).first()
            assert order.lifecycle_state == "PENDING_ENTRY"
            assert order.paused_reason is None
            
            pos = db.query(PaperPosition).first()
            assert pos.lifecycle_state == "OPEN_POSITION"
            assert pos.paused_reason is None
