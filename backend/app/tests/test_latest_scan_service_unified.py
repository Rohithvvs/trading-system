"""Unit tests for LatestScanService unified adapters and get_latest_scan().

Maps to FR-001..FR-005, FR-011..FR-014, AC-003, AC-006 and edge/null handling.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.market_data import ScanSnapshot, ScanSnapshotRecord
from app.services.latest_scan_service import LatestScanService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snapshot(
    scan_id: str = "snap-1",
    *,
    total: int = 10,
    valid: int = 8,
    buy: int = 1,
    watch: int = 1,
    rejected: int = 1,
    ts: datetime | None = None,
) -> ScanSnapshot:
    return ScanSnapshot(
        scan_id=scan_id,
        scan_timestamp=ts or datetime(2026, 7, 27, 10, 0, 0, tzinfo=timezone.utc),
        total_scanned=total,
        valid_symbols=valid,
        buy_count=buy,
        watch_count=watch,
        rejected_count=rejected,
        status="COMPLETED",
    )


def _record(
    symbol: str,
    recommendation: str,
    score: float | None,
    *,
    close_price: float | None = 100.0,
    sma50: float | None = None,
    sma200: float | None = None,
    rsi: float | None = None,
    macd: float | None = None,
    volume: int | None = None,
    reason: str | None = None,
) -> ScanSnapshotRecord:
    return ScanSnapshotRecord(
        symbol=symbol,
        recommendation=recommendation,
        score=score,
        close_price=close_price,
        sma50=sma50,
        sma200=sma200,
        rsi=rsi,
        macd=macd,
        volume=volume,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Unit: dashboard adapter (FR-003, FR-004, FR-011)
# ---------------------------------------------------------------------------


def test_format_dashboard_payload_empty():
    res = LatestScanService._format_dashboard_payload(None, [])
    assert res == {
        "message": "No completed scans found",
        "buy_candidates": [],
        "watch_candidates": [],
        "rejected_candidates": [],
    }


def test_format_dashboard_payload_populated_schema_keys():
    """FR-011: Populated dashboard payload includes all contract keys."""
    now = datetime.now(timezone.utc)
    snapshot = _snapshot(scan_id="test-uuid-1", ts=now)
    rec1 = _record("AAPL", "BUY", 85.5, close_price=150.0, volume=1_000_000, reason="Breakout")
    rec2 = _record("MSFT", "WATCH", 70.0, close_price=300.0, volume=500_000, reason="Consolidation")
    rec3 = _record("TSLA", "REJECTED", 30.0, close_price=200.0, volume=800_000, reason="High Risk")

    res = LatestScanService._format_dashboard_payload(snapshot, [rec1, rec2, rec3])

    expected_keys = {
        "scan_id",
        "scan_timestamp",
        "last_scan_completed_at",
        "total_scanned",
        "valid_symbols",
        "buy_count",
        "watch_count",
        "rejected_count",
        "buy_candidates",
        "watch_candidates",
        "rejected_candidates",
    }
    assert set(res.keys()) == expected_keys
    assert res["scan_id"] == "test-uuid-1"
    assert res["scan_timestamp"] == now.isoformat()
    assert res["last_scan_completed_at"] == now.isoformat()
    assert len(res["buy_candidates"]) == 1
    assert res["buy_candidates"][0]["symbol"] == "AAPL"
    assert len(res["watch_candidates"]) == 1
    assert res["watch_candidates"][0]["symbol"] == "MSFT"
    assert len(res["rejected_candidates"]) == 1
    assert res["rejected_candidates"][0]["symbol"] == "TSLA"


def test_format_dashboard_candidates_sorted_by_score_desc():
    """FR-003: Candidates sorted descending by score within each bucket."""
    snapshot = _snapshot(buy=2, watch=2, rejected=2)
    records = [
        _record("BUY_LOW", "BUY", 10.0),
        _record("BUY_HIGH", "BUY", 99.0),
        _record("WATCH_MID", "WATCH", 50.0),
        _record("WATCH_TOP", "WATCH", 80.0),
        _record("REJ_LOW", "REJECTED", 5.0),
        _record("REJ_HIGH", "REJECTED", 40.0),
    ]
    res = LatestScanService._format_dashboard_payload(snapshot, records)
    assert [c["symbol"] for c in res["buy_candidates"]] == ["BUY_HIGH", "BUY_LOW"]
    assert [c["symbol"] for c in res["watch_candidates"]] == ["WATCH_TOP", "WATCH_MID"]
    assert [c["symbol"] for c in res["rejected_candidates"]] == ["REJ_HIGH", "REJ_LOW"]


def test_format_dashboard_null_scores_and_prices_default_to_zero():
    """Edge: null score/close_price coerce to 0.0 without raising."""
    snapshot = _snapshot(buy=1, watch=0, rejected=0)
    rec = _record("NULLY", "BUY", None, close_price=None)
    res = LatestScanService._format_dashboard_payload(snapshot, [rec])
    assert res["buy_candidates"][0]["score"] == 0.0
    assert res["buy_candidates"][0]["close_price"] == 0.0


def test_format_dashboard_unknown_recommendation_goes_to_rejected():
    """Edge: non-BUY/WATCH recommendations land in rejected_candidates."""
    snapshot = _snapshot(buy=0, watch=0, rejected=1)
    rec = _record("ODD", "HOLD", 55.0)
    res = LatestScanService._format_dashboard_payload(snapshot, [rec])
    assert res["buy_candidates"] == []
    assert res["watch_candidates"] == []
    assert len(res["rejected_candidates"]) == 1
    assert res["rejected_candidates"][0]["symbol"] == "ODD"


def test_format_dashboard_empty_records_with_snapshot():
    """Edge: snapshot exists but no child records → empty candidate arrays."""
    snapshot = _snapshot(buy=0, watch=0, rejected=0, total=0, valid=0)
    res = LatestScanService._format_dashboard_payload(snapshot, [])
    assert res["scan_id"] == "snap-1"
    assert res["buy_candidates"] == []
    assert res["watch_candidates"] == []
    assert res["rejected_candidates"] == []
    assert res["total_scanned"] == 0


# ---------------------------------------------------------------------------
# Unit: analysis adapter (FR-004, FR-012)
# ---------------------------------------------------------------------------


def test_format_analysis_payload_empty():
    res = LatestScanService._format_analysis_payload(None, [])
    assert res == {"available": False}


def test_format_analysis_payload_populated_schema_keys():
    """FR-012: Populated analysis payload includes contract keys."""
    now = datetime.now(timezone.utc)
    snapshot = _snapshot(scan_id="test-uuid-2", ts=now, total=5, buy=1, watch=1, rejected=0)
    rec1 = _record("INFY", "BUY", 90.0, close_price=1400.0, sma50=1350.0, reason="Bullish SMA")
    rec2 = _record("TCS", "WATCH", 65.0, close_price=3200.0, reason="Near Support")

    res = LatestScanService._format_analysis_payload(snapshot, [rec1, rec2])

    assert res["available"] is True
    assert res["timestamp"] == now.isoformat()
    assert res["scan_id"] == "test-uuid-2"
    assert res["total_symbols"] == 5
    assert res["buy_signals"] == 1
    assert res["watch_signals"] == 1
    assert res["no_signals"] == 0
    assert len(res["items"]) == 2
    assert res["items"][0]["symbol"] == "INFY"
    assert res["items"][0]["technical"]["sma50"] == 1350.0
    assert "rsi" in res["items"][0]["technical"]
    assert "macd" in res["items"][0]["technical"]


def test_format_analysis_signal_counts_and_null_technicals():
    """Edge: null technical indicators remain null; counts track recommendation buckets."""
    snapshot = _snapshot(total=3, buy=1, watch=1, rejected=1)
    records = [
        _record("B1", "BUY", 80.0, sma50=None, sma200=None, rsi=None, macd=None),
        _record("W1", "WATCH", 60.0),
        _record("R1", "REJECTED", None, close_price=None),
    ]
    res = LatestScanService._format_analysis_payload(snapshot, records)
    assert res["buy_signals"] == 1
    assert res["watch_signals"] == 1
    assert res["no_signals"] == 1
    buy_item = next(i for i in res["items"] if i["symbol"] == "B1")
    assert buy_item["technical"]["sma50"] is None
    rej_item = next(i for i in res["items"] if i["symbol"] == "R1")
    assert rej_item["score"] == 0.0
    assert rej_item["close_price"] == 0.0


# ---------------------------------------------------------------------------
# Unit: get_latest_scan master method (FR-001, FR-002, FR-005, FR-009)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_scan_dashboard_empty_bypass():
    """FR-004/FR-011: Empty DB via unified entry returns empty dashboard JSON + BYPASS."""
    service = LatestScanService(AsyncMock())

    async def _empty_fetch():
        return None, []

    with patch.object(service, "_fetch_latest_snapshot_and_records", side_effect=_empty_fetch):
        with patch.object(
            service, "_fetch_latest_from_canonical_results", new_callable=AsyncMock, return_value=None
        ):
            payload, status = await service.get_latest_scan(
                format_type="dashboard", cache_enabled=False
            )

    assert status == "BYPASS"
    data = json.loads(payload)
    assert data["message"] == "No completed scans found"
    assert data["buy_candidates"] == []


@pytest.mark.asyncio
async def test_get_latest_scan_analysis_empty_bypass():
    """Empty scan_store via unified analysis returns available=false + BYPASS."""
    service = LatestScanService(AsyncMock())

    with patch(
        "app.db.scan_store.load_latest_scan",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with patch.object(
            service,
            "_fetch_analysis_from_canonical_results",
            new_callable=AsyncMock,
            return_value=None,
        ):
            payload, status = await service.get_latest_scan(
                format_type="analysis", cache_enabled=False
            )

    assert status == "BYPASS"
    assert json.loads(payload) == {"available": False}


@pytest.mark.asyncio
async def test_get_latest_scan_dashboard_populated():
    """FR-001/FR-003: Unified dashboard path formats snapshot records correctly."""
    service = LatestScanService(AsyncMock())
    snap = _snapshot(scan_id="dash-1")
    records = [
        _record("AAA", "BUY", 10.0),
        _record("BBB", "BUY", 90.0),
        _record("CCC", "WATCH", 70.0),
    ]

    async def _fetch():
        return snap, records

    with patch.dict("os.environ", {"SCAN_RESULT_MINIMAL_WRITES": "false"}):
        with patch.object(service, "_fetch_latest_snapshot_and_records", side_effect=_fetch):
            payload, status = await service.get_latest_scan(
                format_type="dashboard", cache_enabled=False
            )

    assert status == "BYPASS"
    data = json.loads(payload)
    assert data["scan_id"] == "dash-1"
    assert [c["symbol"] for c in data["buy_candidates"]] == ["BBB", "AAA"]
    assert data["watch_candidates"][0]["symbol"] == "CCC"


@pytest.mark.asyncio
async def test_get_latest_scan_analysis_populated_screener_contract():
    """Unified analysis must emit ScreenerResponse fields used by the frontend."""
    service = LatestScanService(AsyncMock())
    screener_payload = {
        "buy_candidate_symbols": ["INFY"],
        "watch_candidate_symbols": ["TCS"],
        "shortlisted_symbols": ["INFY", "TCS"],
        "all_analyzed_stocks": [{"symbol": "INFY"}, {"symbol": "TCS"}],
        "matches": [{"symbol": "INFY"}],
        "items": [{"symbol": "INFY", "signal": "BUY"}, {"symbol": "TCS", "signal": "WATCH"}],
        "scanned_at": "2026-07-27T12:00:00+00:00",
        "last_scan_completed_at": "2026-07-27T12:00:00+00:00",
        "analysis": {"items": [{"symbol": "INFY"}]},
    }

    with patch(
        "app.db.scan_store.load_latest_scan",
        new_callable=AsyncMock,
        return_value=screener_payload,
    ):
        payload, status = await service.get_latest_scan(
            format_type="analysis", cache_enabled=False
        )

    data = json.loads(payload)
    assert status == "BYPASS"
    assert data["available"] is True
    assert data["buy_candidate_symbols"] == ["INFY"]
    assert data["watch_candidate_symbols"] == ["TCS"]
    assert data["all_analyzed_stocks"][0]["symbol"] == "INFY"
    assert data["scanned_at"] == "2026-07-27T12:00:00+00:00"
    assert data["analysis"]["items"][0]["symbol"] == "INFY"
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_get_latest_scan_rejects_invalid_format_type():
    service = LatestScanService(AsyncMock())
    with pytest.raises(ValueError, match="Unsupported format_type"):
        await service.get_latest_scan(format_type="unknown", cache_enabled=False)


@pytest.mark.asyncio
async def test_get_latest_scan_uses_dashboard_cache_key():
    """FR-009: Dashboard format uses scanner:latest:v1 cache key."""
    service = LatestScanService(AsyncMock())
    seen: dict = {}

    async def fake_resolve(key, produce_json, force=False, cache_enabled=None):
        seen["key"] = key
        seen["force"] = force
        body = await produce_json()
        return body, "MISS"

    async def _empty():
        return None, []

    with (
        patch.object(service, "_fetch_latest_snapshot_and_records", side_effect=_empty),
        patch.object(
            service, "_fetch_latest_from_canonical_results", new_callable=AsyncMock, return_value=None
        ),
        patch(
            "app.services.scanner_cache_service.scanner_cache_service.resolve_latest_scan",
            side_effect=fake_resolve,
        ),
    ):
        await service.get_latest_scan(format_type="dashboard", force=True, cache_enabled=True)

    assert seen["key"] == "scanner:latest:v1"
    assert seen["force"] is True


@pytest.mark.asyncio
async def test_get_latest_scan_uses_analysis_cache_key():
    """FR-009: Analysis format uses analysis:scan:latest:v1 cache key."""
    service = LatestScanService(AsyncMock())
    seen: dict = {}

    async def fake_resolve(key, produce_json, force=False, cache_enabled=None):
        seen["key"] = key
        body = await produce_json()
        return body, "MISS"

    with (
        patch(
            "app.db.scan_store.load_latest_scan",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch.object(
            service,
            "_fetch_analysis_from_canonical_results",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.scanner_cache_service.scanner_cache_service.resolve_latest_scan",
            side_effect=fake_resolve,
        ),
    ):
        await service.get_latest_scan(format_type="analysis", cache_enabled=True)

    assert seen["key"] == "analysis:scan:latest:v1"


@pytest.mark.asyncio
async def test_get_latest_scan_cache_hit_skips_produce():
    """FR-009/AC-006: Cache HIT returns payload without invoking DB produce path."""
    service = LatestScanService(AsyncMock())
    cached = json.dumps({"scan_id": "from-cache", "buy_candidates": []})
    produce = AsyncMock()

    async def fake_resolve(key, produce_json, force=False, cache_enabled=None):
        # Simulate HIT: do not call produce_json
        return cached, "HIT"

    with patch(
        "app.services.scanner_cache_service.scanner_cache_service.resolve_latest_scan",
        side_effect=fake_resolve,
    ):
        payload, status = await service.get_latest_scan(
            format_type="dashboard", cache_enabled=True
        )

    assert status == "HIT"
    assert json.loads(payload)["scan_id"] == "from-cache"


@pytest.mark.asyncio
async def test_fetch_latest_snapshot_prefers_completed():
    """FR-002: COMPLETED snapshot preferred over non-completed fallback."""
    db = AsyncMock()
    completed = _snapshot(scan_id="completed-1")
    records = [_record("X", "BUY", 50.0)]

    # First execute → COMPLETED snapshot; second → records
    exec_completed = MagicMock()
    exec_completed.scalar_one_or_none.return_value = completed
    exec_records = MagicMock()
    exec_records.scalars.return_value.all.return_value = records
    db.execute = AsyncMock(side_effect=[exec_completed, exec_records])

    service = LatestScanService(db)
    snap, recs = await service._fetch_latest_snapshot_and_records()
    assert snap is completed
    assert snap.scan_id == "completed-1"
    assert len(recs) == 1


@pytest.mark.asyncio
async def test_fetch_latest_snapshot_falls_back_when_no_completed():
    """FR-002: Falls back to newest snapshot when no COMPLETED row exists."""
    db = AsyncMock()
    fallback = _snapshot(scan_id="running-1")
    fallback.status = "RUNNING"

    empty_completed = MagicMock()
    empty_completed.scalar_one_or_none.return_value = None
    any_row = MagicMock()
    any_row.scalar_one_or_none.return_value = fallback
    empty_records = MagicMock()
    empty_records.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(side_effect=[empty_completed, any_row, empty_records])

    service = LatestScanService(db)
    snap, recs = await service._fetch_latest_snapshot_and_records()
    assert snap is fallback
    assert snap.scan_id == "running-1"
    assert recs == []


@pytest.mark.asyncio
async def test_fetch_latest_snapshot_empty_db():
    """FR-002/FR-004: No snapshots at all → (None, [])."""
    db = AsyncMock()
    empty = MagicMock()
    empty.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(side_effect=[empty, empty])

    service = LatestScanService(db)
    snap, recs = await service._fetch_latest_snapshot_and_records()
    assert snap is None
    assert recs == []
