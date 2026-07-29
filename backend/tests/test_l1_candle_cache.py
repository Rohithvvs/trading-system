"""Unit tests for L1 In-Memory LRU Candle Cache and Candle Validation Engine.

Spec: specs/020-authoritative-candle-store/spec.md
  FR-002 Read Strategy (L1 in-memory cache hit/miss mechanics)
  FR-003 Write Strategy & Deduplication
  FR-006 Data Validation & Quality Enforcement (OHLC logic, monotonicity,
        non-negative volume, resolution normalization)

Task: T005 [P][US1] (tasks.md)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.app.schemas.analysis import OHLCVPoint
from backend.app.services.candle_validation_engine import (
    RESOLUTION_MAP,
    normalize_resolution,
    validate_candle_series,
    validate_ohlcv_point,
)
from backend.app.services.l1_candle_cache import L1CandleCache


# ---------------------------------------------------------------------------
# Test helpers
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
def cache() -> L1CandleCache:
    return L1CandleCache(max_capacity=3)


@pytest.fixture()
def candles() -> list[OHLCVPoint]:
    return [_make_candle(i) for i in range(5)]


# ===========================================================================
# L1 In-Memory Cache (FR-002)
# ===========================================================================

class TestL1CandleCacheHitMiss:
    def test_miss_returns_none_when_key_absent(self, cache: L1CandleCache):
        assert cache.get("INFY-EQ", "1D") is None

    def test_hit_returns_a_copy_of_cached_candles(self, cache: L1CandleCache, candles):
        cache.set("INFY-EQ", "1D", candles)
        out = cache.get("INFY-EQ", "1D")
        assert out == candles
        # Returned list must not mutate internal state
        out.append(_make_candle(99))
        assert cache.get("INFY-EQ", "1D") == candles

    def test_key_is_uppercased_and_resolution_normalized(self, cache: L1CandleCache, candles):
        cache.set("infy-eq", "d", candles)
        assert cache.get("INFY-EQ", "1D") == candles
        assert cache.get("infy-eq", "1d") == candles

    def test_empty_candle_list_is_not_cached(self, cache: L1CandleCache):
        cache.set("INFY-EQ", "1D", [])
        assert cache.size() == 0
        assert cache.get("INFY-EQ", "1D") is None


class TestL1CacheRangeCoverage:
    """L1 cache MUST only serve as a hit when it covers the requested window."""

    def test_head_partial_miss(self, cache: L1CandleCache, candles):
        cache.set("INFY-EQ", "1D", candles)
        start = candles[0].timestamp - timedelta(days=2)
        # First cached timestamp > start -> missing head range
        assert cache.get("INFY-EQ", "1D", start_date=start) is None

    def test_tail_partial_miss(self, cache: L1CandleCache, candles):
        cache.set("INFY-EQ", "1D", candles)
        end = candles[-1].timestamp + timedelta(days=2)
        assert cache.get("INFY-EQ", "1D", end_date=end) is None

    def test_full_range_covered_returns_candles(self, cache: L1CandleCache, candles):
        cache.set("INFY-EQ", "1D", candles)
        start = candles[0].timestamp
        end = candles[-1].timestamp
        assert cache.get("INFY-EQ", "1D", start_date=start, end_date=end) == candles

    def test_naive_boundary_datetimes_treated_as_utc(self, cache: L1CandleCache, candles):
        cache.set("INFY-EQ", "1D", candles)
        naive_start = candles[0].timestamp.replace(tzinfo=None)
        naive_end = candles[-1].timestamp.replace(tzinfo=None)
        assert cache.get("INFY-EQ", "1D", start_date=naive_start, end_date=naive_end) == candles


class TestL1LRUEviction:
    """Cache MUST evict least-recently-used when capacity is exceeded."""

    def test_capacity_bounded_eviction(self, cache: L1CandleCache, candles):
        # capacity = 3
        for idx in range(3):
            cache.set(f"SYM{idx}-EQ", "1D", candles)
        assert cache.size() == 3

        cache.set("NEW-EQ", "1D", candles)
        # SYM0 was LRU -> evicted, NEW inserted
        assert cache.size() == 3
        assert cache.get("SYM0-EQ", "1D") is None
        assert cache.get("NEW-EQ", "1D") == candles

    def test_access_reorders_lru(self, cache: L1CandleCache, candles):
        cache.set("A-EQ", "1D", candles)
        cache.set("B-EQ", "1D", candles)
        cache.set("C-EQ", "1D", candles)
        # Touch A so it is most-recently-used
        _ = cache.get("A-EQ", "1D")
        cache.set("D-EQ", "1D", candles)
        # B should now be the LRU -> evicted
        assert cache.get("B-EQ", "1D") is None
        assert cache.get("A-EQ", "1D") == candles

    def test_set_existing_key_does_not_grow_size(self, cache: L1CandleCache, candles):
        cache.set("A-EQ", "1D", candles)
        cache.set("A-EQ", "1D", candles)
        assert cache.size() == 1

    def test_set_existing_key_replaces_value(self, cache: L1CandleCache, candles):
        replacement = [_make_candle(i, base=datetime(2027, 1, 1, tzinfo=timezone.utc)) for i in range(3)]
        cache.set("A-EQ", "1D", candles)
        cache.set("A-EQ", "1D", replacement)
        assert cache.get("A-EQ", "1D") == replacement


class TestL1CacheLifecycle:
    def test_clear(self, cache: L1CandleCache, candles):
        cache.set("A-EQ", "1D", candles)
        cache.clear()
        assert cache.size() == 0
        assert cache.get("A-EQ", "1D") is None

    def test_size_reflects_distinct_symbol_resolution_keys(self, cache: L1CandleCache, candles):
        cache.set("A-EQ", "1D", candles)
        cache.set("A-EQ", "5m", candles)
        assert cache.size() == 2

    def test_default_capacity_is_2000(self):
        from backend.app.services.l1_candle_cache import l1_candle_cache
        assert l1_candle_cache.max_capacity == 2000


# ===========================================================================
# Candle Validation Engine (FR-006 / FR-003)
# ===========================================================================

class TestNormalizeResolution:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1D", "1D"),
            ("D", "1D"),
            ("1d", "1D"),
            ("day", "1D"),
            ("daily", "1D"),
            ("1m", "1m"),
            ("1", "1m"),
            ("5m", "5m"),
            ("5", "5m"),
            ("15m", "15m"),
            ("15", "15m"),
            ("30m", "30m"),
            ("60m", "60m"),
            ("1h", "60m"),
            ("  1D ", "1D"),
            ("DAILY", "1D"),
        ],
    )
    def test_canonical_mapping(self, raw: str, expected: str):
        assert normalize_resolution(raw) == expected

    def test_empty_resolution_defaults_to_1D(self):
        assert normalize_resolution("") == "1D"

    def test_unknown_resolution_passthrough_stripped(self):
        # Unknown values are returned trimmed (case preserved after trim/lower).
        assert normalize_resolution("2H") == "2H"

    def test_whole_mapping_table_has_no_collisions(self):
        # Sanity: every alias maps to a canonical value (non-empty and known).
        canonical_values = {"1D", "1m", "5m", "15m", "30m", "60m"}
        for v in RESOLUTION_MAP.values():
            assert v in canonical_values


class TestValidateOHLCVPoint:
    def test_dict_input_converted_to_ohlcv_point(self):
        raw = {
            "timestamp": "2026-01-05T09:15:00Z",
            "open": "100.5",
            "high": "102.0",
            "low": "100.0",
            "close": "101.0",
            "volume": "1234",
        }
        out = validate_ohlcv_point(raw)
        assert isinstance(out, OHLCVPoint)
        assert out.open == 100.5
        assert out.high == 102.0
        assert out.low == 100.0
        assert out.close == 101.0
        assert out.volume == 1234
        assert out.timestamp.tzinfo is not None

    def test_naive_datetime_input_gets_utc_timezone(self):
        raw = {
            "timestamp": datetime(2026, 1, 5, 9, 15),
            "open": 100, "high": 100, "low": 100, "close": 100, "volume": 10,
        }
        out = validate_ohlcv_point(raw)
        assert out.timestamp.tzinfo is not None
        assert out.timestamp.utcoffset() == timedelta(0)

    def test_ohlcv_point_input_naive_datetime_gets_utc(self):
        p = OHLCVPoint(
            timestamp=datetime(2026, 1, 1),
            open=10, high=11, low=9, close=10, volume=1,
        )
        out = validate_ohlcv_point(p)
        assert out.timestamp.tzinfo is not None

    def test_high_below_max_open_close_is_adjusted_up(self):
        # FR-006.2: High >= max(Open, Close). Invalid High auto-corrected upward.
        raw = {
            "timestamp": "2026-01-01T00:00:00",
            "open": 100, "high": 90, "low": 80, "close": 110, "volume": 10,
        }
        out = validate_ohlcv_point(raw)
        assert out.high == 110

    def test_low_above_min_open_close_is_adjusted_down(self):
        # FR-006.2: Low <= min(Open, Close). Invalid Low auto-corrected downward.
        raw = {
            "timestamp": "2026-01-01T00:00:00",
            "open": 100, "high": 110, "low": 105, "close": 95, "volume": 10,
        }
        out = validate_ohlcv_point(raw)
        assert out.low == 95

    def test_negative_volume_normalized_to_zero(self):
        # FR-006.3: Volume >= 0 enforced.
        raw = {
            "timestamp": "2026-01-01T00:00:00",
            "open": 100, "high": 101, "low": 99, "close": 100, "volume": -50,
        }
        out = validate_ohlcv_point(raw)
        assert out.volume == 0

    def test_ohlc_already_valid_unchanged(self):
        p = OHLCVPoint(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100, high=110, low=90, close=105, volume=1000,
        )
        out = validate_ohlcv_point(p)
        assert out == p


class TestValidateCandleSeries:
    def test_empty_series_returns_empty_list(self):
        assert validate_candle_series([]) == []

    def test_sorts_unsorted_series_chronologically(self):
        # FR-006.1: Timestamp monotonicity enforced via sort.
        later = _make_candle(5)
        earlier = _make_candle(0)
        out = validate_candle_series([later, earlier])
        assert out[0].timestamp < out[1].timestamp
        assert [c.timestamp for c in out] == sorted([c.timestamp for c in out])

    def test_duplicate_timestamps_are_deduplicated(self):
        # FR-003: Range deduplication in memory prior to persistence.
        c1 = OHLCVPoint(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100, high=110, low=90, close=100, volume=100,
        )
        c2 = OHLCVPoint(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100, high=115, low=85, close=105, volume=200,
        )
        out = validate_candle_series([c1, c2])
        assert len(out) == 1

    def test_ohlc_violations_in_series_drop_are_normalized(self):
        bad = OHLCVPoint(
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100, high=50, low=200, close=110, volume=-5,
        )
        out = validate_candle_series([bad])
        assert out[0].high == 110
        assert out[0].low == 100
        assert out[0].volume == 0

    def test_mixed_dict_and_object_inputs_accepted(self):
        mixed = [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10,
            },
            OHLCVPoint(
                timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
                open=100, high=101, low=99, close=100, volume=10,
            ),
        ]
        out = validate_candle_series(mixed)
        assert len(out) == 2
        assert out[0].timestamp < out[1].timestamp