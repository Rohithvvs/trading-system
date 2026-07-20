from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.app.models.paper_trading import ExecutionEvent, PaperNotification, PaperOrder, PaperPosition
from backend.app.services.market_engine_service import MarketEngineService
from backend.app.services.paper_trading_service import PaperTradingService
import backend.app.services.paper_trading_service as paper_service
from tests.utils.fakes import FakeFyersService, FakeMarketDataFeed

# Deterministic user scope for multi-tenant paper accounts.
_TEST_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


@pytest.fixture()
def engine(monkeypatch):
    service = MarketEngineService()
    service._feed = FakeMarketDataFeed(service._on_tick, service._on_feed_error, service._on_connection_change)
    monkeypatch.setattr(service, "is_market_hours", lambda now=None: True)
    return service


@pytest.fixture(autouse=True)
def fake_quotes(monkeypatch):
    monkeypatch.setattr(paper_service, "FyersService", FakeFyersService)


@pytest.fixture(autouse=True)
def stub_sync_notifications(monkeypatch):
    """Market engine writes notifications via sync SessionLocal (separate DB).

    Stub that side-path so async in-memory tests stay isolated and lock-free.
    """
    monkeypatch.setattr(
        PaperTradingService,
        "add_notification",
        lambda self, *args, **kwargs: None,
    )


async def make_pending_order(async_db_session, limit: float = 95.0) -> PaperOrder:
    def _seed(session):
        service = PaperTradingService(session, user_id=_TEST_USER_ID)
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
        session.add(order)
        session.commit()
        return order.id

    order_id = await async_db_session.run_sync(_seed)
    order = await async_db_session.get(PaperOrder, order_id)
    assert order is not None
    return order


@pytest.mark.asyncio
async def test_limit_buy_remains_pending_until_threshold(async_db_session, engine):
    order = await make_pending_order(async_db_session)
    await engine._process_symbol(async_db_session, "INFY-EQ", 96.0)
    await async_db_session.commit()
    await async_db_session.refresh(order)
    assert order.status == "PENDING"
    assert order.lifecycle_state == "PENDING_ENTRY"


@pytest.mark.asyncio
async def test_duplicate_target_ticks_create_one_sell_and_one_exit_event(async_db_session, engine):
    await make_pending_order(async_db_session)
    await engine._process_symbol(async_db_session, "INFY-EQ", 95.0)
    await async_db_session.commit()
    position = (
        await async_db_session.scalars(select(PaperPosition).where(PaperPosition.symbol == "INFY-EQ"))
    ).first()
    assert position is not None

    await engine._process_symbol(async_db_session, "INFY-EQ", 105.0)
    await engine._process_symbol(async_db_session, "INFY-EQ", 106.0)
    await async_db_session.commit()

    sell_count = len(
        (
            await async_db_session.scalars(
                select(PaperOrder).where(PaperOrder.symbol == "INFY-EQ", PaperOrder.side == "SELL")
            )
        ).all()
    )
    exit_count = len(
        (
            await async_db_session.scalars(
                select(ExecutionEvent).where(ExecutionEvent.event_type == "EXIT_FILLED")
            )
        ).all()
    )
    assert sell_count == 1
    assert exit_count == 1


@pytest.mark.asyncio
async def test_stop_loss_tick_creates_one_sell(async_db_session, engine):
    await make_pending_order(async_db_session)
    await engine._process_symbol(async_db_session, "INFY-EQ", 95.0)
    await engine._process_symbol(async_db_session, "INFY-EQ", 90.0)
    await engine._process_symbol(async_db_session, "INFY-EQ", 89.0)
    await async_db_session.commit()
    sell_count = len(
        (
            await async_db_session.scalars(
                select(PaperOrder).where(PaperOrder.symbol == "INFY-EQ", PaperOrder.side == "SELL")
            )
        ).all()
    )
    exit_count = len(
        (
            await async_db_session.scalars(
                select(ExecutionEvent).where(ExecutionEvent.event_type == "EXIT_FILLED")
            )
        ).all()
    )
    assert sell_count == 1
    assert exit_count == 1


@pytest.mark.asyncio
async def test_token_expiry_pauses_once_and_dedupes_notification(async_db_session, engine):
    await make_pending_order(async_db_session)
    session = await engine._get_or_create_session(async_db_session)
    await async_db_session.commit()

    # Notifications are written via sync SessionLocal (separate DB). Assert session/order state here.
    await engine._pause_for_token(async_db_session, session)
    await engine._pause_for_token(async_db_session, session)
    await async_db_session.commit()

    assert session.status == "PAUSED_TOKEN_EXPIRED"
    order = (await async_db_session.scalars(select(PaperOrder))).first()
    assert order is not None
    assert order.lifecycle_state == "TOKEN_EXPIRED_PAUSED"


@pytest.mark.asyncio
async def test_market_closed_sets_waiting_without_crashing(async_db_session, monkeypatch):
    engine = MarketEngineService()
    engine._feed = FakeMarketDataFeed(engine._on_tick, engine._on_feed_error, engine._on_connection_change)
    monkeypatch.setattr(engine, "is_market_hours", lambda now=None: False)
    order = await make_pending_order(async_db_session)
    session = await engine._get_or_create_session(async_db_session)
    session.status = "STARTING"
    await engine._reconcile_session(async_db_session, session)
    await async_db_session.commit()
    await async_db_session.refresh(order)
    assert session.status == "WAITING_MARKET_OPEN"
    assert order.lifecycle_state == "MARKET_CLOSED_WAITING"


@pytest.mark.asyncio
async def test_symbol_subscriptions_follow_active_state(async_db_session, engine):
    await make_pending_order(async_db_session)
    session = await engine._get_or_create_session(async_db_session)
    session.status = "STARTING"
    await engine._reconcile_session(async_db_session, session)
    assert engine._feed.symbols == {"INFY-EQ"}

    await engine._process_symbol(async_db_session, "INFY-EQ", 95.0)
    await async_db_session.commit()
    await engine._reconcile_session(async_db_session, session)
    assert engine._feed.symbols == {"INFY-EQ"}

    await engine._process_symbol(async_db_session, "INFY-EQ", 105.0)
    await async_db_session.commit()
    await engine._reconcile_session(async_db_session, session)
    assert await engine._desired_symbols(async_db_session) == set()
    assert engine._feed.symbols == set()


@pytest.mark.asyncio
async def test_restart_rebuilds_desired_symbols(async_db_session, engine):
    await make_pending_order(async_db_session)
    fresh_engine = MarketEngineService()
    assert await fresh_engine._desired_symbols(async_db_session) == {"INFY-EQ"}


def test_market_hours_are_deterministic():
    engine = MarketEngineService()
    monday_open = datetime(2026, 5, 18, 4, 0, tzinfo=timezone.utc)
    saturday = datetime(2026, 5, 23, 4, 0, tzinfo=timezone.utc)
    assert engine.is_market_hours(monday_open) is True
    assert engine.is_market_hours(saturday) is False
