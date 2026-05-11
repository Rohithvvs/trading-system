from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.app.schemas import AnalysisMode
from backend.app.services import candle_store
from backend.app.services.fyers_service import FyersService


@pytest.mark.unit
def test_daily_cache_reused_when_latest_completed_session_is_present(monkeypatch, tmp_path):
    monkeypatch.setattr(candle_store, "DB_PATH", str(tmp_path / "candle_cache.db"))
    candle_store.init_db()

    end_date = datetime(2026, 5, 15, tzinfo=timezone.utc)
    rows = []
    for offset in range(260):
        day = end_date - timedelta(days=259 - offset)
        rows.append(
            {
                "date": day.date().isoformat(),
                "open": 100 + offset,
                "high": 101 + offset,
                "low": 99 + offset,
                "close": 100 + offset,
                "volume": 100000 + offset,
            }
        )
    candle_store.store_candles("INFY", pd.DataFrame(rows))

    with sqlite3.connect(candle_store.DB_PATH) as conn:
        conn.execute("UPDATE candles SET fetched_at = ?", ("2026-05-10T00:00:00+00:00",))
        conn.commit()

    monkeypatch.setattr(
        candle_store,
        "get_latest_completed_market_session_date",
        lambda reference_date=None: "2026-05-15",
    )
    fetch_calls: list[tuple] = []
    service = FyersService()
    monkeypatch.setattr(
        service,
        "_fetch_fyers_candles",
        lambda *args, **kwargs: fetch_calls.append((args, kwargs)) or [],
    )

    candles = service.get_candles_cached("INFY-EQ", AnalysisMode.swing, "1d", 260)

    assert len(candles) == 260
    assert fetch_calls == []
    assert service.get_ohlcv_source("INFY-EQ", AnalysisMode.swing, "1d") == "CANDLE_CACHE_DB"


@pytest.mark.unit
def test_incomplete_daily_cache_triggers_fallback(monkeypatch, tmp_path):
    # Setup a small/incomplete DB cache (fewer than required points)
    monkeypatch.setattr(candle_store, "DB_PATH", str(tmp_path / "candle_cache.db"))
    candle_store.init_db()

    end_date = datetime(2026, 5, 15, tzinfo=timezone.utc)
    # Create fewer rows than the required 260 points
    rows = []
    for offset in range(200):
        day = end_date - timedelta(days=199 - offset)
        rows.append(
            {
                "date": day.date().isoformat(),
                "open": 100 + offset,
                "high": 101 + offset,
                "low": 99 + offset,
                "close": 100 + offset,
                "volume": 100000 + offset,
            }
        )
    candle_store.store_candles("INFY", pd.DataFrame(rows))

    # Mark fetched_at older so freshness-check alone won't block reuse;
    # monkeypatch latest completed session to force the has_completed_daily_session path
    with sqlite3.connect(candle_store.DB_PATH) as conn:
        conn.execute("UPDATE candles SET fetched_at = ?", ("2026-05-10T00:00:00+00:00",))
        conn.commit()

    monkeypatch.setattr(
        candle_store,
        "get_latest_completed_market_session_date",
        lambda reference_date=None: "2026-05-15",
    )

    fetch_calls: list[tuple] = []
    service = FyersService()

    # Simulate FYERS fetch returning a complete set of candles (260 points)
    def fake_fetch(*args, **kwargs):
        fetch_calls.append((args, kwargs))
        fetched = []
        for i in range(260):
            day = end_date - timedelta(days=259 - i)
            fetched.append(
                SimpleNamespace(
                    timestamp=day,
                    open=100 + i,
                    high=101 + i,
                    low=99 + i,
                    close=100 + i,
                    volume=100000 + i,
                )
            )
        return fetched

    monkeypatch.setattr(service, "_fetch_fyers_candles", fake_fetch)

    candles = service.get_candles_cached("INFY-EQ", AnalysisMode.swing, "1d", 260)

    # Verify fallback was used and FYERS fetch invoked
    assert len(candles) == 260
    assert fetch_calls != []
    assert service.get_ohlcv_source("INFY-EQ", AnalysisMode.swing, "1d") == "FYERS_PRIMARY"
