"""Edge-case tests for Authoritative Candle Store components.

Testing.md: Edge Case Tests
  - Empty collections
  - Null / missing bounds
  - Duplicate requests
  - Large inputs (batch chunking > 500)
  - Boundary values

Spec: FR-003 batch chunking (max 500), FR-006 validation, FR-007 gap bounds.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.config.settings import settings
from backend.app.schemas.analysis import OHLCVPoint
from backend.app.services.authoritative_candle_store import AuthoritativeCandleStore
from backend.app.services.candle_validation_engine import (
    normalize_resolution,
    validate_candle_series,
    validate_ohlcv_point,
)
from backend.app.services.l1_candle_cache import L1CandleCache


def _candle(idx: int, base: datetime | None = None) -> OHLCVPoint:
    base = base or datetime(2026, 1, 1, tzinfo=timezone.utc)
    close = 100 + idx
    return OHLCVPoint(
        timestamp=base + timedelta(days=idx),
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.5,
        close=close,
        volume=max(0, 1000 + idx),
    )


@pytest.fixture(autouse=True)
def flag_on():
    saved = settings.authoritative_candle_store_enabled
    saved_env = os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)
    saved_dual = settings.candle_store_dual_write
    object.__setattr__(settings, "authoritative_candle_store_enabled", True)
    object.__setattr__(settings, "candle_store_dual_write", False)
    yield
    object.__setattr__(settings, "authoritative_candle_store_enabled", saved)
    object.__setattr__(settings, "candle_store_dual_write", saved_dual)
    if saved_env is not None:
        os.environ["AUTHORITATIVE_CANDLE_STORE_ENABLED"] = saved_env


# ===========================================================================
# Empty / null / missing
# ===========================================================================

class TestEmptyAndNullInputs:
    def test_validate_series_empty(self):
        assert validate_candle_series([]) == []

    def test_normalize_none_like_empty_string(self):
        assert normalize_resolution("") == "1D"

    def test_cache_get_missing_key_returns_none(self):
        cache = L1CandleCache(max_capacity=5)
        assert cache.get("NOPE-EQ", "1D") is None

    def test_cache_set_empty_is_noop(self):
        cache = L1CandleCache(max_capacity=5)
        cache.set("X-EQ", "1D", [])
        assert cache.size() == 0

    async def test_get_candles_no_bounds_with_l1_hit(self):
        cache = L1CandleCache(max_capacity=5)
        series = [_candle(i) for i in range(3)]
        cache.set("SYM-EQ", "1D", series)
        store = AuthoritativeCandleStore(cache=cache)
        store._query_db_candles = AsyncMock(return_value=[])  # type: ignore[assignment]
        out = await store.get_candles("SYM-EQ", "1D")  # no start/end
        assert out == series
        store._query_db_candles.assert_not_awaited()

    async def test_ingest_none_candles_via_empty_list(self):
        store = AuthoritativeCandleStore(cache=L1CandleCache(max_capacity=5))
        store._upsert_db_candles = AsyncMock(return_value=(0, 0))  # type: ignore[assignment]
        result = await store.ingest_candles("SYM-EQ", "1D", [])
        assert result.inserted_count == 0
        assert result.dual_write_status == "SKIPPED"


# ===========================================================================
# Boundary values
# ===========================================================================

class TestBoundaryValues:
    def test_zero_volume_accepted(self):
        raw = {
            "timestamp": "2026-01-01T00:00:00Z",
            "open": 100, "high": 100, "low": 100, "close": 100, "volume": 0,
        }
        out = validate_ohlcv_point(raw)
        assert out.volume == 0

    def test_flat_ohlc_all_equal_valid(self):
        raw = {
            "timestamp": "2026-01-01T00:00:00Z",
            "open": 50, "high": 50, "low": 50, "close": 50, "volume": 1,
        }
        out = validate_ohlcv_point(raw)
        assert out.high == 50 and out.low == 50

    def test_exact_start_end_boundary_is_l1_hit(self):
        cache = L1CandleCache(max_capacity=5)
        series = [_candle(i) for i in range(5)]
        cache.set("B-EQ", "1D", series)
        # Exact boundaries — inclusive coverage
        hit = cache.get(
            "B-EQ", "1D",
            start_date=series[0].timestamp,
            end_date=series[-1].timestamp,
        )
        assert hit == series

    def test_one_tick_beyond_end_is_l1_miss(self):
        cache = L1CandleCache(max_capacity=5)
        series = [_candle(i) for i in range(5)]
        cache.set("B-EQ", "1D", series)
        miss = cache.get(
            "B-EQ", "1D",
            end_date=series[-1].timestamp + timedelta(microseconds=1),
        )
        assert miss is None

    def test_parse_datetime_invalid_string_raises_or_handled(self):
        store = AuthoritativeCandleStore(cache=L1CandleCache(max_capacity=2))
        # fromisoformat raises ValueError for garbage — document current behavior
        with pytest.raises(ValueError):
            store._parse_datetime("not-a-date")


# ===========================================================================
# Duplicate requests / concurrent same-key
# ===========================================================================

class TestDuplicateRequests:
    async def test_duplicate_get_candles_served_from_l1(self):
        cache = L1CandleCache(max_capacity=10)
        series = [_candle(i) for i in range(4)]
        store = AuthoritativeCandleStore(cache=cache)
        store._query_db_candles = AsyncMock(return_value=series)  # type: ignore[assignment]
        store._fetch_provider_candles = AsyncMock(return_value=[])  # type: ignore[assignment]

        start, end = series[0].timestamp, series[-1].timestamp
        first = await store.get_candles("DUP-EQ", "1D", start, end)
        second = await store.get_candles("DUP-EQ", "1D", start, end)
        third = await store.get_candles("DUP-EQ", "1D", start, end)

        assert first == second == third
        # Only first call hits DB
        assert store._query_db_candles.await_count == 1

    async def test_duplicate_timestamps_in_ingest_payload_deduped(self):
        store = AuthoritativeCandleStore(cache=L1CandleCache(max_capacity=5))
        store._upsert_db_candles = AsyncMock(return_value=(1, 0))  # type: ignore[assignment]
        dup_ts = datetime(2026, 3, 1, tzinfo=timezone.utc)
        payload = [
            OHLCVPoint(timestamp=dup_ts, open=1, high=2, low=0.5, close=1.5, volume=10),
            OHLCVPoint(timestamp=dup_ts, open=1, high=3, low=0.5, close=2.0, volume=20),
        ]
        await store.ingest_candles("D-EQ", "1D", payload)
        upserted = store._upsert_db_candles.call_args.args[2]
        assert len(upserted) == 1


# ===========================================================================
# Large inputs — batch chunking (FR-003 max 500)
# ===========================================================================

class TestLargeBatchChunking:
    async def test_upsert_chunks_above_500_rows(self):
        """Verify _upsert_db_candles processes large series in 500-row chunks.

        We intercept session.execute to count chunk executions without a live DB.
        Each chunk now issues a pre-select + upsert (2 executes per chunk).
        """
        large = [_candle(i) for i in range(1200)]  # 3 chunks: 500 + 500 + 200
        store = AuthoritativeCandleStore(cache=L1CandleCache(max_capacity=5))

        execute_calls: list[int] = []

        class FakeResult:
            rowcount = 500

            def scalars(self):
                return self

            def all(self):
                return []  # no existing rows → all inserts

        class FakeSession:
            async def execute(self, stmt):
                execute_calls.append(1)
                return FakeResult()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        class FakeBegin:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, *a):
                return False

        class FakeSessionFactory:
            def __call__(self):
                return self

            async def __aenter__(self):
                sess = FakeSession()
                sess.begin = lambda: FakeBegin(sess)  # type: ignore[method-assign]
                return sess

            async def __aexit__(self, *a):
                return False

        from backend.app.services import authoritative_candle_store as mod

        with patch.object(mod, "AsyncSessionLocal", FakeSessionFactory()):
            inserted, updated = await store._upsert_db_candles(
                "BIG-EQ", "1D", large, source="FYERS"
            )

        # 1200 rows → 3 chunks × (preselect + upsert) = 6 executes
        assert len(execute_calls) == 6
        assert inserted == 1200
        assert updated == 0

    async def test_validate_large_unsorted_series(self):
        # 300 candles out of order — must sort + keep unique timestamps
        series = [_candle(i) for i in range(300)]
        reversed_series = list(reversed(series))
        out = validate_candle_series(reversed_series)
        assert len(out) == 300
        assert all(out[i].timestamp < out[i + 1].timestamp for i in range(299))


# ===========================================================================
# Whitespace / symbol normalization edge cases
# ===========================================================================

class TestSymbolNormalizationEdges:
    async def test_symbol_with_internal_spaces_only_stripped_ends(self):
        cache = L1CandleCache(max_capacity=5)
        series = [_candle(0)]
        cache.set("RELIANCE-EQ", "1D", series)
        store = AuthoritativeCandleStore(cache=cache)
        out = await store.get_candles("  RELIANCE-EQ  ", "1D")
        assert out == series

    def test_unknown_resolution_passthrough_preserves_custom(self):
        assert normalize_resolution("4H") == "4H"
