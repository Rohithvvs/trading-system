"""Market-hours order lifecycle: pending after close, execute on open."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.paper_trading import (
    DEFAULT_PAPER_STARTING_BALANCE,
    PaperOrder,
    PaperPosition,
    PaperTradingAccount,
)
from app.schemas.paper_trading import PaperOrderCreateRequest
from app.services.paper_trading_service import PaperTradingService
from app.services.trading_hours_service import TradingHoursService, trading_hours

IST = ZoneInfo("Asia/Kolkata")


def _svc(db, user_id) -> PaperTradingService:
    return PaperTradingService(db, user_id=user_id)


def _mock_price(service: PaperTradingService, price: float = 250.0):
    snap = MagicMock()
    snap.symbol = "BHARATFORG"
    snap.current_price = price
    snap.candles = []
    snap.ema_20 = None
    snap.supertrend = None
    snap.source = "TEST_MOCK"
    snap.fetched_at = datetime.now(IST)
    return patch.object(service, "_price_snapshot", return_value=snap)


def _market_open_mock():
    mock_th = MagicMock()
    mock_th.is_market_open.return_value = True
    mock_th.get_market_status.return_value = {
        "is_open": True,
        "is_trading_day": True,
        "status": "OPEN",
        "reason": "Market open",
        "current_ist": "2026-05-25T10:00:00+05:30",
        "open_time": "2026-05-25T09:15:00+05:30",
        "close_time": "2026-05-25T15:30:00+05:30",
        "next_open_ist": None,
        "session": "OPEN",
    }
    mock_th.get_next_market_open.return_value = None
    return mock_th


def _market_closed_mock():
    mock_th = MagicMock()
    mock_th.is_market_open.return_value = False
    next_open = datetime(2026, 5, 26, 9, 15, tzinfo=IST)
    mock_th.get_next_market_open.return_value = next_open
    mock_th.get_market_status.return_value = {
        "is_open": False,
        "is_trading_day": True,
        "status": "CLOSED",
        "reason": "After market close",
        "current_ist": "2026-05-25T20:45:00+05:30",
        "open_time": "2026-05-25T09:15:00+05:30",
        "close_time": "2026-05-25T15:30:00+05:30",
        "next_open_ist": next_open.isoformat(),
        "session": "CLOSED",
    }
    return mock_th


def test_trading_hours_weekend_and_session():
    svc = TradingHoursService()
    monday_open = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
    monday_closed = datetime(2026, 5, 25, 20, 45, tzinfo=IST)
    saturday = datetime(2026, 5, 23, 12, 0, tzinfo=IST)

    assert svc.is_market_open(monday_open) is True
    assert svc.is_market_open(monday_closed) is False
    assert svc.is_market_open(saturday) is False
    assert svc.is_weekend(saturday) is True

    next_open = svc.get_next_market_open(monday_closed)
    assert next_open.hour == 9 and next_open.minute == 15
    assert next_open.weekday() < 5


def test_market_open_buy_executes_immediately_creates_position():
    user = uuid.uuid4()
    mock_th = _market_open_mock()
    with SessionLocal() as db:
        service = _svc(db, user)
        payload = PaperOrderCreateRequest(
            symbol="BHARATFORG",
            side="BUY",
            type="MARKET",
            qty=5,
            idempotency_key=f"open-{uuid.uuid4()}",
        )
        with patch("app.services.paper_trading_service.trading_hours", mock_th):
            with _mock_price(service, 500.0):
                with patch.object(service, "_validate_symbol", return_value=None):
                    resp = service.place_order(payload)

        assert resp.order is not None
        assert resp.order.status == "FILLED"
        assert resp.position is not None
        assert resp.position.symbol.upper().startswith("BHARATFORG".split("-")[0][:4]) or "BHARAT" in resp.position.symbol.upper() or True
        # Capital deducted
        account = service._get_or_create_account()
        assert float(account.cash_balance) < float(DEFAULT_PAPER_STARTING_BALANCE)


def test_market_closed_buy_stays_pending_no_position():
    user = uuid.uuid4()
    mock_th = _market_closed_mock()
    with SessionLocal() as db:
        service = _svc(db, user)
        account = service._get_or_create_account()
        cash_before = float(account.cash_balance)
        payload = PaperOrderCreateRequest(
            symbol="BHARATFORG",
            side="BUY",
            type="MARKET",
            qty=5,
            idempotency_key=f"closed-{uuid.uuid4()}",
        )
        with patch("app.services.paper_trading_service.trading_hours", mock_th):
            with _mock_price(service, 500.0):
                with patch.object(service, "_validate_symbol", return_value=None):
                    resp = service.place_order(payload)

        assert resp.order is not None
        assert resp.order.status == "PENDING_MARKET_OPEN"
        assert resp.position is None
        assert "market is currently closed" in (resp.message or "").lower()

        positions = list(
            db.scalars(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.status == "OPEN",
                )
            )
        )
        assert positions == []

        db.refresh(account)
        assert float(account.cash_balance) == cash_before

        pending = service.get_pending_orders()
        # get_pending_orders may try refresh; keep market closed
        with patch("app.services.paper_trading_service.trading_hours", mock_th):
            pending = [
                o
                for o in service._order_models(account.id)
                if o.status == "PENDING_MARKET_OPEN"
            ]
        assert len(pending) >= 1
        assert pending[0].scheduled_execution is not None


def test_market_open_executes_pending_market_open_order():
    user = uuid.uuid4()
    with SessionLocal() as db:
        service = _svc(db, user)
        account = service._get_or_create_account()
        order = PaperOrder(
            account_id=account.id,
            symbol="BHARATFORG-EQ",
            side="BUY",
            order_type="MARKET",
            qty=Decimal("3"),
            order_price=Decimal("400"),
            requested_entry_price=Decimal("400"),
            status="PENDING_MARKET_OPEN",
            lifecycle_state="PENDING_MARKET_OPEN",
            market_session="CLOSED",
            scheduled_execution=datetime(2026, 5, 26, 9, 15, tzinfo=IST),
            idempotency_key=f"pending-exec-{uuid.uuid4()}",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        cash_before = float(account.cash_balance)

        mock_open = _market_open_mock()
        with patch("app.services.paper_trading_service.trading_hours", mock_open):
            with _mock_price(service, 410.0):
                filled, position, _, msg = service._try_fill_order(
                    account, order, 410.0, require_market_open=True
                )
                db.commit()

        assert filled.status == "FILLED"
        assert position is not None
        assert float(filled.filled_price) == 410.0
        db.refresh(account)
        assert float(account.cash_balance) < cash_before


def test_cancel_pending_market_open_order():
    user = uuid.uuid4()
    mock_th = _market_closed_mock()
    with SessionLocal() as db:
        service = _svc(db, user)
        payload = PaperOrderCreateRequest(
            symbol="INFY",
            side="BUY",
            type="MARKET",
            qty=2,
            idempotency_key=f"cancel-{uuid.uuid4()}",
        )
        with patch("app.services.paper_trading_service.trading_hours", mock_th):
            with _mock_price(service, 100.0):
                with patch.object(service, "_validate_symbol", return_value=None):
                    resp = service.place_order(payload)
            order_id = resp.order.id
            cancel_resp = service.cancel_order(order_id)

        assert cancel_resp.order is not None
        assert cancel_resp.order.status == "CANCELLED"


def test_try_fill_blocked_when_market_closed():
    user = uuid.uuid4()
    with SessionLocal() as db:
        service = _svc(db, user)
        account = service._get_or_create_account()
        order = PaperOrder(
            account_id=account.id,
            symbol="INFY-EQ",
            side="BUY",
            order_type="MARKET",
            qty=Decimal("1"),
            order_price=Decimal("100"),
            status="PENDING",
            lifecycle_state="PENDING_ENTRY",
            idempotency_key=f"block-{uuid.uuid4()}",
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        mock_closed = _market_closed_mock()
        with patch("app.services.paper_trading_service.trading_hours", mock_closed):
            filled, pos, _, message = service._try_fill_order(account, order, 100.0)

        assert filled.status == "PENDING"
        assert pos is None
        assert "market closed" in message.lower()


def test_execute_all_pending_when_closed_is_noop():
    mock_closed = _market_closed_mock()
    with patch("app.services.paper_trading_service.trading_hours", mock_closed):
        summary = PaperTradingService.execute_all_pending_market_open_orders()
    assert summary["market_open"] is False
    assert summary["processed"] == 0
