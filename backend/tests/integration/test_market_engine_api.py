from __future__ import annotations

import pytest
from sqlalchemy import select

from backend.app.models.paper_trading import ExecutionEvent, MarketEngineSession, PaperNotification, PaperOrder, PaperPosition
from backend.app.services.market_engine_service import MarketEngineService, market_engine
import backend.app.services.paper_trading_service as paper_service
from tests.utils.fakes import FakeFyersService, FakeMarketDataFeed


@pytest.fixture(autouse=True)
def fake_services(monkeypatch):
    monkeypatch.setattr(paper_service, "FyersService", FakeFyersService)
    monkeypatch.setattr(market_engine, "_feed", FakeMarketDataFeed(market_engine._on_tick, market_engine._on_feed_error, market_engine._on_connection_change))
    monkeypatch.setattr(market_engine, "is_market_hours", lambda now=None: True)


@pytest.mark.integration
def test_start_stop_status_and_heartbeat_routes(client, db_session):
    started = client.post("/paper-trading/engine/start")
    assert started.status_code == 200
    assert started.json()["status"] == "STARTING"

    status = client.get("/paper-trading/engine/status")
    assert status.status_code == 200
    assert status.json()["market_hours_active"] is True
    assert status.json()["websocket_connected"] is False

    before_orders = db_session.query(PaperOrder).count()
    heartbeat = client.get("/health/heartbeat")
    assert heartbeat.status_code == 200
    assert heartbeat.json()["status"] == "ok"
    assert db_session.query(PaperOrder).count() == before_orders
    assert db_session.query(MarketEngineSession).one().last_heartbeat_at is not None

    stopped = client.post("/paper-trading/engine/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "STOPPED"


@pytest.mark.integration
def test_limit_order_api_persists_lifecycle_and_execution_audit(client, db_session):
    response = client.post(
        "/paper-trading/orders",
        json={"symbol": "INFY-EQ", "side": "BUY", "type": "LIMIT", "qty": 1, "limit_price": 95, "stop_loss": 90, "target": 105},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["order"]["status"] == "PENDING"
    assert body["order"]["lifecycle_state"] == "PENDING_ENTRY"

    order = db_session.scalar(select(PaperOrder).where(PaperOrder.symbol == "INFY-EQ"))
    engine = MarketEngineService()
    engine._process_symbol(db_session, "INFY-EQ", 95.0)
    engine._process_symbol(db_session, "INFY-EQ", 105.0)
    db_session.commit()

    db_session.refresh(order)
    assert order.requested_entry_price == 95.0
    assert order.lifecycle_state == "ENTRY_FILLED"
    assert db_session.query(PaperPosition).count() == 0
    assert db_session.query(ExecutionEvent).filter_by(event_type="ENTRY_FILLED").count() == 1
    assert db_session.query(ExecutionEvent).filter_by(event_type="EXIT_FILLED").count() == 1
    assert db_session.query(PaperNotification).filter_by(event_type="PENDING_ENTRY_CREATED").count() == 1
    assert db_session.query(PaperNotification).filter_by(event_type="ENTRY_FILLED").count() >= 1
    assert db_session.query(PaperNotification).filter_by(event_type="EXIT_FILLED").count() == 1


@pytest.mark.integration
def test_restart_recovery_and_market_closed_reconcile_do_not_crash(db_session, monkeypatch):
    service_engine = MarketEngineService()
    order = PaperOrder(
        account_id=1,
        symbol="TCS-EQ",
        side="BUY",
        order_type="LIMIT",
        product_type="CNC",
        qty=1,
        order_price=100.0,
        requested_entry_price=100.0,
        status="PENDING",
        lifecycle_state="PENDING_ENTRY",
    )
    db_session.add(order)
    db_session.commit()

    assert service_engine._desired_symbols(db_session) == {"TCS-EQ"}
    session = service_engine._get_or_create_session(db_session)
    session.status = "STARTING"
    monkeypatch.setattr(service_engine, "is_market_hours", lambda now=None: False)
    service_engine._reconcile_session(db_session, session)
    db_session.commit()
    db_session.refresh(order)
    assert session.status == "WAITING_MARKET_OPEN"
    assert order.lifecycle_state == "MARKET_CLOSED_WAITING"
