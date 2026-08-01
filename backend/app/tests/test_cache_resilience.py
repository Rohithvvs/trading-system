"""Resilience and failure recovery tests for Redis timeout and connection errors.

Maps to User Story 5, FR-008, FR-009, SC-005.
"""

from __future__ import annotations

import asyncio
import json
from typing import Dict, Optional
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import settings
from app.tests.cache_test_utils import set_scanner_cache_enabled
from app.main import app


DB_PAYLOAD = {
    "scan_timestamp": "2026-07-27T09:45:00Z",
    "buy_candidates": [{"symbol": "RELIANCE", "score": 85.5}],
    "watch_candidates": [],
    "rejected_candidates": [],
}


class MockFailingRedis:
    async def get(self, key):
        raise ConnectionError("Simulated Redis Outage")

    async def set(self, key, value, ex=None, nx=False):
        raise ConnectionError("Simulated Redis Outage")

    async def delete(self, *keys):
        raise ConnectionError("Simulated Redis Outage")


class MockTimeoutRedis:
    def __init__(self, delay_sec: float = 0.2) -> None:
        self.delay_sec = delay_sec

    async def get(self, key):
        await asyncio.sleep(self.delay_sec)
        return None

    async def set(self, key, value, ex=None, nx=False):
        await asyncio.sleep(self.delay_sec)
        return True

    async def delete(self, *keys):
        return 0


class InMemoryRedis:
    def __init__(self) -> None:
        self.store: Dict[str, str] = {}
        self.fail_set = False

    async def get(self, key: str) -> Optional[str]:
        return self.store.get(key)

    async def set(
        self, key: str, value: str, ex: Optional[int] = None, nx: bool = False
    ) -> bool:
        if self.fail_set:
            raise ConnectionError("write failed")
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                n += 1
        return n


@pytest.mark.asyncio
async def test_redis_failure_fallback_returns_http_200(monkeypatch):
    """US5 / SC-005: Redis connection failure still returns HTTP 200 from DB."""
    set_scanner_cache_enabled(monkeypatch, True)
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: MockFailingRedis(),
    )

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=DB_PAYLOAD,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/scanner/latest")

    assert response.status_code == 200
    assert response.headers.get("x-cache-status") == "FALLBACK"
    assert response.json()["scan_timestamp"] == DB_PAYLOAD["scan_timestamp"]


@pytest.mark.asyncio
async def test_redis_failure_analysis_endpoint_returns_http_200(monkeypatch):
    """US5: Analysis endpoint also survives Redis outage with HTTP 200."""
    set_scanner_cache_enabled(monkeypatch, True)
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: MockFailingRedis(),
    )
    analysis_data = {"items": [{"symbol": "INFY"}], "scan_timestamp": "t1"}

    with patch(
        "app.routes.analysis.load_latest_scan",
        new_callable=AsyncMock,
        return_value=analysis_data,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/analysis/scan/latest")

    assert response.status_code == 200
    assert response.headers.get("x-cache-status") == "FALLBACK"
    assert response.json()["available"] is True


@pytest.mark.asyncio
async def test_redis_timeout_falls_back_to_db(monkeypatch):
    """US5 / Edge: Redis read timeout (>50ms) falls back without 5xx."""
    set_scanner_cache_enabled(monkeypatch, True)
    monkeypatch.setattr(settings, "redis_cache_read_timeout_ms", 20)
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: MockTimeoutRedis(delay_sec=0.15),
    )

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=DB_PAYLOAD,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/scanner/latest")

    assert response.status_code == 200
    assert response.headers.get("x-cache-status") == "FALLBACK"
    assert response.json()["buy_candidates"][0]["symbol"] == "RELIANCE"


@pytest.mark.asyncio
async def test_redis_client_none_falls_back(monkeypatch):
    """FR-008: get_redis_client() returning None must not produce 5xx."""
    set_scanner_cache_enabled(monkeypatch, True)
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: None,
    )

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=DB_PAYLOAD,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/scanner/latest")

    assert response.status_code == 200
    assert response.headers.get("x-cache-status") == "FALLBACK"
    assert response.json()["scan_timestamp"] == DB_PAYLOAD["scan_timestamp"]


@pytest.mark.asyncio
async def test_redis_write_failure_still_returns_db_payload(monkeypatch):
    """Redis write failure after miss: client still receives DB JSON HTTP 200."""
    set_scanner_cache_enabled(monkeypatch, True)
    mock = InMemoryRedis()
    mock.fail_set = True
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: mock,
    )

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=DB_PAYLOAD,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/scanner/latest")

    assert response.status_code == 200
    assert response.json() == DB_PAYLOAD


@pytest.mark.asyncio
async def test_no_5xx_on_repeated_redis_errors(monkeypatch):
    """SC-005: Multiple consecutive Redis failures still return 200."""
    set_scanner_cache_enabled(monkeypatch, True)
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: MockFailingRedis(),
    )

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=DB_PAYLOAD,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(5):
                response = await client.get("/scanner/latest")
                assert response.status_code == 200
                assert response.headers.get("x-cache-status") == "FALLBACK"


@pytest.mark.asyncio
async def test_corrupted_cache_json_evicted_and_refills(monkeypatch):
    """Edge: corrupt Redis payload is deleted and replaced from DB."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock = InMemoryRedis()
    redis_mock.store["scanner:latest:v1"] = "{not-valid-json"
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=DB_PAYLOAD,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/scanner/latest")

    assert response.status_code == 200
    assert response.json()["scan_timestamp"] == DB_PAYLOAD["scan_timestamp"]
    assert "scanner:latest:v1" in redis_mock.store
    assert json.loads(redis_mock.store["scanner:latest:v1"])["scan_timestamp"] == (
        DB_PAYLOAD["scan_timestamp"]
    )
