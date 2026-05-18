from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.models.paper_trading import PaperNotification, PaperOrder, PaperPosition
from backend.app.services.market_engine_service import MarketEngineService
from backend.app.services.paper_trading_service import PaperTradingService
import backend.app.services.paper_trading_service as paper_service
from tests.utils.fakes import FakeFyersService


@pytest.mark.integration
def test_pending_limit_buy_auto_fills_and_target_auto_exits(db_session, monkeypatch):
    monkeypatch.setattr(paper_service, "FyersService", FakeFyersService)
    service = PaperTradingService(db_session)
    account = service._get_or_create_account()

    order = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="BUY",
        order_type="LIMIT",
        product_type="CNC",
        qty=2,
        order_price=95.0,
        requested_entry_price=95.0,
        stop_loss=90.0,
        target=105.0,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY",
    )
    db_session.add(order)
    db_session.commit()

    engine = MarketEngineService()
    engine._process_symbol(db_session, "INFY-EQ", 95.0)
    db_session.commit()

    db_session.refresh(order)
    position = db_session.query(PaperPosition).filter_by(symbol="INFY-EQ").one()
    assert order.status == "FILLED"
    assert order.lifecycle_state == "ENTRY_FILLED"
    assert position.lifecycle_state == "OPEN_POSITION"

    engine._process_symbol(db_session, "INFY-EQ", 105.0)
    db_session.commit()

    assert db_session.query(PaperPosition).filter_by(symbol="INFY-EQ").count() == 0
    assert db_session.query(PaperOrder).filter_by(symbol="INFY-EQ", side="SELL").count() == 1
    assert db_session.query(PaperNotification).count() >= 2


@pytest.mark.integration
def test_market_hours_are_deterministic():
    engine = MarketEngineService()
    monday_open = datetime(2026, 5, 18, 4, 0, tzinfo=timezone.utc)  # 09:30 IST
    saturday = datetime(2026, 5, 23, 4, 0, tzinfo=timezone.utc)
    assert engine.is_market_hours(monday_open) is True
    assert engine.is_market_hours(saturday) is False
