"""Unit tests for AuthoritativeCandleStore.get_candles() multi-tier routing.

Spec: specs/020-authoritative-candle-store/spec.md
  FR-001 Single Ownership (disabled path)
  FR-002 Multi-Tier Resolution (L1 RAM -> L2 PostgreSQL -> L3 FYERS Provider Fetch)
  FR-005 Read Preference & Fallback

Task: T006 [P][US1] (tasks.md)

The store touches AsyncSessionLocal via _query_db_candles and invokes
FYERS via _fetch_provider_candles. Both are replaced with AsyncMock stubs so
this suite runs without a live database or broker connection.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from backend.app.config.settings import settings
from backend.app.schemas.analysis import OHLCVPoint
from backend.app.services.authoritative_candle_store import AuthoritativeCandleStore
from backend.app.services.l1_candle_cache import L1CandleCache


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_candle(idx: int, base: datetime | None = None) -> OHLCVPoint:
    base = base or datetime(2026, 1, 1, tzinfo=timezone.utc)
    ts = base + timedelta(days=idx)
    close = 100 + idx
    return OHLCVPoint(
        timestamp=ts,
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.5,
        close=close,
        volume=10_000 + idx,
    )


@pytest.fixture()
def candles() -> list[OHLCVPoint]:
    return [_make_candle(i) for i in range(5)]


@pytest.fixture()
def fresh_cache() -> L1CandleCache:
    return L1CandleCache(max_capacity=50)


@pytest.fixture(autouse=True)
def disable_flag():
    """Default flag state for the suite = OFF so each test opts in explicitly."""
    saved = settings.authoritative_candle_store_enabled
    object.__setattr__(settings, "authoritative_candle_store_enabled", False)
    # Ensure no env override leaks in
    import os
    saved_env = os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)
    yield
    object.__setattr__(settings, "authoritative_candle_store_enabled", saved)
    if saved_env is not None:
        os.environ["AUTHORITATIVE_CANDLE_STORE_ENABLED"] = saved_env


def _flag(value: bool) -> None:
    object.__setattr__(settings, "authoritative_candle_store_enabled", value)


def _make_store(cache: L1CandleCache) -> AuthoritativeCandleStore:
    """Build an AuthoritativeCandleStore with provider/db edges stubbed.

    DB query and FYERS fetch are AsyncMocks that tests configure per-case.
    """
    store = AuthoritativeCandleStore(cache=cache)
    store._query_db_candles = AsyncMock(return_value=[])  # type: ignore[assignment]
    store._fetch_provider_candles = AsyncMock(return_value=[])  # type: ignore[assignment]
    return store


# ===========================================================================
# FR-005: Feature Flag OFF routes to legacy fallback
# ===========================================================================

class TestFeatureFlagOffLegacyRouting:
    async def test_flag_off_calls_legacy_path(self, fresh_cache, candles):
        store = _make_store(fresh_cache)
        store._legacy_get_candles = AsyncMock(return_value=candles)  # type: ignore[assignment]
        _flag(False)

        out = await store.get_candles("RELIANCE-EQ", "1D")
        assert out == candles
        store._legacy_get_candles.assert_awaited_once()


# ===========================================================================
# FR-002 Tier 1: L1 In-Memory Cache hit
# ===========================================================================

class TestL1Hit:
    async def test_l1_hit_returns_cached_without_db_query(self, fresh_cache, candles):
        _flag(True)
        fresh_cache.set("RELIANCE-EQ", "1D", candles)
        store = _make_store(fresh_cache)

        out = await store.get_candles("RELIANCE-EQ", "1D")
        assert out == candles
        store._query_db_candles.assert_not_awaited()
        store._fetch_provider_candles.assert_not_awaited()

    async def test_symbol_normalized_before_l1_lookup(self, fresh_cache, candles):
        _flag(True)
        fresh_cache.set("RELIANCE-EQ", "1D", candles)
        store = _make_store(fresh_cache)

        out = await store.get_candles(" reliance-eq ", "d")
        assert out == candles


# ===========================================================================
# FR-002 Tier 2: DB hit fully covering range
# ===========================================================================

class TestL2DBHit:
    async def test_db_full_coverage_returns_validated_and_caches_l1(
        self, fresh_cache, candles
    ):
        _flag(True)
        store = _make_store(fresh_cache)
        store._query_db_candles.return_value = candles

        start, end = candles[0].timestamp, candles[-1].timestamp
        result = await store.get_candles("RELIANCE-EQ", "1D", start, end)

        assert result == candles
        store._fetch_provider_candles.assert_not_awaited()
        # L1 should now be populated
        assert fresh_cache.get("RELIANCE-EQ", "1D") == candles


# ===========================================================================
# FR-002 Tier 3: Provider fetch on partial / gap
# ===========================================================================

class TestL3ProviderGapFill:
    async def test_partial_db_coverage_triggers_provider_fetch(
        self, fresh_cache, candles, monkeypatch
    ):
        _flag(True)
        store = _make_store(fresh_cache)

        # DB only has first two candles; full request asks for all five.
        db_subset = candles[:2]
        provider_tail = candles[2:]
        store._query_db_candles.return_value = db_subset
        store._fetch_provider_candles.return_value = provider_tail

        # Suppress fire-and-forget ingest scheduling for this unit test
        tracked: list[asyncio.Task] = []
        real = asyncio.create_task

        def track(coro):
            t = real(coro)
            tracked.append(t)
            return t

        monkeypatch.setattr(
            "backend.app.services.authoritative_candle_store.asyncio.create_task",
            track,
        )

        start, end = candles[0].timestamp, candles[-1].timestamp
        out = await store.get_candles("RELIANCE-EQ", "1D", start, end)

        store._fetch_provider_candles.assert_awaited_once()
        assert out == candles
        # L1 cache populated with full merged continuous series
        assert fresh_cache.get("RELIANCE-EQ", "1D") == candles
        # Drain any pending ingest tasks to keep the event loop clean
        if tracked:
            await asyncio.gather(*tracked, return_exceptions=True)

    async def test_empty_db_and_empty_provider_returns_empty_list(self, fresh_cache):
        _flag(True)
        store = _make_store(fresh_cache)
        store._query_db_candles.return_value = []
        store._fetch_provider_candles.return_value = []

        out = await store.get_candles("RELIANCE-EQ", "1D",
                                      datetime(2026, 1, 1, tzinfo=timezone.utc),
                                      datetime(2026, 1, 10, tzinfo=timezone.utc))
        assert out == []

    async def test_force_provider_fetch_bypasses_l1_even_on_hit(
        self, fresh_cache, candles
    ):
        _flag(True)
        fresh_cache.set("RELIANCE-EQ", "1D", candles)
        store = _make_store(fresh_cache)
        store._query_db_candles.return_value = []
        store._fetch_provider_candles.return_value = candles

        out = await store.get_candles("RELIANCE-EQ", "1D", force_provider_fetch=True)
        store._fetch_provider_candles.assert_awaited_once()
        assert out == candles


# ===========================================================================
# Gap detection helper (FR-007)
# ===========================================================================

class TestHasDataGap:
    def _setup(self, fresh_cache):
        store = AuthoritativeCandleStore(cache=fresh_cache)
        return store

    def test_empty_series_is_gap(self, fresh_cache):
        assert self._setup(fresh_cache)._has_data_gap([], None, None) is True

    def test_head_missing_is_gap(self, fresh_cache, candles):
        s = self._setup(fresh_cache)
        assert s._has_data_gap(candles, candles[0].timestamp - timedelta(days=1), None) is True

    def test_tail_missing_is_gap(self, fresh_cache, candles):
        s = self._setup(fresh_cache)
        assert s._has_data_gap(candles, None, candles[-1].timestamp + timedelta(days=1)) is True

    def test_full_coverage_is_not_gap(self, fresh_cache, candles):
        s = self._setup(fresh_cache)
        assert s._has_data_gap(candles, candles[0].timestamp, candles[-1].timestamp) is False

    def test_no_bounds_existing_candles_is_not_gap(self, fresh_cache, candles):
        s = self._setup(fresh_cache)
        assert s._has_data_gap(candles, None, None) is False

    def test_interior_gap_detected_for_daily_series(self, fresh_cache):
        """C2: hole larger than weekend allowance triggers gap."""
        s = self._setup(fresh_cache)
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        series = [
            OHLCVPoint(timestamp=base, open=100, high=101, low=99, close=100, volume=1000),
            # 10-day hole ( > 5 day daily allowance)
            OHLCVPoint(
                timestamp=base + timedelta(days=10),
                open=110, high=111, low=109, close=110, volume=1000,
            ),
        ]
        assert s._has_data_gap(series, base, base + timedelta(days=10), "1D") is True
        windows = s._missing_windows(series, base, base + timedelta(days=10), "1D")
        assert any(w[0] == base and w[1] == base + timedelta(days=10) for w in windows) or len(windows) >= 1

    def test_lookback_covers_requested_range(self, fresh_cache):
        s = self._setup(fresh_cache)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 4, 1, tzinfo=timezone.utc)
        lookback = s._lookback_for_range(start, end, "1D")
        assert lookback >= 90  # ~90 calendar days + margin


# ===========================================================================
# DateTime parsing helper (used by FR-007 boundaries)
# ===========================================================================

class TestParseDateTime:
    def _setup(self, fresh_cache):
        return AuthoritativeCandleStore(cache=fresh_cache)

    def test_none_returns_none(self, fresh_cache):
        assert self._setup(fresh_cache)._parse_datetime(None) is None

    def test_aware_datetime_passthrough(self, fresh_cache):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert self._setup(fresh_cache)._parse_datetime(dt) == dt

    def test_naive_datetime_gets_utc(self, fresh_cache):
        out = self._setup(fresh_cache)._parse_datetime(datetime(2026, 1, 1))
        assert out.tzinfo is not None
        assert out.utcoffset() == timedelta(0)

    def test_iso_string_with_z(self, fresh_cache):
        out = self._setup(fresh_cache)._parse_datetime("2026-01-05T09:15:00Z")
        assert out.utcoffset() == timedelta(0)
        assert out == datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)

    def test_iso_string_with_offset(self, fresh_cache):
        out = self._setup(fresh_cache)._parse_datetime("2026-01-05T09:15:00+05:30")
        # Timezone-aware expected (not forcibly UTC-overridden for offset strings)
        assert out.tzinfo is not None

    def test_unsupported_type_returns_none(self, fresh_cache):
        assert self._setup(fresh_cache)._parse_datetime(12345) is None

    def test_string_iso_short_form(self, fresh_cache):
        out = self._setup(fresh_cache)._parse_datetime("2026-01-05")
        assert out == datetime(2026, 1, 5, tzinfo=timezone.utc)