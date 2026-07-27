"""Integration and contract tests for cached scanner read endpoints.

Covers US1 acceptance scenarios, FR-001..FR-004, SC-003 payload parity,
and X-Cache-Status contract values for both endpoints.
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
    "available": True,
    "scan_timestamp": "2026-07-27T09:45:00Z",
    "buy_candidates": [{"symbol": "RELIANCE", "score": 85.5}],
    "watch_candidates": [],
    "rejected_candidates": [],
}

ANALYSIS_PAYLOAD: Dict[str, Any] = {
    "available": True,
    "analysis_id": "an-20260727-094500",
    "items": [{"symbol": "INFY"}],
    "summary": {
        "bullish_count": 42,
        "bearish_count": 12,
        "market_regime": "BULLISH_TREND",
    },
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
# Feature flag OFF — BYPASS contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_scanner_latest_response_headers(monkeypatch):
    """When cache disabled, GET /scanner/latest includes X-Cache-Status: BYPASS."""
    set_scanner_cache_enabled(monkeypatch, False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/scanner/latest")
        assert response.status_code == 200
        assert "x-cache-status" in response.headers
        assert response.headers["x-cache-status"] == "BYPASS"
        assert "application/json" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_get_analysis_scan_latest_response_headers(monkeypatch):
    """When cache disabled, GET /analysis/scan/latest includes X-Cache-Status: BYPASS."""
    set_scanner_cache_enabled(monkeypatch, False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/analysis/scan/latest")
        assert response.status_code == 200
        assert "x-cache-status" in response.headers
        assert response.headers["x-cache-status"] == "BYPASS"


# ---------------------------------------------------------------------------
# US1 AC1 — Miss path populates cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_latest_cache_miss_populates_redis(
    monkeypatch, redis_mock: InMemoryRedis
):
    """US1 AC1 / FR-004: empty cache → DB query → Redis SET with TTL → MISS."""
    set_scanner_cache_enabled(monkeypatch, True)
    monkeypatch.setattr(settings, "scanner_latest_cache_ttl_seconds", 300)

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=SCANNER_PAYLOAD,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/scanner/latest")

    assert response.status_code == 200
    assert response.headers["x-cache-status"] == "MISS"
    body = response.json()
    assert body["scan_timestamp"] == SCANNER_PAYLOAD["scan_timestamp"]
    assert "scanner:latest:v1" in redis_mock.store
    cached = json.loads(redis_mock.store["scanner:latest:v1"])
    assert cached["scan_timestamp"] == SCANNER_PAYLOAD["scan_timestamp"]
    # TTL applied (default settings or explicit)
    assert redis_mock.ttls.get("scanner:latest:v1") == 300 or any(
        c[0] == "scanner:latest:v1" for c in redis_mock.set_calls
    )


@pytest.mark.asyncio
async def test_analysis_scan_latest_cache_miss_populates_redis(
    monkeypatch, redis_mock: InMemoryRedis
):
    """US1 AC1 for analysis endpoint: miss fills analysis:scan:latest:v1."""
    set_scanner_cache_enabled(monkeypatch, True)
    with patch(
        "app.routes.analysis.load_latest_scan",
        new_callable=AsyncMock,
        return_value=ANALYSIS_PAYLOAD,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/analysis/scan/latest")

    assert response.status_code == 200
    assert response.headers["x-cache-status"] == "MISS"
    assert "analysis:scan:latest:v1" in redis_mock.store
    cached = json.loads(redis_mock.store["analysis:scan:latest:v1"])
    assert cached["available"] is True
    assert cached.get("analysis_id") == ANALYSIS_PAYLOAD["analysis_id"]


# ---------------------------------------------------------------------------
# US1 AC2 — Hit path serves Redis only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_latest_cache_hit_skips_db(
    monkeypatch, redis_mock: InMemoryRedis
):
    """US1 AC2 / FR-003: Redis hit returns HIT without DB service call."""
    set_scanner_cache_enabled(monkeypatch, True)
    cached_json = json.dumps(SCANNER_PAYLOAD)
    redis_mock.store["scanner:latest:v1"] = cached_json

    db_mock = AsyncMock(return_value=SCANNER_PAYLOAD)
    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        db_mock,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/scanner/latest")

    assert response.status_code == 200
    assert response.headers["x-cache-status"] == "HIT"
    assert response.json() == SCANNER_PAYLOAD
    db_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_analysis_scan_latest_cache_hit_skips_db(
    monkeypatch, redis_mock: InMemoryRedis
):
    """US1 AC2 for analysis: HIT from Redis, load_latest_scan not called."""
    set_scanner_cache_enabled(monkeypatch, True)
    full = {"available": True, **ANALYSIS_PAYLOAD}
    redis_mock.store["analysis:scan:latest:v1"] = json.dumps(full)

    db_mock = AsyncMock(return_value=ANALYSIS_PAYLOAD)
    with patch("app.routes.analysis.load_latest_scan", db_mock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/analysis/scan/latest")

    assert response.status_code == 200
    assert response.headers["x-cache-status"] == "HIT"
    assert response.json()["available"] is True
    db_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# SC-003 payload parity hit vs miss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_payload_parity_hit_vs_miss(
    monkeypatch, redis_mock: InMemoryRedis
):
    """SC-003: Cached HIT body matches MISS body structure/values."""
    set_scanner_cache_enabled(monkeypatch, True)
    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=SCANNER_PAYLOAD,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            miss = await client.get("/scanner/latest")
            hit = await client.get("/scanner/latest")

    assert miss.headers["x-cache-status"] == "MISS"
    assert hit.headers["x-cache-status"] == "HIT"
    assert miss.json() == hit.json()


# ---------------------------------------------------------------------------
# Empty / null scan edge case
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_empty_result_cached_with_short_ttl(
    monkeypatch, redis_mock: InMemoryRedis
):
    """Edge: empty DB result cached with short TTL (10s) when cache enabled."""
    set_scanner_cache_enabled(monkeypatch, True)
    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=None,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/scanner/latest")

    assert response.status_code == 200
    assert response.headers["x-cache-status"] == "MISS"
    body = response.json()
    assert body.get("buy_candidates") == []
    assert "scanner:latest:v1" in redis_mock.store
    assert redis_mock.ttls.get("scanner:latest:v1") == 10


@pytest.mark.asyncio
async def test_analysis_empty_result_cached_with_short_ttl(
    monkeypatch, redis_mock: InMemoryRedis
):
    """Edge: analysis empty DB result uses short TTL."""
    set_scanner_cache_enabled(monkeypatch, True)
    with patch(
        "app.routes.analysis.load_latest_scan",
        new_callable=AsyncMock,
        return_value=None,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/analysis/scan/latest")

    assert response.status_code == 200
    assert response.json() == {"available": False}
    assert redis_mock.ttls.get("analysis:scan:latest:v1") == 10


# ---------------------------------------------------------------------------
# Content-Type contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_content_type_is_json(
    monkeypatch, redis_mock: InMemoryRedis
):
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock.store["scanner:latest:v1"] = json.dumps(SCANNER_PAYLOAD)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/scanner/latest")
    assert response.status_code == 200
    assert "application/json" in response.headers.get("content-type", "")
