import pytest
import asyncio
import os
import uuid
import tempfile
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from app.models.paper_trading import PaperTradingAccount, PaperOrder
from app.services.paper_trading_service import PaperTradingService
from app.schemas.paper_trading import PaperOrderCreateRequest
from app.config.settings import settings, Settings
from unittest.mock import patch, PropertyMock

@pytest.fixture(scope="function")
def isolated_db():
    db_fd, db_path = tempfile.mkstemp(suffix=f"_{uuid.uuid4().hex[:8]}.db")
    os.close(db_fd)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 15})
    
    from app.db.session import init_db
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
def test_order_idempotency_db_crash_recovery(isolated_db):
    TestingSessionLocal, engine = isolated_db
    
    request = PaperOrderCreateRequest(
        symbol="NSE:TCS-EQ",
        side="BUY",
        order_type="LIMIT",
        product_type="CNC",
        qty=10,
        price=3000.0,
        idempotency_key="crash-recovery-key-12345"
    )
    
    # Simulate first attempt crashing AT flush (before commit)
    with TestingSessionLocal() as db:
        svc = PaperTradingService(db)
        
        # Mock fetch LTP
        original_flush = db.flush
        def crashing_flush(*args, **kwargs):
            raise OperationalError("database is locked", params=None, orig=None)
            
        with patch("app.config.settings.Settings.nifty500_symbols", new_callable=PropertyMock) as mock_nifty:
            mock_nifty.return_value = ["NSE:TCS-EQ"]
            with patch.object(svc.fyers_service, "fetch_ltp", return_value=3005.0):
                with patch.object(db, "flush", side_effect=crashing_flush):
                    with pytest.raises(OperationalError):
                        svc.place_order(request)
            
            # Since flush failed, the db state rolls back (or we manually rollback in the route)
            db.rollback()
            
    # Verify DB is clean
    with TestingSessionLocal() as db:
        orders = db.query(PaperOrder).all()
        assert len(orders) == 0

    # 2. Re-attempt the exact same request. It should succeed now.
    with TestingSessionLocal() as db:
        svc = PaperTradingService(db)
        with patch("app.config.settings.Settings.nifty500_symbols", new_callable=PropertyMock) as mock_nifty:
            mock_nifty.return_value = ["NSE:TCS-EQ"]
            with patch.object(svc.fyers_service, "fetch_ltp", return_value=3005.0):
                resp = svc.place_order(request)
            db.commit()
            
            assert resp.order is not None
            
            db_order = db.query(PaperOrder).filter_by(id=resp.order.id).first()
            assert db_order.idempotency_key == "crash-recovery-key-12345"

    # 3. Third attempt. It should hit the idempotency short-circuit and NOT duplicate
    with TestingSessionLocal() as db:
        svc = PaperTradingService(db)
        with patch("app.config.settings.Settings.nifty500_symbols", new_callable=PropertyMock) as mock_nifty:
            mock_nifty.return_value = ["NSE:TCS-EQ"]
            with patch.object(svc.fyers_service, "fetch_ltp", return_value=3005.0):
                resp = svc.place_order(request)
                db.commit()
                
                # Message should indicate idempotent retry
                assert "Idempotent retry" in resp.message
                
                # DB should still only have 1 order
                orders = db.query(PaperOrder).all()
                assert len(orders) == 1
