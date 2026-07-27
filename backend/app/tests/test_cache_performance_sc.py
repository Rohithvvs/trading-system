"""Automated checks for SC-001 / SC-002 style success criteria.

SC-001 (p95 < 10ms) is environment-dependent; CI asserts a conservative
budget that still proves the HIT path is cache-bound (not DB-bound).
SC-002 is validated as \"only one DB call on warm cache under polling\".
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from typing import Dict, Optional
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import settings
from app.main import app
from app.tests.cache_test_utils import set_scanner_cache_enabled


class InMemoryRedis:
    def __init__(self) -> None:
        self.store: Dict[str, str] = {}

    async def get(self, key: str) -> Optional[str]:
        return self.store.get(key)

    async def set(
        self, key: str, value: str, ex: Optional[int] = None, nx: bool = False
    ) -> bool:
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


PAYLOAD = {
    "scan_timestamp": "2026-07-27T09:45:00Z",
    "buy_candidates": [{"symbol": "RELIANCE", "score": 85.5}],
    "watch_candidates": [],
    "rejected_candidates": [],
}


@pytest.mark.asyncio
async def test_sc001_cache_hit_latency_budget(monkeypatch):
    """SC-001 proxy: warm HIT path p95 stays under a CI-safe budget (50ms)."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock = InMemoryRedis()
    redis_mock.store["scanner:latest:v1"] = json.dumps(PAYLOAD)
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )

    db_mock = AsyncMock(return_value=PAYLOAD)
    latencies_ms: list[float] = []

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        db_mock,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Warm + measure
            for _ in range(30):
                t0 = time.perf_counter()
                response = await client.get("/scanner/latest")
                latencies_ms.append((time.perf_counter() - t0) * 1000)
                assert response.status_code == 200
                assert response.headers.get("x-cache-status") == "HIT"

    db_mock.assert_not_awaited()
    latencies_ms.sort()
    p95 = latencies_ms[int(0.95 * (len(latencies_ms) - 1))]
    # Production target is <10ms; CI/shared runners get a looser budget.
    assert p95 < 50.0, f"HIT p95 too high: {p95:.2f}ms (samples={latencies_ms})"
    assert statistics.median(latencies_ms) < 30.0


@pytest.mark.asyncio
async def test_sc002_warm_poll_avoids_repeated_db(monkeypatch):
    """SC-002 proxy: repeated polls after warm miss use cache (1 DB call total)."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock = InMemoryRedis()
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )

    db_mock = AsyncMock(return_value=PAYLOAD)

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        db_mock,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.get("/scanner/latest")
            assert first.headers.get("x-cache-status") == "MISS"
            statuses = []
            for _ in range(20):
                r = await client.get("/scanner/latest")
                assert r.status_code == 200
                statuses.append(r.headers.get("x-cache-status"))

    assert db_mock.await_count == 1
    assert all(s == "HIT" for s in statuses)
    # >90% of these poll requests are HITs (20/21 overall including miss ≈ 95%)
    hit_ratio = statuses.count("HIT") / max(1, len(statuses))
    assert hit_ratio >= 0.90


@pytest.mark.asyncio
async def test_live_env_flag_toggle_without_settings_restart(monkeypatch):
    """Risk fix: flipping SCANNER_LATEST_CACHE_ENABLED in os.environ takes effect live."""
    redis_mock = InMemoryRedis()
    redis_mock.store["scanner:latest:v1"] = json.dumps(PAYLOAD)
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )
    db_mock = AsyncMock(return_value=PAYLOAD)

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        db_mock,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            monkeypatch.setenv("SCANNER_LATEST_CACHE_ENABLED", "false")
            off = await client.get("/scanner/latest")
            assert off.headers.get("x-cache-status") == "BYPASS"
            assert db_mock.await_count == 1

            monkeypatch.setenv("SCANNER_LATEST_CACHE_ENABLED", "true")
            on = await client.get("/scanner/latest")
            assert on.headers.get("x-cache-status") == "HIT"
            # No additional DB call — served from Redis after live enable
            assert db_mock.await_count == 1
