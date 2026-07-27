"""Dual-path parity and contract tests for unified latest-scan endpoints.

Verifies AC-001, AC-002, AC-005, AC-006, FR-006..FR-014 for:
- GET /scanner/latest
- GET /analysis/scan/latest

When SCANNER_UNIFIED_LATEST_ENABLED is toggled OFF vs ON, JSON structure,
status codes, and X-Cache-Status contract remain compatible.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import settings
from app.main import app
from app.tests.cache_test_utils import (
    set_scanner_cache_enabled,
    set_scanner_unified_latest_enabled,
)

DASHBOARD_EMPTY_KEYS = {
    "message",
    "buy_candidates",
    "watch_candidates",
    "rejected_candidates",
}

DASHBOARD_POPULATED_KEYS = {
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

ANALYSIS_EMPTY_KEYS = {"available"}
# Live production contract: available + ScreenerResponse fields (frontend loadLatestScan).
SCREENER_CONTRACT_KEYS = {
    "available",
    "buy_candidate_symbols",
    "watch_candidate_symbols",
    "shortlisted_symbols",
    "all_analyzed_stocks",
    "matches",
    "items",
    "scanned_at",
    "last_scan_completed_at",
}

CACHE_STATUSES = {"HIT", "MISS", "BYPASS", "FALLBACK"}

SCREENER_SAMPLE = {
    "buy_candidate_symbols": ["RELIANCE"],
    "watch_candidate_symbols": ["INFY"],
    "shortlisted_symbols": ["RELIANCE", "INFY"],
    "all_analyzed_stocks": [{"symbol": "RELIANCE"}, {"symbol": "INFY"}],
    "matches": [{"symbol": "RELIANCE", "close": 100.0}],
    "items": [
        {"symbol": "RELIANCE", "signal": "BUY", "matched": True},
        {"symbol": "INFY", "signal": "WATCH", "matched": True},
    ],
    "scanned_at": "2026-07-27T10:00:00+00:00",
    "last_scan_completed_at": "2026-07-27T10:00:00+00:00",
    "analysis": {"items": [{"symbol": "RELIANCE"}]},
    "scanned_symbols": 2,
}

DASHBOARD_SAMPLE = {
    "scan_id": "snap-parity-1",
    "scan_timestamp": "2026-07-27T10:00:00+00:00",
    "last_scan_completed_at": "2026-07-27T10:00:00+00:00",
    "total_scanned": 2,
    "valid_symbols": 2,
    "buy_count": 1,
    "watch_count": 1,
    "rejected_count": 0,
    "buy_candidates": [
        {"symbol": "RELIANCE", "recommendation": "BUY", "score": 90.0, "close_price": 100.0}
    ],
    "watch_candidates": [
        {"symbol": "INFY", "recommendation": "WATCH", "score": 70.0, "close_price": 1500.0}
    ],
    "rejected_candidates": [],
}


class InMemoryRedis:
    def __init__(self) -> None:
        self.store: Dict[str, str] = {}
        self.ttls: Dict[str, int] = {}
        self.set_calls: list = []

    async def get(self, key: str) -> Optional[str]:
        return self.store.get(key)

    async def set(
        self, key: str, value: str, ex: Optional[int] = None, nx: bool = False
    ) -> bool:
        if nx and key in self.store:
            return False
        self.set_calls.append((key, value, ex))
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                n += 1
        return n


@pytest.fixture
def redis_mock(monkeypatch) -> InMemoryRedis:
    mock = InMemoryRedis()
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: mock,
    )
    return mock


# ---------------------------------------------------------------------------
# AC-001 / US1: scanner parity legacy vs unified
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_latest_unified_parity(monkeypatch):
    """US1 / T007 / AC-001: identical schema under unified vs legacy path."""
    set_scanner_unified_latest_enabled(monkeypatch, False)
    set_scanner_cache_enabled(monkeypatch, False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_off = await client.get("/scanner/latest")
        assert res_off.status_code == 200
        data_off = res_off.json()

    set_scanner_unified_latest_enabled(monkeypatch, True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_on = await client.get("/scanner/latest")
        assert res_on.status_code == 200
        data_on = res_on.json()

    assert res_off.status_code == res_on.status_code
    assert "x-cache-status" in res_on.headers
    assert res_on.headers["x-cache-status"] in CACHE_STATUSES
    assert set(data_off.keys()) == set(data_on.keys())
    if "message" in data_off:
        assert data_off["message"] == data_on["message"]
        assert set(data_on.keys()) == DASHBOARD_EMPTY_KEYS
    else:
        assert DASHBOARD_POPULATED_KEYS.issubset(set(data_on.keys()))
        assert data_off.get("scan_id") == data_on.get("scan_id")
        assert len(data_off.get("buy_candidates", [])) == len(data_on.get("buy_candidates", []))


@pytest.mark.asyncio
async def test_scanner_latest_content_type_and_cache_header(monkeypatch):
    """FR-013: Content-Type application/json and X-Cache-Status always present."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/scanner/latest")
    assert res.status_code == 200
    assert "application/json" in res.headers.get("content-type", "")
    assert res.headers.get("x-cache-status") in CACHE_STATUSES


