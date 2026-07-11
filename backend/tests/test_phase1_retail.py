"""Phase 1 retail platform — unit/integration tests (offline, no live FYERS required)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.auth import User
from app.models.paper_trading import PaperPosition, PaperTradeHistory, PaperTradingAccount
from app.models.retail import Watchlist, WatchlistItem, UserRiskLimits, UserNotification
from app.models.stock import StockMaster
from app.schemas.retail import (
    OrderPreviewRequest,
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistUpdate,
)
from app.services.chart_service import ChartService
from app.services.notification_center_service import NotificationCenterService
from app.services.order_ticket_service import OrderTicketService
from app.services.risk_enforcement_service import RiskEnforcementService
from app.services.symbol_search_service import SymbolSearchService
from app.services.watchlist_service import WatchlistService


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Only create Phase-1 related tables to avoid PG-only types (JSONB) on SQLite.
    tables = [
        User.__table__,
        PaperTradingAccount.__table__,
        PaperPosition.__table__,
        PaperTradeHistory.__table__,
        Watchlist.__table__,
        WatchlistItem.__table__,
        UserRiskLimits.__table__,
        UserNotification.__table__,
        StockMaster.__table__,
    ]
    # Optional models used by search favorites / history
    from app.models.retail import FavoriteSymbol, SymbolSearchHistory

    tables.extend([FavoriteSymbol.__table__, SymbolSearchHistory.__table__])
    Base.metadata.create_all(engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def user(db):
    u = User(
        id=uuid.uuid4(),
        email="retail@test.com",
        full_name="Retail Tester",
        password_hash="x",
        is_active=True,
        is_email_verified=True,
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def account(db, user):
    acc = PaperTradingAccount(
        user_id=user.id,
        name="Test",
        starting_balance=Decimal("1000000"),
        cash_balance=Decimal("1000000"),
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def _seed_stocks(db):
    for sym, sector in [("RELIANCE", "Energy"), ("TCS", "IT"), ("INFY", "IT")]:
        db.add(
            StockMaster(
                symbol=sym,
                company_name=f"{sym} Ltd",
                sector=sector,
                series="EQ",
                isin=f"INE{sym[:6]}",
                universe="NIFTY500",
                is_active=True,
            )
        )
    db.commit()


def test_watchlist_crud(db, user):
    with patch("app.services.watchlist_service.MarketQuotesService.get_quotes_batch", return_value={}):
        svc = WatchlistService(db, user.id)
        wl = svc.create_watchlist(WatchlistCreate(name="Swing", symbols=["RELIANCE", "TCS"]))
        assert wl.name == "Swing"
        assert wl.item_count == 2

        wl2 = svc.update_watchlist(wl.id, WatchlistUpdate(is_pinned=True, is_favorite=True, sort_by="alphabet"))
        assert wl2.is_pinned is True
        assert wl2.is_favorite is True

        wl3 = svc.add_item(wl.id, WatchlistItemCreate(symbol="INFY"))
        assert any(i.symbol == "INFY" for i in wl3.items)

        item_id = next(i.id for i in wl3.items if i.symbol == "TCS")
        wl4 = svc.remove_item(wl.id, item_id)
        assert all(i.symbol != "TCS" for i in wl4.items)

        exported = svc.export_watchlist(wl.id)
        assert "RELIANCE" in exported.symbols

        lists = svc.list_watchlists()
        assert len(lists) >= 1

        svc.delete_watchlist(wl.id)
        remaining = db.query(Watchlist).filter(Watchlist.user_id == user.id).all() if hasattr(db, "query") else []
        # SQLAlchemy 2 style
        from sqlalchemy import select

        remaining = list(db.scalars(select(Watchlist).where(Watchlist.user_id == user.id)).all())
        assert remaining == []


def test_risk_enforcement_rejects_oversized_position(db, user, account):
    risk = RiskEnforcementService(db, user.id)
    limits = risk.get_or_create_limits()
    limits.max_position_size = Decimal("10000")
    db.commit()

    result = risk.validate_order(
        account=account,
        symbol="RELIANCE",
        side="BUY",
        qty=100,
        price=5000,  # 500_000 value
        product_type="CNC",
    )
    assert result.allowed is False
    assert any("position size" in r.lower() or "MAX_POSITION_SIZE" in str(result.checks) for r in result.reasons) or any(
        c["code"] == "MAX_POSITION_SIZE" and not c["passed"] for c in result.checks
    )


def test_risk_enforcement_rejects_daily_loss_breach(db, user, account):
    risk = RiskEnforcementService(db, user.id)
    limits = risk.get_or_create_limits()
    limits.max_daily_loss = Decimal("100")
    db.commit()

    with patch.object(risk, "_daily_pnl", return_value=Decimal("-150")):
        result = risk.validate_order(
            account=account,
            symbol="TCS",
            side="BUY",
            qty=1,
            price=100,
            product_type="CNC",
        )
    assert result.allowed is False
    assert any(c["code"] == "MAX_DAILY_LOSS" and not c["passed"] for c in result.checks)


def test_order_preview_charges(db, user, account):
    with patch("app.services.order_ticket_service.MarketQuotesService.get_quotes_batch", return_value={"RELIANCE": {"ltp": 2500.0}}):
        with patch.object(RiskEnforcementService, "validate_order") as mock_v:
            from app.services.risk_enforcement_service import RiskCheckResult

            mock_v.return_value = RiskCheckResult(allowed=True, checks=[{"code": "OK", "passed": True, "message": "ok"}])
            ticket = OrderTicketService(db, user.id, account)
            prev = ticket.preview(
                OrderPreviewRequest(symbol="RELIANCE", side="BUY", type="MARKET", product_type="CNC", qty=10)
            )
    assert prev.order_value == 25000.0
    assert prev.charges.total_charges >= 0
    assert prev.margin_required > 0
    assert prev.estimated_price == 2500.0


def test_notification_center(db, user):
    svc = NotificationCenterService(db, user.id)
    n = svc.create_simple(
        category="order_update",
        title="Order filled",
        body="RELIANCE BUY filled",
        level="success",
        symbol="RELIANCE",
    )
    assert n.id > 0
    assert svc.unread_count() == 1
    listed = svc.list_notifications()
    assert listed.total == 1
    svc.mark_all_read()
    assert svc.unread_count() == 0
    svc.delete([n.id])
    assert svc.list_notifications().total == 0


def test_symbol_search(db, user):
    _seed_stocks(db)
    svc = SymbolSearchService(db, user.id)
    res = svc.search("REL")
    assert any(r.symbol == "RELIANCE" for r in res.results)
    svc.record_search("RELIANCE", "REL")
    svc.add_favorite("TCS")
    res2 = svc.search("")
    assert any(r.symbol == "TCS" for r in res2.favorites)


def test_chart_indicators_math():
    closes = [float(i) for i in range(1, 60)]
    sma = ChartService._sma(closes, 20)
    assert sma[18] is None
    assert sma[19] is not None
    ema = ChartService._ema(closes, 20)
    assert ema[19] is not None
    rsi = ChartService._rsi(closes, 14)
    assert any(v is not None for v in rsi)


def test_retail_routes_registered():
    from app.routes import api_router

    paths = []
    for r in api_router.routes:
        p = getattr(r, "path", None)
        if p:
            paths.append(p)
    expected = [
        "/watchlists",
        "/market/quote-board",
        "/market/indices",
        "/market/heatmap",
        "/search/symbols",
        "/charts/{symbol}",
        "/notifications",
        "/holdings",
        "/positions",
        "/orders",
        "/order-ticket/preview",
        "/risk/limits",
        "/ws/quotes",
    ]
    for e in expected:
        assert any(e in p for p in paths), f"Missing route {e} in {paths}"
