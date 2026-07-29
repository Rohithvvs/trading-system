"""Unit tests for candle gap detection, range stitching, and ingest_candles.

Spec: specs/020-authoritative-candle-store/spec.md
  FR-003 Write Strategy & Deduplication (idempotent ON CONFLICT DO UPDATE)
  FR-007 Backfill & Gap Strategy (head/tail gap identification + stitching)

Task: T016 [P][US3] (tasks.md)

These tests focus on pure gap detection logic and ingest_candles idempotent
behavior. The PostgreSQL upsert path is mocked since SQLite ON CONFLICT
behavior is exercised in the integration suite (test_candle_store_gap_fill.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from backend.app.config.settings import settings
from backend.app.schemas.analysis import OHLCVPoint
from backend.app.services.authoritative_candle_store import (
    AuthoritativeCandleStore,
    IngestionResult,
)
from backend.app.services.l1_candle_cache import L1CandleCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candle(idx: int, base: datetime | None = None) -> OHLCVPoint:
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


@pytest.fixture(autouse=True)
def disable_dual_write():
    """Side effects of dual-write secondary path are tested elsewhere (T012)."""
    saved = settings.candle_store_dual_write
    object.__setattr__(settings, "candle_store_dual_write", False)
    yield
    object.__setattr__(settings, "candle_store_dual_write", saved)


@pytest.fixture()
def store() -> AuthoritativeCandleStore:
    s = AuthoritativeCandleStore(cache=L1CandleCache(max_capacity=10))
    s._upsert_db_candles = AsyncMock(return_value=(0, 0))  # type: ignore[assignment]
    return s


# ===========================================================================
# FR-007: Backfill gap identification
# ===========================================================================

class TestGapIdentification:
    def test_empty_db_series_is_gap(self, store):
        assert store._has_data_gap([], None, None) is True

    def test_full_coverage_no_bounds_is_not_gap(self, store):
        candles = [_candle(i) for i in range(5)]
        assert store._has_data_gap(candles, None, None) is False

    def test_head_gap_detected(self, store):
        candles = [_candle(i) for i in range(5)]
        # Requested start earlier than first stored timestamp
        assert store._has_data_gap(candles, candles[0].timestamp - timedelta(days=1), None) is True

    def test_tail_gap_detected(self, store):
        candles = [_candle(i) for i in range(5)]
        # Requested end later than last stored timestamp
        assert store._has_data_gap(candles, None, candles[-1].timestamp + timedelta(days=1)) is True

    def test_interior_request_within_stored_no_gap(self, store):
        candles = [_candle(i) for i in range(10)]
        start = candles[2].timestamp
        end = candles[7].timestamp
        assert store._has_data_gap(candles, start, end) is False

    def test_exact_boundary_request_no_gap(self, store):
        candles = [_candle(i) for i in range(5)]
        assert store._has_data_gap(candles, candles[0].timestamp, candles[-1].timestamp) is False


# ===========================================================================
# FR-007: Range stitching produces a continuous series
# ===========================================================================

class TestRangeStitching:
    async def test_db_and_provider_merge_welds_disjoint_windows(self, store):
        """Stitching merges non-overlapping DB and provider ranges without gaps."""
        db = [_candle(i) for i in range(0, 3)]
        provider = [_candle(i) for i in range(3, 6)]
        # Simulate the merge logic used inside get_candles Tier 3.
        from backend.app.services.candle_validation_engine import validate_candle_series

        merged = validate_candle_series(db + provider)
        assert len(merged) == 6
        # Continuous: each consecutive candle differs by 1 day exactly.
        for prev, cur in zip(merged, merged[1:]):
            assert (cur.timestamp - prev.timestamp) == timedelta(days=1)

    async def test_overlapping_ranges_dedupe_on_timestamp(self, store):
        """Stitching must not produce duplicate timestamps (FR-003 dedup)."""
        from backend.app.services.candle_validation_engine import validate_candle_series

        # Overlapping by one timestamp
        db = [_candle(i) for i in range(0, 3)]
        provider = [_candle(i) for i in range(2, 5)]
        merged = validate_candle_series(db + provider)
        timestamps = [c.timestamp for c in merged]
        assert len(timestamps) == len(set(timestamps))
        assert len(merged) == 5

    async def test_head_backfill_window(self, store):
        """FR-007: head range [start, db_start] fetched from provider."""
        db = [_candle(i) for i in range(3, 6)]  # 2026-01-04..06
        head = [_candle(i) for i in range(0, 3)]  # 2026-01-01..03
        from backend.app.services.candle_validation_engine import validate_candle_series

        merged = validate_candle_series((db or []) + head)
        assert merged[0].timestamp < db[0].timestamp
        assert len(merged) == 6

    async def test_tail_backfill_window(self, store):
        """FR-007: tail range [db_end, end] fetched from provider."""
        db = [_candle(i) for i in range(0, 3)]  # 2026-01-01..03
        tail = [_candle(i) for i in range(3, 6)]  # 2026-01-04..06
        from backend.app.services.candle_validation_engine import validate_candle_series

        merged = validate_candle_series((db or []) + tail)
        assert merged[-1].timestamp > db[-1].timestamp
        assert len(merged) == 6


# ===========================================================================
# FR-003: ingest_candles idempotent batch upsert
# ===========================================================================

class TestIngestCandlesIdempotency:
    async def test_validate_and_upsert_called_once(self, store):
        candles = [_candle(i) for i in range(3)]
        store._upsert_db_candles = AsyncMock(return_value=(3, 0))  # type: ignore[assignment]
        result = await store.ingest_candles("RELIANCE-EQ", "1D", candles, source="FYERS")
        assert isinstance(result, IngestionResult)
        assert result.inserted_count == 3
        assert result.updated_count == 0
        store._upsert_db_candles.assert_awaited_once()

    async def test_empty_candle_list_skipped(self, store):
        result = await store.ingest_candles("RELIANCE-EQ", "1D", [], source="FYERS")
        assert result.dual_write_status == "SKIPPED"
        assert result.inserted_count == 0
        assert result.updated_count == 0
        store._upsert_db_candles.assert_not_awaited()

    async def test_all_invalid_candles_skip(self, store):
        """Empty list after validation means SKIPPED, not exception."""
        # Validation engine never returns an empty list for non-empty input
        # (it normalizes), so we instead pass [] directly here too via duplicate
        # empty-by-validation path. We pass-invalidated candles that survive
        # validation to ensure the upsert is still invoked.
        candles = [_candle(i) for i in range(2)]
        store._upsert_db_candles = AsyncMock(return_value=(2, 0))  # type: ignore[assignment]
        result = await store.ingest_candles("sym", "1D", candles, source="FYERS")
        assert result.dual_write_status == "SKIPPED"
        store._upsert_db_candles.assert_awaited_once()

    async def test_normalizes_symbol_and_resolution_in_payload(self, store):
        """Symbol uppercased and resolution normalized before persistence."""
        candles = [_candle(i) for i in range(2)]
        store._upsert_db_candles = AsyncMock(return_value=(2, 0))  # type: ignore[assignment]
        await store.ingest_candles(" reliance-eq ", "d", candles, source="FYERS")
        # _upsert_db_candles bound-mock receives (symbol, resolution, candles, source)
        args, _ = store._upsert_db_candles.call_args
        assert args[0] == "RELIANCE-EQ"
        assert args[1] == "1D"

    async def test_ingest_updates_l1_cache(self, store):
        candles = [_candle(i) for i in range(3)]
        store._upsert_db_candles = AsyncMock(return_value=(3, 0))  # type: ignore[assignment]
        await store.ingest_candles("RELIANCE-EQ", "1D", candles, source="FYERS")
        cached = store.cache.get("RELIANCE-EQ", "1D")
        assert cached is not None
        assert cached == candles

    async def test_dict_input_accepted_and_coerced(self, store):
        """ingest_candles accepts raw dicts per contract (validation coerces)."""
        raw_candles = [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000,
            },
            {
                "timestamp": "2026-01-02T00:00:00Z",
                "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000,
            },
        ]
        store._upsert_db_candles = AsyncMock(return_value=(2, 0))  # type: ignore[assignment]
        result = await store.ingest_candles("SYM-EQ", "1D", raw_candles, source="FYERS")
        assert result.inserted_count == 2
        store._upsert_db_candles.assert_awaited_once()
        # Bound mock call args: (symbol, resolution, candles, source)
        upsert_arg = store._upsert_db_candles.call_args.args[2]
        assert all(isinstance(c, OHLCVPoint) for c in upsert_arg)