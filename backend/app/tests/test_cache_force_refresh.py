"""Unit/integration tests for force refresh query param and Cache-Control header.

Maps to User Story 3, FR-006, FR-007.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import settings
from app.tests.cache_test_utils import set_scanner_cache_enabled
from app.main import app


SCANNER_PAYLOAD: Dict[str, Any] = {
    "scan_timestamp": "2026-07-27T10:00:00Z",
    "buy_candidates": [{"symbol": "HDFCBANK", "score": 77.0}],
    "watch_candidates": [],
    "rejected_candidates": [],
}

FRESH_PAYLOAD: Dict[str, Any] = {
    "scan_timestamp": "2026-07-27T11:00:00Z",
    "buy_candidates": [{"symbol": "SBIN", "score": 90.0}],
    "watch_candidates": [],
    "rejected_candidates": [],
}


class InMemoryRedis:
    def __init__(self) -> None:
        self.store: Dict[str, str] = {}
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


@pytest.mark.asyncio
async def test_force_query_param_bypasses_cache_read(monkeypatch, redis_mock: InMemoryRedis):
    """US3 / FR-006: GET /scanner/latest?force=true bypasses Redis read and refreshes cache."""
    set_scanner_cache_enabled(monkeypatch, True)
    stale = json.dumps(SCANNER_PAYLOAD)
    redis_mock.store["scanner:latest:v1"] = stale

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=FRESH_PAYLOAD,
    ) as db_mock:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/scanner/latest?force=true")

    assert response.status_code == 200
    assert response.headers.get("x-cache-status") == "MISS"
    assert response.json()["scan_timestamp"] == FRESH_PAYLOAD["scan_timestamp"]
    db_mock.assert_awaited()
    # FR-007: Redis key overwritten with fresh payload
    assert "scanner:latest:v1" in redis_mock.store
    assert json.loads(redis_mock.store["scanner:latest:v1"])["scan_timestamp"] == (
        FRESH_PAYLOAD["scan_timestamp"]
    )


@pytest.mark.asyncio
async def test_cache_control_header_bypasses_cache_read(
    monkeypatch, redis_mock: InMemoryRedis
):
    """US3 / FR-006: Header Cache-Control: no-cache forces a fresh database read."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock.store["scanner:latest:v1"] = json.dumps(SCANNER_PAYLOAD)

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=FRESH_PAYLOAD,
    ) as db_mock:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/scanner/latest", headers={"Cache-Control": "no-cache"}
            )

    assert response.status_code == 200
    assert response.headers.get("x-cache-status") == "MISS"
    assert response.json()["scan_timestamp"] == FRESH_PAYLOAD["scan_timestamp"]
    db_mock.assert_awaited()


@pytest.mark.asyncio
async def test_force_true_on_analysis_endpoint(monkeypatch, redis_mock: InMemoryRedis):
    """US3: force=true also applies to GET /analysis/scan/latest."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock.store["analysis:scan:latest:v1"] = json.dumps(
        {"available": True, "items": [{"symbol": "OLD"}]}
    )
    fresh = {"items": [{"symbol": "NEW"}], "scan_timestamp": "2026-07-27T12:00:00Z"}

    with patch(
        "app.routes.analysis.load_latest_scan",
        new_callable=AsyncMock,
        return_value=fresh,
    ) as db_mock:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/analysis/scan/latest?force=true")

    assert response.status_code == 200
    assert response.headers.get("x-cache-status") == "MISS"
    assert response.json()["items"][0]["symbol"] == "NEW"
    db_mock.assert_awaited()


@pytest.mark.asyncio
async def test_cache_control_no_cache_on_analysis_endpoint(
    monkeypatch, redis_mock: InMemoryRedis
):
    """US3: Cache-Control: no-cache on analysis endpoint bypasses HIT."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock.store["analysis:scan:latest:v1"] = json.dumps(
        {"available": True, "items": []}
    )
    fresh = {"items": [{"symbol": "TCS"}]}

    with patch(
        "app.routes.analysis.load_latest_scan",
        new_callable=AsyncMock,
        return_value=fresh,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/analysis/scan/latest", headers={"Cache-Control": "no-cache"}
            )

    assert response.status_code == 200
    assert response.headers.get("x-cache-status") == "MISS"
    assert response.json()["items"][0]["symbol"] == "TCS"


@pytest.mark.asyncio
async def test_force_false_does_not_bypass_hit(monkeypatch, redis_mock: InMemoryRedis):
    """Regression: force=false (default) still serves HIT when cache is warm."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock.store["scanner:latest:v1"] = json.dumps(SCANNER_PAYLOAD)

    db_mock = AsyncMock(return_value=FRESH_PAYLOAD)
    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        db_mock,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/scanner/latest?force=false")

    assert response.status_code == 200
    assert response.headers.get("x-cache-status") == "HIT"
    assert response.json()["scan_timestamp"] == SCANNER_PAYLOAD["scan_timestamp"]
    db_mock.assert_not_awaited()
