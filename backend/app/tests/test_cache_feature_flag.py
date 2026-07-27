"""Integration tests for dynamic feature flag SCANNER_LATEST_CACHE_ENABLED.

Maps to User Story 4, FR-001.
"""

from __future__ import annotations

import json
from typing import Dict, Optional
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import settings
from app.tests.cache_test_utils import set_scanner_cache_enabled
from app.main import app


class InMemoryRedis:
    def __init__(self) -> None:
        self.store: Dict[str, str] = {}
        self.get_calls: list = []
        self.set_calls: list = []

    async def get(self, key: str) -> Optional[str]:
        self.get_calls.append(key)
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
async def test_feature_flag_disabled_behavior(monkeypatch, redis_mock: InMemoryRedis):
    """US4: When flag is OFF, responses carry X-Cache-Status: BYPASS on both endpoints."""
    set_scanner_cache_enabled(monkeypatch, False)
    redis_mock.store["scanner:latest:v1"] = json.dumps({"stale": True})
    redis_mock.store["analysis:scan:latest:v1"] = json.dumps({"stale": True})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res1 = await client.get("/scanner/latest")
        assert res1.status_code == 200
        assert res1.headers.get("x-cache-status") == "BYPASS"

        res2 = await client.get("/analysis/scan/latest")
        assert res2.status_code == 200
        assert res2.headers.get("x-cache-status") == "BYPASS"

    # FR-001 OFF: no Redis read or write
    assert redis_mock.get_calls == []
    assert redis_mock.set_calls == []


@pytest.mark.asyncio
async def test_feature_flag_enabled_behavior(monkeypatch, redis_mock: InMemoryRedis):
    """When flag is ON, responses carry X-Cache-Status: MISS or HIT."""
    set_scanner_cache_enabled(monkeypatch, True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/scanner/latest")
        assert res.status_code == 200
        assert res.headers.get("x-cache-status") in ("MISS", "HIT")


@pytest.mark.asyncio
async def test_feature_flag_off_ignores_warm_cache(
    monkeypatch, redis_mock: InMemoryRedis
):
    """US4 AC: Flag false never serves Redis payload even if key is warm."""
    set_scanner_cache_enabled(monkeypatch, False)
    redis_mock.store["scanner:latest:v1"] = json.dumps(
        {
            "scan_timestamp": "FROM_CACHE",
            "buy_candidates": [{"symbol": "CACHE_ONLY"}],
            "watch_candidates": [],
            "rejected_candidates": [],
        }
    )
    db_payload = {
        "scan_timestamp": "FROM_DB",
        "buy_candidates": [{"symbol": "DB_ONLY"}],
        "watch_candidates": [],
        "rejected_candidates": [],
    }

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new_callable=AsyncMock,
        return_value=db_payload,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/scanner/latest")

    assert res.status_code == 200
    assert res.headers.get("x-cache-status") == "BYPASS"
    assert res.json()["scan_timestamp"] == "FROM_DB"
    assert redis_mock.get_calls == []


@pytest.mark.asyncio
async def test_feature_flag_toggle_runtime(
    monkeypatch, redis_mock: InMemoryRedis
):
    """US4: Runtime toggle from OFF→ON switches BYPASS to HIT/MISS without redeploy."""
    redis_mock.store["scanner:latest:v1"] = json.dumps(
        {
            "scan_timestamp": "CACHED",
            "buy_candidates": [],
            "watch_candidates": [],
            "rejected_candidates": [],
        }
    )

    set_scanner_cache_enabled(monkeypatch, False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        off = await client.get("/scanner/latest")
        assert off.headers.get("x-cache-status") == "BYPASS"

        set_scanner_cache_enabled(monkeypatch, True)
        on = await client.get("/scanner/latest")
        assert on.headers.get("x-cache-status") == "HIT"
        assert on.json()["scan_timestamp"] == "CACHED"
