import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from backend.app.db.session import SessionLocal
from backend.app.models.paper_trading import PaperTradingAccount, PaperPosition, PaperOrder
from backend.app.services.market_engine_service import MarketEngineService

@pytest.fixture
def mock_fyers():
    with patch("backend.app.services.market_engine_service.FyersService") as mock_class:
        mock_instance = mock_class.return_value
        mock_instance.fetch_ltp.return_value = 105.0
        yield mock_instance

def test_warm_boot_recovery(mock_fyers):
    """
    Seed the database with an active open position (target + trailing stop-loss).
    Simulate a backend restart by reinstantiating the market_engine.
    Assert it immediately detects the pre-existing trade and resumes tracking.
    """
    with SessionLocal() as db:
        # Clear existing
        db.query(PaperPosition).delete()
        db.query(PaperOrder).delete()
        db.commit()

        account = db.query(PaperTradingAccount).first()
        if not account:
            account = PaperTradingAccount(cash_balance=100000.0)
            db.add(account)
            db.commit()
            db.refresh(account)

        # Seed an active position simulating a closed market or sudden shutdown
        pos = PaperPosition(
            account_id=account.id,
            symbol="HDFCBANK",
            qty=10,
            avg_entry_price=100.0,
            status="OPEN",
            lifecycle_state="MARKET_CLOSED_WAITING",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(pos)
        
        # Seed an associated pending trailing stop order
        order = PaperOrder(
            account_id=account.id,
            symbol="HDFCBANK",
            side="SELL",
            qty=10,
            order_type="STOP_LOSS",
            status="PENDING",
            lifecycle_state="MARKET_CLOSED_WAITING",
            stop_price=95.0,
            created_at=datetime.utcnow()
        )
        db.add(order)
        db.commit()

    # Reinstantiate market_engine to simulate backend restart
    test_engine = MarketEngineService()
    
    with SessionLocal() as db:
        # Simulate the warm boot loop reconcile
        test_engine._resume_active_models(db)
        db.commit()

        # Assert it immediately detects the pre-existing trade and resumes tracking
        resumed_pos = db.query(PaperPosition).filter_by(symbol="HDFCBANK").first()
        assert resumed_pos is not None
        assert resumed_pos.status == "OPEN"
        assert resumed_pos.lifecycle_state == "OPEN_POSITION" # Resumed!

        resumed_order = db.query(PaperOrder).filter_by(symbol="HDFCBANK").first()
        assert resumed_order is not None
        assert resumed_order.status == "PENDING"
        assert resumed_order.lifecycle_state == "PENDING_ENTRY" # Resumed tracking!
