"""Failure-path tests for Authoritative Candle Store.

Spec: specs/020-authoritative-candle-store/spec.md §11 Failure Handling
  - Provider API timeout / exception → best-available path (empty provider list)
  - Primary DB write failure → non-blocking; returns (0, 0)
  - DB query failure → returns []
  - Legacy path failure → falls back to provider fetch
  - L1 cache clear rebuilds on next request (self-healing)

Testing.md: Failure Path Tests (exceptions, DB failures, external dependency failures).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.config.settings import settings
from backend.app.schemas.analysis import OHLCVPoint
from backend.app.services.authoritative_candle_store import AuthoritativeCandleStore
from backend.app.services.l1_candle_cache import L1CandleCache


def _candles(n: int = 3) -> list[OHLCVPoint]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        OHLCVPoint(
            timestamp=base + timedelta(days=i),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100 + i,
            volume=10_000 + i,
        )
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def flag_on():
    saved = settings.authoritative_candle_store_enabled
    saved_env = os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)
    object.__setattr__(settings, "authoritative_candle_store_enabled", True)
    yield
    object.__setattr__(settings, "authoritative_candle_store_enabled", saved)
    if saved_env is not None:
        os.environ["AUTHORITATIVE_CANDLE_STORE_ENABLED"] = saved_env
    else:
        os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)


@pytest.fixture()
def cache() -> L1CandleCache:
    return L1CandleCache(max_capacity=10)


# ===========================================================================
# Provider failures
# ===========================================================================

class TestProviderFailurePaths:
    async def test_provider_exception_returns_empty_merged_when_db_empty(self, cache, monkeypatch):
        async def _no_sleep(_):
            return None

        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        failing_fyers = MagicMock()
        failing_fyers.fetch_ohlcv = AsyncMock(side_effect=TimeoutError("timeout > 3s"))
        store = AuthoritativeCandleStore(cache=cache, fyers_service=failing_fyers)
        store._query_db_candles = AsyncMock(return_value=[])  # type: ignore[assignment]

        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 5, tzinfo=timezone.utc)
        out = await store.get_candles("RELIANCE-EQ", "1D", start, end)
        assert out == []
        assert failing_fyers.fetch_ohlcv.await_count == 3  # retries exhausted

    async def test_provider_failure_still_returns_db_candles_when_partial(self, cache, monkeypatch):
        """When provider fails, best-available DB series is returned (allow_fallback)."""
        async def _no_sleep(_):
            return None

        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        db = _candles(2)
        failing_fyers = MagicMock()
        failing_fyers.fetch_ohlcv = AsyncMock(side_effect=TimeoutError("timeout"))
        store = AuthoritativeCandleStore(cache=cache, fyers_service=failing_fyers)
        store._query_db_candles = AsyncMock(return_value=db)  # type: ignore[assignment]

        # Request end beyond DB tail so gap is detected and provider is attempted
        start = db[0].timestamp
        end = db[-1].timestamp + timedelta(days=5)
        out = await store.get_candles("RELIANCE-EQ", "1D", start, end)
        # Best-available: validated DB candles (provider returned [])
        assert len(out) == 2
        assert out[0].timestamp == db[0].timestamp


# ===========================================================================
# Database failures
# ===========================================================================

class TestDatabaseFailurePaths:
    async def test_db_query_exception_treated_as_empty_series(self, cache):
        """_query_db_candles swallows exceptions and returns []."""
        store = AuthoritativeCandleStore(cache=cache)
        # Force the real path to raise inside the try by breaking session factory
        store._query_db_candles = AsyncMock(side_effect=RuntimeError("db down"))  # type: ignore[assignment]
        # When get_candles calls _query_db_candles and it raises, the exception
        # would propagate unless the real method catches it. The production
        # method catches Exception — so we exercise the real method via a
        # patched AsyncSessionLocal that raises.
        from backend.app.services import authoritative_candle_store as mod

        class BoomSession:
            async def __aenter__(self):
                raise ConnectionError("postgres unavailable")

            async def __aexit__(self, *a):
                return False

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(mod, "AsyncSessionLocal", lambda: BoomSession())
        try:
            store2 = AuthoritativeCandleStore(cache=cache)
            store2._fetch_provider_candles = AsyncMock(return_value=_candles())  # type: ignore[assignment]
            out = await store2.get_candles(
                "SYM-EQ",
                "1D",
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 3, tzinfo=timezone.utc),
            )
            # DB empty due to error → provider backfill path used
            assert len(out) == 3
        finally:
            monkeypatch.undo()

    async def test_upsert_exception_returns_zero_counts_without_raising(self, cache):
        from backend.app.services import authoritative_candle_store as mod

        class BoomSession:
            async def __aenter__(self):
                raise ConnectionError("write lock failure")

            async def __aexit__(self, *a):
                return False

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(mod, "AsyncSessionLocal", lambda: BoomSession())
        try:
            object.__setattr__(settings, "candle_store_dual_write", False)
            store = AuthoritativeCandleStore(cache=cache)
            result = await store.ingest_candles("SYM-EQ", "1D", _candles(), source="FYERS")
            assert result.inserted_count == 0
            assert result.updated_count == 0
            # L1 still updated even if DB write failed (non-blocking consumer path)
            assert store.cache.get("SYM-EQ", "1D") is not None
        finally:
            monkeypatch.undo()


# ===========================================================================
# Legacy path failures
# ===========================================================================

class TestLegacyFailurePaths:
    async def test_legacy_market_data_failure_falls_back_to_provider(self, cache):
        object.__setattr__(settings, "authoritative_candle_store_enabled", False)
        os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)

        broken_mds = MagicMock()
        broken_mds.get_candles = AsyncMock(side_effect=RuntimeError("legacy broken"))
        ok_provider = MagicMock()
        ok_provider.fetch_ohlcv = AsyncMock(return_value=_candles())

        store = AuthoritativeCandleStore(
            cache=cache,
            market_data_service=broken_mds,
            fyers_service=ok_provider,
        )
        out = await store.get_candles("RELIANCE-EQ", "1D")
        assert len(out) == 3
        ok_provider.fetch_ohlcv.assert_awaited()


# ===========================================================================
# L1 cache self-healing (corruption / clear)
# ===========================================================================

class TestL1SelfHealing:
    async def test_cleared_cache_rebuilds_from_db_on_next_read(self, cache):
        series = _candles()
        cache.set("RELIANCE-EQ", "1D", series)
        assert cache.get("RELIANCE-EQ", "1D") is not None

        # Simulate corruption recovery: clear affected entries
        cache.clear()
        assert cache.get("RELIANCE-EQ", "1D") is None

        store = AuthoritativeCandleStore(cache=cache)
        store._query_db_candles = AsyncMock(return_value=series)  # type: ignore[assignment]
        store._fetch_provider_candles = AsyncMock(return_value=[])  # type: ignore[assignment]

        start, end = series[0].timestamp, series[-1].timestamp
        out = await store.get_candles("RELIANCE-EQ", "1D", start, end)
        assert out == series
        # Rebuilt into L1
        assert cache.get("RELIANCE-EQ", "1D") == series
        store._query_db_candles.assert_awaited_once()
