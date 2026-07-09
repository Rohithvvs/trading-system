import pytest
import asyncio
import os
import uuid
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.paper_trading import PaperTradingAccount, PaperOrder, PaperPosition, ExecutionEvent
from app.services.market_engine_service import MarketEngineService
from app.services.paper_trading_service import PaperTradingService

@pytest.fixture(scope="function")
def isolated_db():
    db_fd, db_path = tempfile.mkstemp(suffix=f"_{uuid.uuid4().hex[:8]}.db")
    os.close(db_fd)
    
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 15}
    )
    
    # Initialize schema
    from app.db.session import init_db
    with patch("app.db.session.engine", engine):
        with patch("app.db.session.settings.database_url", f"sqlite:///{db_path}"):
            init_db()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create initial account
    with TestingSessionLocal() as db:
        account = PaperTradingAccount(
            starting_balance=100000.0,
            cash_balance=100000.0,
        )
        db.add(account)
        db.commit()

    yield TestingSessionLocal, engine
    
    # Teardown
    engine.dispose()
    try:
        os.remove(db_path)
    except OSError:
        pass


@pytest.mark.recovery
@pytest.mark.asyncio
async def test_duplicate_tick_idempotency(isolated_db):
    TestingSessionLocal, engine = isolated_db
    
    with patch("app.services.market_engine_service.SessionLocal", TestingSessionLocal):
        engine_svc = MarketEngineService()
        
        # 1. Setup a pending order
        with TestingSessionLocal() as db:
            account = db.query(PaperTradingAccount).first()
            order = PaperOrder(
                account_id=account.id,
                symbol="TCS",
                side="BUY",
                order_type="LIMIT",
                product_type="CNC",
                qty=10,
                order_price=3000.0,
                requested_entry_price=3000.0,
                status="PENDING",
                lifecycle_state="PENDING_ENTRY",
                monitor_enabled=True,
                idempotency_key="tick-test-order"
            )
            db.add(order)
            db.commit()

        # 2. Fire 20 duplicate/jittered ticks concurrently mimicking a replay storm
        # All of these hit the entry price!
        barrier = asyncio.Barrier(20)
        
        async def inject_tick(jitter_price: float):
            await barrier.wait()
            # Engine's tick handler is synchronous, so we run it in thread
            await engine_svc._on_tick("TCS", jitter_price)

        # Generate 20 ticks. Prices jitter between 2999.0 and 2999.9 (all trigger the limit buy)
        tasks = [asyncio.create_task(inject_tick(2999.0 + (i * 0.01))) for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # We expect IntegrityErrors or OperationalErrors due to concurrency locks/unique constraints
        for r in results:
            if isinstance(r, Exception):
                pass # Expected deduplication rejections

        # 3. Assert execution was entirely idempotent
        with TestingSessionLocal() as db:
            account = db.query(PaperTradingAccount).first()
            
            # The balance should have deducted EXACTLY once. 
            # 10 qty * ~2999 = ~29990.
            # Original: 100000. Remaining should be ~70010. NOT negative.
            assert account.cash_balance > 60000.0
            
            # Order should be filled
            order = db.query(PaperOrder).filter_by(symbol="TCS").first()
            assert order.status == "FILLED"
            assert order.lifecycle_state == "ENTRY_FILLED"
            
            # There should be exactly 1 position
            positions = db.query(PaperPosition).filter_by(symbol="TCS").all()
            assert len(positions) == 1
            
            # There should be exactly 1 execution event for entry
            events = db.query(ExecutionEvent).filter_by(symbol="TCS").all()
            assert len(events) == 1
            assert events[0].to_state == "ENTRY_FILLED"


@pytest.mark.recovery
@pytest.mark.asyncio
async def test_reconnect_burst_stoploss(isolated_db):
    TestingSessionLocal, engine = isolated_db
    
    with patch("app.services.market_engine_service.SessionLocal", TestingSessionLocal):
        engine_svc = MarketEngineService()
        
        # 1. Setup an active position with a stop-loss
        with TestingSessionLocal() as db:
            account = db.query(PaperTradingAccount).first()
            pos = PaperPosition(
                account_id=account.id,
                symbol="RELIANCE",
                qty=10,
                avg_entry_price=2500.0,
                stop_loss=2400.0,
                status="OPEN",
                lifecycle_state="OPEN_POSITION",
                monitor_enabled=True
            )
            db.add(pos)
            db.commit()

        # 2. Simulate rapid websocket reconnect replays that all breach the stop-loss
        # Re-ordered and jittered timestamps
        barrier = asyncio.Barrier(10)
        
        async def inject_reconnect_tick(price: float):
            await barrier.wait()
            await engine_svc._on_tick("RELIANCE", price)

        # Burst of 10 ticks breaching the stoploss (2399, 2398, etc)
        tasks = [asyncio.create_task(inject_reconnect_tick(2399.0 - (i * 0.1))) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. Assert exactly 1 exit
        with TestingSessionLocal() as db:
            pos = db.query(PaperPosition).filter_by(symbol="RELIANCE").first()
            assert pos is None
            
            # Only 1 exit event
            events = db.query(ExecutionEvent).filter_by(symbol="RELIANCE").all()
            assert len(events) == 1
            assert events[0].to_state == "EXIT_FILLED"
