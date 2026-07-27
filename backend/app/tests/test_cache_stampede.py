"""Concurrency / stampede tests for scanner cache singleflight.

Maps to Edge Case "Cache Stampede", FR-010, SC-004 (service-level + multi-worker).
"""

from __future__ import annotations

import asyncio
import json
from typing import Dict, Optional

import pytest

from app.config.settings import settings
from app.tests.cache_test_utils import set_scanner_cache_enabled
from app.services.scanner_cache_service import ScannerCacheService, lock_key_for


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


@pytest.mark.asyncio
async def test_stampede_hundred_concurrent_misses_single_db_query(monkeypatch):
    """SC-004: 100 concurrent singleflight misses → exactly one DB fetch."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock = InMemoryRedis()
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )
    service = ScannerCacheService()

    call_count = 0
    max_parallel = 0
    in_flight = 0

    async def db_fetch():
        nonlocal call_count, max_parallel, in_flight
        call_count += 1
        in_flight += 1
        max_parallel = max(max_parallel, in_flight)
        await asyncio.sleep(0.03)
        payload = json.dumps({"n": call_count, "source": "db"})
        redis_mock.store["scanner:latest:v1"] = payload
        in_flight -= 1
        return payload

    results = await asyncio.gather(
        *[
            service.execute_singleflight("scanner:latest:v1", db_fetch)
            for _ in range(100)
        ]
    )

    assert call_count == 1
    assert max_parallel == 1
    statuses = [status for _, status in results]
    assert statuses.count("MISS") == 1
    assert statuses.count("HIT") == 99
    # All clients observe the same populated payload
    payloads = {data for data, _ in results}
    assert len(payloads) == 1


@pytest.mark.asyncio
async def test_stampede_independent_keys_do_not_share_lock(monkeypatch):
    """Different cache keys use independent locks and may fetch in parallel."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock = InMemoryRedis()
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )
    service = ScannerCacheService()

    in_flight = 0
    max_parallel = 0

    async def fetch_a():
        nonlocal in_flight, max_parallel
        in_flight += 1
        max_parallel = max(max_parallel, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return '{"k":"a"}'

    async def fetch_b():
        nonlocal in_flight, max_parallel
        in_flight += 1
        max_parallel = max(max_parallel, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return '{"k":"b"}'

    await asyncio.gather(
        service.execute_singleflight("key:a", fetch_a),
        service.execute_singleflight("key:b", fetch_b),
    )

    # Independent keys can run concurrently
    assert max_parallel == 2


@pytest.mark.asyncio
async def test_multi_worker_stampede_single_db_fetch(monkeypatch):
    """M1: Two service instances (simulating workers) share one DB refill via Redis NX lock."""
    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock = InMemoryRedis()
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )
    worker_a = ScannerCacheService()
    worker_b = ScannerCacheService()

    call_count = 0
    max_parallel = 0
    in_flight = 0
    cache_key = "scanner:latest:v1"

    async def db_fetch():
        nonlocal call_count, max_parallel, in_flight
        call_count += 1
        in_flight += 1
        max_parallel = max(max_parallel, in_flight)
        await asyncio.sleep(0.08)
        payload = json.dumps({"n": call_count, "source": "db"})
        redis_mock.store[cache_key] = payload
        in_flight -= 1
        return payload

    results = await asyncio.gather(
        *[worker_a.execute_singleflight(cache_key, db_fetch) for _ in range(15)],
        *[worker_b.execute_singleflight(cache_key, db_fetch) for _ in range(15)],
    )

    assert call_count == 1
    assert max_parallel == 1
    statuses = [s for _, s in results]
    assert statuses.count("MISS") == 1
    assert statuses.count("HIT") == 29
    assert lock_key_for(cache_key) not in redis_mock.store  # released after refill


@pytest.mark.asyncio
async def test_route_level_stampede_single_db_fetch(monkeypatch):
    """FR-010 / SC-004: concurrent HTTP misses to /scanner/latest → one DB fetch."""
    from unittest.mock import AsyncMock, patch

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    set_scanner_cache_enabled(monkeypatch, True)
    redis_mock = InMemoryRedis()
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )

    call_count = 0
    in_flight = 0
    max_parallel = 0
    payload = {
        "scan_timestamp": "2026-07-27T09:45:00Z",
        "buy_candidates": [{"symbol": "RELIANCE", "score": 85.5}],
        "watch_candidates": [],
        "rejected_candidates": [],
    }

    async def db_fetch(*_a, **_k):
        nonlocal call_count, in_flight, max_parallel
        call_count += 1
        in_flight += 1
        max_parallel = max(max_parallel, in_flight)
        await asyncio.sleep(0.03)
        in_flight -= 1
        return payload

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
        new=AsyncMock(side_effect=db_fetch),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            responses = await asyncio.gather(
                *[client.get("/scanner/latest") for _ in range(25)]
            )

    assert call_count == 1
    assert max_parallel == 1
    assert all(r.status_code == 200 for r in responses)
    bodies = {r.text for r in responses}
    assert len(bodies) == 1
    # One MISS fills; remaining HIT under singleflight.
    statuses = [r.headers.get("x-cache-status") for r in responses]
    assert statuses.count("MISS") == 1
    assert statuses.count("HIT") == 24
