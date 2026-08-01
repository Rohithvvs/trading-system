"""Unit tests for FR-008 Automated Consistency Checks (validate_consistency).

Spec: specs/020-authoritative-candle-store/spec.md
  FR-008: Background audit sample-checks stored series against provider snapshots.
          Discrepancies exceeding price difference trigger automated repair.
  Section 17.1 / Failure Handling: Data mismatch auto-remediation.

Task coverage (Testing.md gap fill for Sprint 4).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from backend.app.schemas.analysis import OHLCVPoint
from backend.app.services.authoritative_candle_store import (
    AuditReport,
    AuthoritativeCandleStore,
)
from backend.app.services.l1_candle_cache import L1CandleCache


def _candle(
    idx: int,
    *,
    close: float | None = None,
    base: datetime | None = None,
) -> OHLCVPoint:
    base = base or datetime(2026, 1, 1, tzinfo=timezone.utc)
    ts = base + timedelta(days=idx)
    c = 100.0 + idx if close is None else close
    return OHLCVPoint(
        timestamp=ts,
        open=c - 0.5,
        high=c + 1.0,
        low=c - 1.5,
        close=c,
        volume=10_000 + idx,
    )


@pytest.fixture()
def store() -> AuthoritativeCandleStore:
    s = AuthoritativeCandleStore(cache=L1CandleCache(max_capacity=20))
    s._query_db_candles = AsyncMock(return_value=[])  # type: ignore[assignment]
    s._fetch_provider_candles = AsyncMock(return_value=[])  # type: ignore[assignment]
    s.ingest_candles = AsyncMock(  # type: ignore[method-assign]
        return_value=type(
            "R",
            (),
            {
                "symbol": "X",
                "resolution": "1D",
                "inserted_count": 0,
                "updated_count": 0,
                "dual_write_status": "SKIPPED",
            },
        )()
    )
    return s


class TestValidateConsistencyMatch:
    async def test_matching_close_prices_count_as_matched(self, store):
        series = [_candle(i) for i in range(5)]
        store._query_db_candles.return_value = series
        store._fetch_provider_candles.return_value = series

        report = await store.validate_consistency(["RELIANCE-EQ"], "1D", sample_ratio=1.0)

        assert isinstance(report, AuditReport)
        assert report.total_audited == 1
        assert report.matched_count == 1
        assert report.mismatched_count == 0
        assert report.repaired_count == 0
        assert report.discrepancies == []
        store.ingest_candles.assert_not_awaited()

    async def test_close_diff_within_relative_threshold_is_match(self, store):
        """FR-008: relative threshold 0.01% — 0.005% drift is a match."""
        db = [_candle(0, close=100.00)]
        # abs(100.005-100)/100 = 0.005% < 0.01%
        prov = [_candle(0, close=100.005)]
        store._query_db_candles.return_value = db
        store._fetch_provider_candles.return_value = prov

        report = await store.validate_consistency(["INFY-EQ"], "1D", sample_ratio=1.0)
        assert report.matched_count == 1
        assert report.mismatched_count == 0
        store.ingest_candles.assert_not_awaited()


class TestValidateConsistencyMismatchRepair:
    async def test_mismatched_close_triggers_repair_ingest(self, store):
        db = [_candle(0, close=100.00)]
        # 0.10% relative drift >> 0.01% threshold
        prov = [_candle(0, close=100.10)]
        store._query_db_candles.return_value = db
        store._fetch_provider_candles.return_value = prov

        report = await store.validate_consistency(["TCS-EQ"], "1D", sample_ratio=1.0)

        assert report.matched_count == 0
        assert report.mismatched_count == 1
        assert report.repaired_count == 1
        assert len(report.discrepancies) == 1
        disc = report.discrepancies[0]
        assert disc["symbol"] == "TCS-EQ"
        assert disc["db_close"] == pytest.approx(100.0)
        assert disc["provider_close"] == pytest.approx(100.1)
        store.ingest_candles.assert_awaited_once()
        # Repair uses provider candles as source of truth
        args, kwargs = store.ingest_candles.call_args
        assert args[0] == "TCS-EQ"
        assert args[1] == "1D"
        assert kwargs.get("source") == "REPAIR_AUDIT" or (
            len(args) >= 4 and args[3] == "REPAIR_AUDIT"
        )


class TestValidateConsistencyEdgeCases:
    async def test_empty_db_skips_symbol_without_error(self, store):
        store._query_db_candles.return_value = []
        store._fetch_provider_candles.return_value = [_candle(0)]

        report = await store.validate_consistency(["EMPTY-EQ"], "1D", sample_ratio=1.0)
        assert report.total_audited == 1
        assert report.matched_count == 0
        assert report.mismatched_count == 0
        store.ingest_candles.assert_not_awaited()

    async def test_empty_provider_skips_symbol_without_error(self, store):
        store._query_db_candles.return_value = [_candle(0)]
        store._fetch_provider_candles.return_value = []

        report = await store.validate_consistency(["NO-PROV-EQ"], "1D", sample_ratio=1.0)
        assert report.matched_count == 0
        assert report.mismatched_count == 0
        store.ingest_candles.assert_not_awaited()

    async def test_multiple_symbols_aggregate_counts(self, store):
        match_series = [_candle(i) for i in range(3)]
        mismatch_db = [_candle(0, close=50.0)]
        mismatch_prov = [_candle(0, close=60.0)]

        async def query_side_effect(symbol, resolution, start_dt=None, end_dt=None):
            if symbol == "MATCH-EQ":
                return match_series
            if symbol == "MISMATCH-EQ":
                return mismatch_db
            return []

        async def provider_side_effect(symbol, resolution, start_dt=None, end_dt=None):
            if symbol == "MATCH-EQ":
                return match_series
            if symbol == "MISMATCH-EQ":
                return mismatch_prov
            return []

        store._query_db_candles.side_effect = query_side_effect
        store._fetch_provider_candles.side_effect = provider_side_effect

        report = await store.validate_consistency(
            ["MATCH-EQ", "MISMATCH-EQ", "EMPTY-EQ"], "d", sample_ratio=1.0
        )
        assert report.total_audited == 3
        assert report.matched_count == 1
        assert report.mismatched_count == 1
        assert report.repaired_count == 1

    async def test_sample_ratio_limits_audit_population(self, store):
        """FR-008: default 1% sample of a large list must not audit every symbol."""
        symbols = [f"SYM{i}-EQ" for i in range(200)]
        store._query_db_candles.return_value = [_candle(0)]
        store._fetch_provider_candles.return_value = [_candle(0)]

        report = await store.validate_consistency(symbols, "1D", sample_ratio=0.01)
        # ceil(200 * 0.01) = 2
        assert report.total_audited == 2
        assert store._query_db_candles.await_count == 2

    async def test_resolution_normalized_before_audit(self, store):
        series = [_candle(0)]
        store._query_db_candles.return_value = series
        store._fetch_provider_candles.return_value = series

        await store.validate_consistency(["SYM-EQ"], "d", sample_ratio=1.0)
        # Both DB and provider queried with canonical resolution
        for mock in (store._query_db_candles, store._fetch_provider_candles):
            args = mock.call_args.args
            assert args[1] == "1D"
