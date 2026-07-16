"""
Phase 1 — Multi-user paper trading isolation tests.

Verifies:
- Each user gets an independent ₹10,00,000 paper account
- Orders / positions / trades / analytics never leak across users
- Horizontal privilege escalation is blocked (order/position of user A invisible to B)
"""
from __future__ import annotations

import os
import tempfile
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

# SQLite JSONB / UUID compatibility for create_all
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"  # type: ignore[method-assign]
SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "CHAR(36)"  # type: ignore[method-assign]

from app.models.paper_trading import (  # noqa: E402
    Base,
    PaperOrder,
    PaperPosition,
    PaperTradeHistory,
    PaperTradingAccount,
    PaperTransaction,
    PaperAlert,
    DEFAULT_PAPER_STARTING_BALANCE,
)
from app.services.paper_trading_service import PaperTradingService  # noqa: E402
from app.schemas.paper_trading import PaperOrderCreateRequest  # noqa: E402


test_db_path = os.path.join(tempfile.gettempdir(), "test_multi_user_paper_isolation.db")
if os.path.exists(test_db_path):
    os.remove(test_db_path)

engine = create_engine(
    f"sqlite:///{test_db_path}",
    connect_args={"check_same_thread": False, "timeout": 15},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_tables():
    with SessionLocal() as db:
        for model in (
            PaperAlert,
            PaperTransaction,
            PaperTradeHistory,
            PaperOrder,
            PaperPosition,
            PaperTradingAccount,
        ):
            db.query(model).delete()
        db.commit()
    yield
    with SessionLocal() as db:
        for model in (
            PaperAlert,
            PaperTransaction,
            PaperTradeHistory,
            PaperOrder,
            PaperPosition,
            PaperTradingAccount,
        ):
            db.query(model).delete()
        db.commit()


def _svc(db, user_id: uuid.UUID) -> PaperTradingService:
    return PaperTradingService(db, user_id=user_id)


def _mock_price(service: PaperTradingService, price: float = 100.0):
    from datetime import datetime, timezone

    class Dummy:
        symbol = "INFY-EQ"
        current_price = price
        candles = []
        ema_20 = None
        supertrend = None
        source = "TEST_MOCK"
        fetched_at = datetime.now(timezone.utc)

    return patch.object(service, "_price_snapshot", return_value=Dummy())


def _place_buy(service: PaperTradingService, **kwargs):
    payload = PaperOrderCreateRequest(
        symbol=kwargs.get("symbol", "INFY-EQ"),
        side=kwargs.get("side", "BUY"),
        type=kwargs.get("type", "MARKET"),
        qty=kwargs.get("qty", 10),
        limit_price=kwargs.get("limit_price"),
        idempotency_key=kwargs.get("idempotency_key", f"key-{uuid.uuid4()}"),
    )
    # market hours check is imported inside place_order
    mock_th = MagicMock()
    mock_th.validate_can_place_buy_order.return_value = None
    with patch.dict("sys.modules", {}):
        with patch("app.services.trading_hours_service.trading_hours", mock_th):
            with _mock_price(service, kwargs.get("price", 100.0)):
                # Also patch the import path used inside place_order dynamically
                with patch(
                    "app.services.paper_trading_service.PaperTradingService._validate_symbol",
                    return_value=None,
                ):
                    return service.place_order(payload)


def test_each_user_gets_isolated_ten_lakh_account():
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    with SessionLocal() as db:
        a = _svc(db, user_a)._get_or_create_account()
        b = _svc(db, user_b)._get_or_create_account()

        assert a.id != b.id
        assert a.user_id == user_a
        assert b.user_id == user_b
        assert float(a.cash_balance) == float(DEFAULT_PAPER_STARTING_BALANCE)
        assert float(b.cash_balance) == float(DEFAULT_PAPER_STARTING_BALANCE)
        assert float(DEFAULT_PAPER_STARTING_BALANCE) == 1_000_000.0


def test_ensure_paper_account_is_idempotent():
    user = uuid.uuid4()
    with SessionLocal() as db:
        a1 = PaperTradingService.ensure_paper_account_for_user(db, user)
        a2 = PaperTradingService.ensure_paper_account_for_user(db, user)
        assert a1.id == a2.id
        rows = db.scalars(select(PaperTradingAccount).where(PaperTradingAccount.user_id == user)).all()
        assert len(rows) == 1


def test_user_b_does_not_see_user_a_orders_or_positions():
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    with SessionLocal() as db:
        svc_a = _svc(db, user_a)
        # Inject pending order + open position directly (avoids market-hours / price plumbing)
        acc_a = svc_a._get_or_create_account()
        order = PaperOrder(
            account_id=acc_a.id,
            symbol="INFY-EQ",
            side="BUY",
            order_type="MARKET",
            qty=Decimal("10"),
            order_price=Decimal("250"),
            status="FILLED",
            lifecycle_state="ENTRY_FILLED",
            filled_price=Decimal("250"),
            idempotency_key=f"seed-a-{uuid.uuid4()}",
        )
        pos = PaperPosition(
            account_id=acc_a.id,
            symbol="INFY-EQ",
            qty=Decimal("10"),
            avg_entry_price=Decimal("250"),
            current_price=Decimal("250"),
            status="OPEN",
            lifecycle_state="OPEN_POSITION",
        )
        acc_a.cash_balance = Decimal("997500.00")
        db.add(order)
        db.add(pos)
        db.commit()

        dash_a = svc_a.get_dashboard()
        assert len(dash_a.positions) == 1
        assert dash_a.positions[0].symbol == "INFY-EQ"

    with SessionLocal() as db:
        svc_b = _svc(db, user_b)
        dash_b = svc_b.get_dashboard()
        # Fresh ₹10L book
        assert float(dash_b.account.balance) == pytest.approx(1_000_000.0, rel=0, abs=0.01) or float(
            dash_b.account.available_cash
        ) == pytest.approx(1_000_000.0, rel=0, abs=0.01)
        assert dash_b.positions == []
        assert dash_b.open_orders == []
        assert dash_b.trades == []
        analytics = svc_b.get_analytics()
        assert analytics.get("total_trades", 0) == 0


def test_user_b_cannot_cancel_user_a_order():
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    with SessionLocal() as db:
        svc_a = _svc(db, user_a)
        acc_a = svc_a._get_or_create_account()
        order = PaperOrder(
            account_id=acc_a.id,
            symbol="INFY-EQ",
            side="BUY",
            order_type="LIMIT",
            qty=Decimal("1"),
            order_price=Decimal("1.0"),
            status="PENDING",
            lifecycle_state="PENDING_ENTRY",
            idempotency_key=f"seed-limit-{uuid.uuid4()}",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        order_id = order.id

    with SessionLocal() as db:
        svc_b = _svc(db, user_b)
        with pytest.raises(ValueError, match="Order not found"):
            svc_b.cancel_order(order_id)

    # User A can still cancel
    with SessionLocal() as db:
        svc_a = _svc(db, user_a)
        resp = svc_a.cancel_order(order_id)
        assert resp.order is not None
        assert resp.order.status == "CANCELLED"


def test_n_users_isolation_batch():
    """Scale check: N users each get a clean ₹10L book with zero shared rows."""
    n = 10
    user_ids = [uuid.uuid4() for _ in range(n)]
    account_ids = set()

    with SessionLocal() as db:
        for uid in user_ids:
            acc = _svc(db, uid)._get_or_create_account()
            account_ids.add(acc.id)
            assert float(acc.cash_balance) == 1_000_000.0
            assert acc.user_id == uid

        assert len(account_ids) == n

        # Seed activity only for user 0
        acc0 = _svc(db, user_ids[0])._get_or_create_account()
        db.add(
            PaperPosition(
                account_id=acc0.id,
                symbol="RELIANCE-EQ",
                qty=Decimal("5"),
                avg_entry_price=Decimal("100"),
                current_price=Decimal("100"),
                status="OPEN",
            )
        )
        db.commit()

        for uid in user_ids[1:]:
            dash = _svc(db, uid).get_dashboard()
            assert dash.positions == []
            assert dash.trades == []
            assert _svc(db, uid).get_analytics().get("total_trades", 0) == 0

        # User 0 still has their position
        dash0 = _svc(db, user_ids[0]).get_dashboard()
        assert len(dash0.positions) == 1


def test_never_recreate_existing_account_on_ensure():
    user = uuid.uuid4()
    with SessionLocal() as db:
        first = PaperTradingService.ensure_paper_account_for_user(db, user)
        first.cash_balance = Decimal("999000.00")
        db.commit()
        second = PaperTradingService.ensure_paper_account_for_user(db, user)
        assert second.id == first.id
        assert float(second.cash_balance) == 999000.0


def test_fifty_users_account_provisioning():
    """Provision 50 isolated accounts (balance bookkeeping only)."""
    n = 50
    with SessionLocal() as db:
        ids = set()
        for _ in range(n):
            uid = uuid.uuid4()
            acc = PaperTradingService.ensure_paper_account_for_user(db, uid)
            ids.add(acc.id)
            assert float(acc.starting_balance) == 1_000_000.0
        assert len(ids) == n


def test_engine_fill_uses_order_account_not_shared():
    """Market-engine style fill must debit the order's account, not a random shared one."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    with SessionLocal() as db:
        acc_a = _svc(db, user_a)._get_or_create_account()
        acc_b = _svc(db, user_b)._get_or_create_account()
        order = PaperOrder(
            account_id=acc_a.id,
            symbol="INFY-EQ",
            side="BUY",
            order_type="MARKET",
            qty=Decimal("2"),
            order_price=Decimal("100"),
            status="PENDING",
            lifecycle_state="PENDING_ENTRY",
            idempotency_key=f"engine-fill-{uuid.uuid4()}",
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        # System service (no user_id) — same as market engine
        sys_svc = PaperTradingService(db)
        loaded = sys_svc.get_account_by_id(int(order.account_id), for_update=True)
        assert loaded.id == acc_a.id
        assert loaded.id != acc_b.id
        filled, pos, _, _ = sys_svc._try_fill_order(loaded, order, 100.0)
        assert filled.status == "FILLED"
        assert pos is not None
        assert pos.account_id == acc_a.id
        db.commit()

        db.refresh(acc_a)
        db.refresh(acc_b)
        assert float(acc_b.cash_balance) == 1_000_000.0
        assert float(acc_a.cash_balance) < 1_000_000.0