@pytest.mark.asyncio
async def test_scanner_latest_unified_delegates_to_get_latest_scan(monkeypatch):
    """AC-003/FR-008: Flag ON routes /scanner/latest through get_latest_scan('dashboard')."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, False)
    empty = json.dumps(
        {
            "message": "No completed scans found",
            "buy_candidates": [],
            "watch_candidates": [],
            "rejected_candidates": [],
        }
    )
    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_scan",
        new_callable=AsyncMock,
        return_value=(empty, "BYPASS"),
    ) as unified_mock:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/scanner/latest")

    assert res.status_code == 200
    assert res.headers["x-cache-status"] == "BYPASS"
    assert res.json()["message"] == "No completed scans found"
    unified_mock.assert_awaited()
    kwargs = unified_mock.await_args.kwargs
    assert kwargs.get("format_type") == "dashboard" or (
        unified_mock.await_args.args and unified_mock.await_args.args[0] == "dashboard"
    )


@pytest.mark.asyncio
async def test_scanner_latest_legacy_does_not_call_get_latest_scan(monkeypatch):
    """FR-007: Flag OFF uses legacy path; get_latest_scan is not invoked."""
    set_scanner_unified_latest_enabled(monkeypatch, False)
    set_scanner_cache_enabled(monkeypatch, False)
    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_scan",
        new_callable=AsyncMock,
    ) as unified_mock:
        with patch(
            "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get("/scanner/latest")

    assert res.status_code == 200
    unified_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# AC-002 / US2: analysis parity legacy vs unified
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analysis_scan_latest_unified_parity(monkeypatch):
    """US2 / T010 / AC-002: empty-state available parity under unified vs legacy path."""
    set_scanner_unified_latest_enabled(monkeypatch, False)
    set_scanner_cache_enabled(monkeypatch, False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_off = await client.get("/analysis/scan/latest")
        assert res_off.status_code == 200
        data_off = res_off.json()

    set_scanner_unified_latest_enabled(monkeypatch, True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_on = await client.get("/analysis/scan/latest")
        assert res_on.status_code == 200
        data_on = res_on.json()

    assert res_off.status_code == res_on.status_code
    assert "x-cache-status" in res_on.headers
    assert res_on.headers["x-cache-status"] in CACHE_STATUSES
    # Live DB may be empty or populated; parity is the contract.
    assert data_off == data_on
    assert "available" in data_on


@pytest.mark.asyncio
async def test_analysis_populated_deep_parity_legacy_vs_unified(monkeypatch):
    """AC-002/AC-005: populated ScreenerResponse body identical under flag OFF vs ON."""
    set_scanner_cache_enabled(monkeypatch, False)
    with patch(
        "app.routes.analysis.load_latest_scan",
        new_callable=AsyncMock,
        return_value=dict(SCREENER_SAMPLE),
    ), patch(
        "app.db.scan_store.load_latest_scan",
        new_callable=AsyncMock,
        return_value=dict(SCREENER_SAMPLE),
    ):
        set_scanner_unified_latest_enabled(monkeypatch, False)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res_off = await client.get("/analysis/scan/latest")

        set_scanner_unified_latest_enabled(monkeypatch, True)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res_on = await client.get("/analysis/scan/latest")

    assert res_off.status_code == 200
    assert res_on.status_code == 200
    data_off = res_off.json()
    data_on = res_on.json()
    assert data_off == data_on
    assert data_on["available"] is True
    assert data_on["buy_candidate_symbols"] == ["RELIANCE"]
    assert data_on["all_analyzed_stocks"][0]["symbol"] == "RELIANCE"
    assert SCREENER_CONTRACT_KEYS.issubset(set(data_on.keys()))


@pytest.mark.asyncio
async def test_scanner_populated_deep_parity_legacy_vs_unified(monkeypatch):
    """AC-001: populated dashboard body identical under flag OFF vs ON."""
    set_scanner_cache_enabled(monkeypatch, False)
    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=dict(DASHBOARD_SAMPLE),
    ), patch(
        "app.services.latest_scan_service.LatestScanService._fetch_latest_snapshot_and_records",
        new_callable=AsyncMock,
        return_value=(None, []),  # not used when we also patch get_latest_scan path below
    ):
        # Legacy uses get_latest_completed_scan; unified uses get_latest_scan produce path.
        # Patch get_latest_scan's dashboard produce via returning same payload through service.
        async def fake_get_latest_scan(
            self, format_type="dashboard", force=False, cache_enabled=None
        ):
            return json.dumps(DASHBOARD_SAMPLE), "BYPASS"

        with patch(
            "app.services.latest_scan_service.LatestScanService.get_latest_scan",
            new=fake_get_latest_scan,
        ):
            set_scanner_unified_latest_enabled(monkeypatch, False)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res_off = await client.get("/scanner/latest")

            set_scanner_unified_latest_enabled(monkeypatch, True)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res_on = await client.get("/scanner/latest")

    assert res_off.status_code == 200
    assert res_on.status_code == 200
    assert res_off.json() == res_on.json()
    assert res_on.json()["scan_id"] == "snap-parity-1"
    assert res_on.json()["buy_candidates"][0]["symbol"] == "RELIANCE"


@pytest.mark.asyncio
async def test_analysis_scan_latest_unified_delegates_to_get_latest_scan(monkeypatch):
    """AC-003/FR-008: Flag ON routes /analysis/scan/latest through get_latest_scan('analysis')."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, False)
    empty = json.dumps({"available": False})
    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_scan",
        new_callable=AsyncMock,
        return_value=(empty, "BYPASS"),
    ) as unified_mock:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/analysis/scan/latest")

    assert res.status_code == 200
    assert res.json() == {"available": False}
    unified_mock.assert_awaited()
    kwargs = unified_mock.await_args.kwargs
    assert kwargs.get("format_type") == "analysis" or (
        unified_mock.await_args.args and unified_mock.await_args.args[0] == "analysis"
    )


