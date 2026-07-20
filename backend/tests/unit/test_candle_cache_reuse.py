from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from backend.app.schemas import AnalysisMode, OHLCVPoint
from backend.app.services.fyers_service import FyersService


def _frame(rows: int, end_date: datetime) -> pd.DataFrame:
    data = []
    for offset in range(rows):
        day = end_date - timedelta(days=rows - 1 - offset)
        data.append(
            {
                "date": day,
                "open": 100 + offset,
                "high": 101 + offset,
                "low": 99 + offset,
                "close": 100 + offset,
                "volume": 100000 + offset,
            }
        )
    return pd.DataFrame(data)


@pytest.mark.asyncio
async def test_daily_cache_reused_when_latest_completed_session_is_present(monkeypatch):
    end_date = datetime(2026, 5, 15, tzinfo=timezone.utc)
    service = FyersService()

    monkeypatch.setattr(
        "backend.app.services.candle_store.is_cache_fresh",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "backend.app.services.candle_store.has_completed_daily_session",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "backend.app.services.candle_store.get_candle_count",
        AsyncMock(return_value=260),
    )
    monkeypatch.setattr(
        "backend.app.services.candle_store.load_candles",
        AsyncMock(return_value=_frame(260, end_date)),
    )

    fetch_calls: list[tuple] = []

    async def fake_fetch(*args, **kwargs):
        fetch_calls.append((args, kwargs))
        return []

    monkeypatch.setattr(service, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(service, "_fetch_fyers_candles", lambda *a, **k: fetch_calls.append((a, k)) or [])

    candles = await service.get_candles_cached("INFY-EQ", AnalysisMode.swing, "1d", 260)

    assert len(candles) == 260
    assert fetch_calls == []
    assert service.get_ohlcv_source("INFY-EQ", AnalysisMode.swing, "1d") == "CANDLE_CACHE_DB"


@pytest.mark.asyncio
async def test_incomplete_daily_cache_triggers_fallback(monkeypatch):
    end_date = datetime(2026, 5, 15, tzinfo=timezone.utc)
    service = FyersService()

    monkeypatch.setattr(
        "backend.app.services.candle_store.is_cache_fresh",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "backend.app.services.candle_store.has_completed_daily_session",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "backend.app.services.candle_store.get_candle_count",
        AsyncMock(return_value=200),
    )
    monkeypatch.setattr(
        "backend.app.services.candle_store.get_last_stored_date",
        AsyncMock(return_value="2026-05-10"),
    )
    monkeypatch.setattr(
        "backend.app.services.candle_store.store_candles",
        AsyncMock(return_value=None),
    )

    fetch_calls: list[tuple] = []

    def fake_fetch_fyers(*args, **kwargs):
        fetch_calls.append((args, kwargs))
        out: list[OHLCVPoint] = []
        for i in range(260):
            day = end_date - timedelta(days=259 - i)
            out.append(
                OHLCVPoint(
                    timestamp=day,
                    open=100 + i,
                    high=101 + i,
                    low=99 + i,
                    close=100 + i,
                    volume=100000 + i,
                )
            )
        return out

    monkeypatch.setattr(service, "_fetch_fyers_candles", fake_fetch_fyers)

    candles = await service.get_candles_cached("INFY-EQ", AnalysisMode.swing, "1d", 260)

    assert len(candles) == 260
    assert fetch_calls != []
    assert service.get_ohlcv_source("INFY-EQ", AnalysisMode.swing, "1d") == "FYERS_PRIMARY"
