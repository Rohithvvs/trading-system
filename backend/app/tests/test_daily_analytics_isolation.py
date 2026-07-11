"""Daily Analytics must be strictly user-scoped (Phase 2)."""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"  # type: ignore[method-assign]
SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "CHAR(36)"  # type: ignore[method-assign]

from app.models.paper_trading import (  # noqa: E402
    Base,
    PaperTradeHistory,
    PaperTradingAccount,
    PaperDailyJournal,
    PaperOrder,
    PaperPosition,
    PaperTransaction,
    PaperAlert,
)
from app.services.daily_analytics_service import DailyAnalyticsService  # noqa: E402
from app.services.paper_trading_service import PaperTradingService  # noqa: E402

path = os.path.join(tempfile.gettempdir(), "test_daily_analytics_isolation.db")
if os.path.exists(path):
    os.remove(path)
engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clean():
    with Session() as db:
        for m in (PaperDailyJournal, PaperTradeHistory, PaperOrder, PaperPosition, PaperTransaction, PaperAlert, PaperTradingAccount):
            db.query(m).delete()
        db.commit()
    yield


def test_daily_analytics_does_not_leak_trades():
    ua, ub = uuid.uuid4(), uuid.uuid4()
    with Session() as db:
        acc_a = PaperTradingService(db, user_id=ua)._get_or_create_account()
        acc_b = PaperTradingService(db, user_id=ub)._get_or_create_account()
        now = datetime.now(timezone.utc)
        db.add(
            PaperTradeHistory(
                account_id=acc_a.id,
                symbol="INFY-EQ",
                qty=Decimal("10"),
                entry_price=Decimal("100"),
                exit_price=Decimal("110"),
                pnl=Decimal("100"),
                pnl_percent=Decimal("10"),
                opened_at=now,
                closed_at=now,
            )
        )
        db.commit()

        data_a = DailyAnalyticsService(db, user_id=ua).build(period="today", include_ai=False)
        data_b = DailyAnalyticsService(db, user_id=ub).build(period="today", include_ai=False)

        assert data_a["overview"]["trades_executed"] == 1
        assert data_a["overview"]["todays_realized_pnl"] == 100.0
        assert data_b["overview"]["trades_executed"] == 0
        assert data_b["overview"]["todays_realized_pnl"] == 0.0
        assert data_b["account_id"] != data_a["account_id"]


def test_journal_isolated_per_user():
    ua, ub = uuid.uuid4(), uuid.uuid4()
    with Session() as db:
        DailyAnalyticsService(db, user_id=ua).save_journal(
            journal_date="2026-07-11",
            observations="User A notes",
        )
        DailyAnalyticsService(db, user_id=ub).save_journal(
            journal_date="2026-07-11",
            observations="User B notes",
        )
        ja = DailyAnalyticsService(db, user_id=ua)._get_journal(
            PaperTradingService(db, user_id=ua)._get_or_create_account().id,
            "2026-07-11",
        )
        jb = DailyAnalyticsService(db, user_id=ub)._get_journal(
            PaperTradingService(db, user_id=ub)._get_or_create_account().id,
            "2026-07-11",
        )
        assert ja["observations"] == "User A notes"
        assert jb["observations"] == "User B notes"