# ---------------------------------------------------------------------------
# AC-006 / FR-010: force + Cache-Control under unified path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_unified_force_true_bypasses_cache(monkeypatch, redis_mock: InMemoryRedis):
    """FR-010/AC-006: force=true under unified path refreshes from service."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, True)
    stale = {
        "message": "No completed scans found",
        "buy_candidates": [],
        "watch_candidates": [],
        "rejected_candidates": [],
    }
    redis_mock.store["scanner:latest:v1"] = json.dumps(stale)
    fresh = {
        "scan_id": "fresh-1",
        "scan_timestamp": "2026-07-27T12:00:00+00:00",
        "last_scan_completed_at": "2026-07-27T12:00:00+00:00",
        "total_scanned": 1,
        "valid_symbols": 1,
        "buy_count": 0,
        "watch_count": 0,
        "rejected_count": 0,
        "buy_candidates": [],
        "watch_candidates": [],
        "rejected_candidates": [],
    }

    async def produce_via_get_latest_scan(format_type="dashboard", force=False, cache_enabled=None):
        # Simulate unified service resolve: force should skip HIT
        status = "MISS" if force else "HIT"
        body = json.dumps(fresh if force else stale)
        return body, status

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_scan",
        new_callable=AsyncMock,
        side_effect=produce_via_get_latest_scan,
    ) as mock_unified:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/scanner/latest?force=true")

    assert res.status_code == 200
    assert res.headers["x-cache-status"] == "MISS"
    assert res.json()["scan_id"] == "fresh-1"
    assert mock_unified.await_args.kwargs.get("force") is True


@pytest.mark.asyncio
async def test_scanner_unified_cache_control_no_cache(monkeypatch):
    """FR-010: Cache-Control: no-cache under unified path sets force=True."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, True)
    empty = json.dumps(
        {
            "message": "No completed scans found",
            "buy_candidates": [],
            "watch_candidates": [],
            "rejected_candidates": [],
        }
    )
    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_scan",
        new_callable=AsyncMock,
        return_value=(empty, "MISS"),
    ) as mock_unified:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get(
                "/scanner/latest",
                headers={"Cache-Control": "no-cache"},
            )

    assert res.status_code == 200
    assert mock_unified.await_args.kwargs.get("force") is True


