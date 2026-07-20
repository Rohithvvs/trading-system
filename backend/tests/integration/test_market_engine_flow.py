from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.app.models.paper_trading import PaperNotification, PaperOrder, PaperPosition
from backend.app.services.market_engine_service import MarketEngineService
from backend.app.services.paper_trading_service import PaperTradingService
import backend.app.services.paper_trading_service as paper_service
from tests.utils.fakes import FakeFyersService

_TEST_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000010")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pending_limit_buy_auto_fills_and_target_auto_exits(async_db_session, monkeypatch):
    monkeypatch.setattr(paper_service, "FyersService", FakeFyersService)
    # Notifications use a separate sync SessionLocal; stub to keep this async fixture isolated.
    monkeypatch.setattr(PaperTradingService, "add_notification", lambda self, *a, **k: None)

    def _seed(session):
        service = PaperTradingService(session, user_id=_TEST_USER_ID)
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
        session.add(order)
        session.commit()
        return order.id

    order_id = await async_db_session.run_sync(_seed)
    order = await async_db_session.get(PaperOrder, order_id)
    assert order is not None

    engine = MarketEngineService()
    await engine._process_symbol(async_db_session, "INFY-EQ", 95.0)
    await async_db_session.commit()

    await async_db_session.refresh(order)
    position = (
        await async_db_session.scalars(select(PaperPosition).where(PaperPosition.symbol == "INFY-EQ"))
    ).one()
    assert order.status == "FILLED"
    assert order.lifecycle_state == "ENTRY_FILLED"
    assert position.lifecycle_state == "OPEN_POSITION"

    await engine._process_symbol(async_db_session, "INFY-EQ", 105.0)
    await async_db_session.commit()

    pos_count = len(
        (await async_db_session.scalars(select(PaperPosition).where(PaperPosition.symbol == "INFY-EQ"))).all()
    )
    sell_count = len(
        (
            await async_db_session.scalars(
                select(PaperOrder).where(PaperOrder.symbol == "INFY-EQ", PaperOrder.side == "SELL")
            )
        ).all()
    )
    assert pos_count == 0
    assert sell_count == 1


@pytest.mark.integration
def test_market_hours_are_deterministic():
    engine = MarketEngineService()
    monday_open = datetime(2026, 5, 18, 4, 0, tzinfo=timezone.utc)  # 09:30 IST
    saturday = datetime(2026, 5, 23, 4, 0, tzinfo=timezone.utc)
    assert engine.is_market_hours(monday_open) is True
    assert engine.is_market_hours(saturday) is False
