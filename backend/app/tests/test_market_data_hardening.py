import pytest
import asyncio
import pandas as pd
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, patch
from sqlalchemy.exc import OperationalError
from app.services.market_data_service import MarketDataService


@pytest.fixture
def md_service():
    return MarketDataService()


@pytest.fixture
def sample_candles_df():
    now = datetime.now(timezone.utc)
    dates = [now - timedelta(days=i) for i in range(5)]
    df = pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104],
            "high": [105, 106, 107, 108, 109],
            "low": [95, 96, 97, 98, 99],
            "close": [102, 103, 104, 105, 106],
            "volume": [1000, 1100, 1200, 1300, 1400],
        },
        index=dates,
    )
    return df


@pytest.mark.asyncio
async def test_concurrent_upserts(md_service, sample_candles_df, monkeypatch):
    """
    Concurrent multi-upserts complete without sharing a session and respect
    the writer concurrency cap.
    """
    active = {"n": 0}
    peak = {"n": 0}
    calls = {"n": 0}

    async def stub_upsert(symbol, timeframe, df):
        calls["n"] += 1
        active["n"] += 1
        peak["n"] = max(peak["n"], active["n"])
        await asyncio.sleep(0.02)
        active["n"] -= 1

    monkeypatch.setattr(md_service, "upsert_candles", stub_upsert)

    frames = [
        (f"SYM{i}", "1D", sample_candles_df.copy()) for i in range(10)
    ]
    written = await md_service.upsert_candles_multi(frames)
    assert written == 10
    assert calls["n"] == 10
    assert peak["n"] <= 4
    assert peak["n"] >= 2


def test_stale_data_detection(md_service):
    """
    Test that check_stale_candles correctly identifies stale data.
    """
    with patch("app.services.market_data_service.logger") as mock_logger:
        # 1D threshold is > 2 days
        stale_date = datetime.now(timezone.utc) - timedelta(days=3)
        md_service.check_stale_candles("TCS", "1D", stale_date)

        mock_logger.warning.assert_called_with(
            "stale_candle_detected", extra=unittest.mock.ANY
        )


@pytest.mark.asyncio
async def test_retry_exhaustion(md_service, monkeypatch):
    """
    OperationalError / lock-style failures retry then re-raise after exhaustion.
    Exercises _upsert_chunk (direct path) so ACS routing is not involved.
    """
    attempts = {"n": 0}

    class _FailingBegin:
        async def __aenter__(self):
            attempts["n"] += 1
            raise OperationalError("database is locked", None, None)

        async def __aexit__(self, *args):
            return False

    class _FailingSession:
        def begin(self):
            return _FailingBegin()

        async def close(self):
            return None

        async def rollback(self):
            return None

    class _Scope:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return _FailingSession()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(
        "app.services.market_data_service.session_scope",
        lambda *a, **k: _Scope(),
    )
    monkeypatch.setattr("app.services.market_data_service.asyncio.sleep", AsyncMock())

    records = [
        {
            "symbol": "INFY",
            "resolution": "1D",
            "timestamp": datetime.now(timezone.utc),
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1,
        }
    ]

    with patch("app.services.market_data_service.logger") as mock_logger:
        with pytest.raises(OperationalError):
            await md_service._upsert_chunk("INFY", "1D", records)

        assert attempts["n"] >= 5
        assert mock_logger.warning.call_count >= 4