@pytest.mark.asyncio
async def test_analysis_unified_force_true(monkeypatch):
    """FR-010: force=true preserved for analysis unified path."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, True)
    empty = json.dumps({"available": False})
    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_scan",
        new_callable=AsyncMock,
        return_value=(empty, "MISS"),
    ) as mock_unified:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/analysis/scan/latest?force=true")

    assert res.status_code == 200
    assert mock_unified.await_args.kwargs.get("force") is True
    assert mock_unified.await_args.kwargs.get("format_type") == "analysis" or (
        mock_unified.await_args.args and mock_unified.await_args.args[0] == "analysis"
    )


# ---------------------------------------------------------------------------
# Unified path cache HIT / MISS with real get_latest_scan + redis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unified_scanner_cache_hit_and_miss(monkeypatch, redis_mock: InMemoryRedis):
    """AC-006: Under unified flag, miss then hit on /scanner/latest."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, True)
    monkeypatch.setattr(settings, "scanner_latest_cache_ttl_seconds", 300)

    empty_payload = {
        "message": "No completed scans found",
        "buy_candidates": [],
        "watch_candidates": [],
        "rejected_candidates": [],
    }

    async def _empty_fetch(self):
        return None, []

    with patch(
        "app.services.latest_scan_service.LatestScanService._fetch_latest_snapshot_and_records",
        new=_empty_fetch,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            miss = await client.get("/scanner/latest")
            hit = await client.get("/scanner/latest")

    assert miss.status_code == 200
    assert hit.status_code == 200
    assert miss.headers["x-cache-status"] == "MISS"
    assert hit.headers["x-cache-status"] == "HIT"
    assert miss.json() == empty_payload
    assert hit.json() == empty_payload
    assert "scanner:latest:v1" in redis_mock.store


@pytest.mark.asyncio
async def test_unified_analysis_cache_hit_and_miss(monkeypatch, redis_mock: InMemoryRedis):
    """AC-006: Under unified flag, miss then hit on /analysis/scan/latest."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, True)

    with patch(
        "app.db.scan_store.load_latest_scan",
        new_callable=AsyncMock,
        return_value=None,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            miss = await client.get("/analysis/scan/latest")
            hit = await client.get("/analysis/scan/latest")

    assert miss.headers["x-cache-status"] == "MISS"
    assert hit.headers["x-cache-status"] == "HIT"
    assert miss.json() == {"available": False}
    assert hit.json() == {"available": False}
    assert "analysis:scan:latest:v1" in redis_mock.store


@pytest.mark.asyncio
async def test_unified_analysis_cache_stores_screener_shape(
    monkeypatch, redis_mock: InMemoryRedis
):
    """C2 fix: analysis cache key must store ScreenerResponse shape (not simplified adapter)."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, True)

    with patch(
        "app.db.scan_store.load_latest_scan",
        new_callable=AsyncMock,
        return_value=dict(SCREENER_SAMPLE),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/analysis/scan/latest")

    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["buy_candidate_symbols"] == ["RELIANCE"]
    cached = json.loads(redis_mock.store["analysis:scan:latest:v1"])
    assert cached == body
    assert SCREENER_CONTRACT_KEYS.issubset(set(cached.keys()))


# ---------------------------------------------------------------------------
# Regression: both endpoints still 200 when cache disabled under both flags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_endpoints_ok_cache_disabled_flag_matrix(monkeypatch):
    """AC-005/regression: both endpoints return 200 for flag OFF/ON with cache off."""
    set_scanner_cache_enabled(monkeypatch, False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for enabled in (False, True):
            set_scanner_unified_latest_enabled(monkeypatch, enabled)
            r1 = await client.get("/scanner/latest")
            r2 = await client.get("/analysis/scan/latest")
            assert r1.status_code == 200, f"scanner failed flag={enabled}"
            assert r2.status_code == 200, f"analysis failed flag={enabled}"
            assert r1.headers.get("x-cache-status") in CACHE_STATUSES
            assert r2.headers.get("x-cache-status") in CACHE_STATUSES
