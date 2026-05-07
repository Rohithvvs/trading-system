import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.paper_trading import PaperTradingAccount, PaperPosition, PaperTradeHistory
from app.core.gap_replay import run_gap_replay
import app.core.server_state as server_state
import app.core.gap_replay as gr


class Candle:
    def __init__(self, timestamp, open_, high, low, close):
        # keep attribute names used by gap_replay
        self.timestamp = timestamp
        self.open = open_
        self.high = high
        self.low = low
        self.close = close


class FakeFyers:
    def __init__(self, candles):
        self.candles = candles

    def fetch_ohlcv(self, symbol, analysis_mode, interval, lookback_days, allow_mock=False):
        return self.candles


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    # create all tables for models that use `Base`
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return Session()


def write_last_shutdown(tmp_path: Path, last_shutdown: datetime):
    server_state.STATE_FILE = tmp_path / "server_state.json"
    server_state.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with server_state.STATE_FILE.open("w", encoding="utf-8") as fh:
        json.dump({"last_shutdown": last_shutdown.isoformat()}, fh)


def create_account_and_position(session, symbol="TEST-EQ", target=None, stop_loss=None):
    acc = PaperTradingAccount(name="TestAccount", starting_balance=100000.0, cash_balance=100000.0)
    session.add(acc)
    session.commit()
    session.refresh(acc)
    pos = PaperPosition(
        account_id=acc.id,
        status="OPEN",
        symbol=symbol,
        qty=1,
        avg_entry_price=100.0,
        current_price=100.0,
        target=target,
        stop_loss=stop_loss,
        notes="pytest",
    )
    session.add(pos)
    session.commit()
    session.refresh(pos)
    return acc, pos


def test_target_hit(tmp_path):
    session = make_session()
    acc, pos = create_account_and_position(session, symbol="TEST-EQ", target=120.0, stop_loss=None)

    now = datetime.now(timezone.utc)
    last_shutdown = now - timedelta(minutes=10)
    write_last_shutdown(tmp_path, last_shutdown)

    c1 = Candle(last_shutdown + timedelta(minutes=2), 101, 103, 100, 102)
    c2 = Candle(last_shutdown + timedelta(minutes=3), 104, 122, 103, 121)  # high 122 -> target hit

    fake = FakeFyers([c1, c2])

    # avoid timezone/market-hours complications in CI
    gr._is_market_hours = lambda dt: True

    summary = run_gap_replay(session, fake)

    th = (
        session.query(PaperTradeHistory)
        .filter(PaperTradeHistory.symbol == pos.symbol)
        .order_by(PaperTradeHistory.id.desc())
        .first()
    )
    assert th is not None, "Trade history should be created on target hit"
    assert th.exit_reason == "TARGET_HIT"
    assert pytest.approx(th.exit_price, rel=1e-5) == 120.0
    assert session.query(PaperPosition).filter(PaperPosition.symbol == pos.symbol).first() is None


def test_stoploss_hit(tmp_path):
    session = make_session()
    acc, pos = create_account_and_position(session, symbol="TEST-EQ", target=None, stop_loss=90.0)

    now = datetime.now(timezone.utc)
    last_shutdown = now - timedelta(minutes=10)
    write_last_shutdown(tmp_path, last_shutdown)

    c1 = Candle(last_shutdown + timedelta(minutes=2), 101, 101, 95, 100)
    c2 = Candle(last_shutdown + timedelta(minutes=3), 99, 100, 89, 90)  # low 89 -> stoploss hit

    fake = FakeFyers([c1, c2])
    gr._is_market_hours = lambda dt: True

    summary = run_gap_replay(session, fake)

    th = (
        session.query(PaperTradeHistory)
        .filter(PaperTradeHistory.symbol == pos.symbol)
        .order_by(PaperTradeHistory.id.desc())
        .first()
    )
    assert th is not None, "Trade history should be created on stoploss hit"
    assert th.exit_reason == "STOPLOSS_HIT"
    assert pytest.approx(th.exit_price, rel=1e-5) == 90.0
    assert session.query(PaperPosition).filter(PaperPosition.symbol == pos.symbol).first() is None


def test_both_hit_target_first(tmp_path):
    session = make_session()
    acc, pos = create_account_and_position(session, symbol="TEST-EQ", target=120.0, stop_loss=90.0)

    now = datetime.now(timezone.utc)
    last_shutdown = now - timedelta(minutes=10)
    write_last_shutdown(tmp_path, last_shutdown)

    # target hit earlier than stoploss
    c_target = Candle(last_shutdown + timedelta(minutes=2), 119, 120, 119, 120)
    c_stop = Candle(last_shutdown + timedelta(minutes=3), 91, 95, 89, 90)

    fake = FakeFyers([c_target, c_stop])
    gr._is_market_hours = lambda dt: True

    summary = run_gap_replay(session, fake)

    th = (
        session.query(PaperTradeHistory)
        .filter(PaperTradeHistory.symbol == pos.symbol)
        .order_by(PaperTradeHistory.id.desc())
        .first()
    )
    assert th is not None, "Trade history should be created when both hits occur"
    assert th.exit_reason == "TARGET_HIT", "Target should win when hit earlier than stoploss"
    assert pytest.approx(th.exit_price, rel=1e-5) == 120.0
    assert session.query(PaperPosition).filter(PaperPosition.symbol == pos.symbol).first() is None
