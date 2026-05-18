from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.app.models.paper_trading import ExecutionEvent, MarketEngineSession, PaperNotification, PaperOrder, PaperPosition
from backend.app.services.market_engine_service import MarketEngineService
from backend.app.services.paper_trading_service import PaperTradingService
import backend.app.services.paper_trading_service as paper_service
from tests.utils.fakes import FakeFyersService, FakeMarketDataFeed


@pytest.fixture()
def engine(monkeypatch):
    service = MarketEngineService()
    service._feed = FakeMarketDataFeed(service._on_tick, service._on_feed_error, service._on_connection_change)
    monkeypatch.setattr(service, "is_market_hours", lambda now=None: True)
    return service


@pytest.fixture(autouse=True)
def fake_quotes(monkeypatch):
    monkeypatch.setattr(paper_service, "FyersService", FakeFyersService)


def make_pending_order(db_session, limit: float = 95.0) -> PaperOrder:
    service = PaperTradingService(db_session)
    account = service._get_or_create_account()
    order = PaperOrder(
        account_id=account.id,
        symbol="INFY-EQ",
        side="BUY",
        order_type="LIMIT",
        product_type="CNC",
        qty=1,
        order_price=limit,
        requested_entry_price=limit,
        stop_loss=90.0,
        target=105.0,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY",
    )
    db_session.add(order)
    db_session.commit()
    return order


@pytest.mark.unit
def test_limit_buy_remains_pending_until_threshold(db_session, engine):
    order = make_pending_order(db_session)
    engine._process_symbol(db_session, "INFY-EQ", 96.0)
    db_session.commit()
    db_session.refresh(order)
    assert order.status == "PENDING"
    assert order.lifecycle_state == "PENDING_ENTRY"


@pytest.mark.unit
def test_duplicate_target_ticks_create_one_sell_and_one_exit_event(db_session, engine):
    order = make_pending_order(db_session)
    engine._process_symbol(db_session, "INFY-EQ", 95.0)
    db_session.commit()
    position = db_session.scalar(select(PaperPosition).where(PaperPosition.symbol == "INFY-EQ"))
    assert position is not None

    engine._process_symbol(db_session, "INFY-EQ", 105.0)
    engine._process_symbol(db_session, "INFY-EQ", 106.0)
    db_session.commit()

    assert db_session.query(PaperOrder).filter_by(symbol="INFY-EQ", side="SELL").count() == 1
    assert db_session.query(ExecutionEvent).filter_by(event_type="EXIT_FILLED").count() == 1


@pytest.mark.unit
def test_stop_loss_tick_creates_one_sell(db_session, engine):
    make_pending_order(db_session)
    engine._process_symbol(db_session, "INFY-EQ", 95.0)
    engine._process_symbol(db_session, "INFY-EQ", 90.0)
    engine._process_symbol(db_session, "INFY-EQ", 89.0)
    db_session.commit()
    assert db_session.query(PaperOrder).filter_by(symbol="INFY-EQ", side="SELL").count() == 1
    assert db_session.query(ExecutionEvent).filter_by(event_type="EXIT_FILLED").count() == 1


@pytest.mark.unit
def test_token_expiry_pauses_once_and_dedupes_notification(db_session, engine):
    make_pending_order(db_session)
    session = engine._get_or_create_session(db_session)
    db_session.commit()

    engine._pause_for_token(db_session, session)
    engine._pause_for_token(db_session, session)
    db_session.commit()

    assert session.status == "PAUSED_TOKEN_EXPIRED"
    order = db_session.scalar(select(PaperOrder))
    assert order.lifecycle_state == "TOKEN_EXPIRED_PAUSED"
    assert db_session.query(PaperNotification).filter_by(event_type="TOKEN_EXPIRED").count() == 1


@pytest.mark.unit
def test_market_closed_sets_waiting_without_crashing(db_session, monkeypatch):
    engine = MarketEngineService()
    engine._feed = FakeMarketDataFeed(engine._on_tick, engine._on_feed_error, engine._on_connection_change)
    monkeypatch.setattr(engine, "is_market_hours", lambda now=None: False)
    order = make_pending_order(db_session)
    session = engine._get_or_create_session(db_session)
    session.status = "STARTING"
    engine._reconcile_session(db_session, session)
    db_session.commit()
    db_session.refresh(order)
    assert session.status == "WAITING_MARKET_OPEN"
    assert order.lifecycle_state == "MARKET_CLOSED_WAITING"


@pytest.mark.unit
def test_symbol_subscriptions_follow_active_state(db_session, engine):
    order = make_pending_order(db_session)
    session = engine._get_or_create_session(db_session)
    session.status = "STARTING"
    engine._reconcile_session(db_session, session)
    assert engine._feed.symbols == {"INFY-EQ"}

    engine._process_symbol(db_session, "INFY-EQ", 95.0)
    db_session.commit()
    engine._reconcile_session(db_session, session)
    assert engine._feed.symbols == {"INFY-EQ"}

    engine._process_symbol(db_session, "INFY-EQ", 105.0)
    db_session.commit()
    engine._reconcile_session(db_session, session)
    assert engine._desired_symbols(db_session) == set()
    assert engine._feed.symbols == set()


@pytest.mark.unit
def test_restart_rebuilds_desired_symbols(db_session, engine):
    make_pending_order(db_session)
    fresh_engine = MarketEngineService()
    assert fresh_engine._desired_symbols(db_session) == {"INFY-EQ"}


@pytest.mark.unit
def test_market_hours_are_deterministic():
    engine = MarketEngineService()
    monday_open = datetime(2026, 5, 18, 4, 0, tzinfo=timezone.utc)
    saturday = datetime(2026, 5, 23, 4, 0, tzinfo=timezone.utc)
    assert engine.is_market_hours(monday_open) is True
    assert engine.is_market_hours(saturday) is False
