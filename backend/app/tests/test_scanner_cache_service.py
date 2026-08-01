"""Unit tests for ScannerCacheService: hit/miss, TTL, singleflight, timeouts, invalidate.

Maps to FR-002..FR-010 and Edge Cases (stampede, timeout, Redis unavailable).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from app.config.settings import settings
from app.tests.cache_test_utils import set_scanner_cache_enabled
from app.services.scanner_cache_service import ScannerCacheService


class InMemoryRedis:
    """Minimal async Redis stand-in for deterministic unit tests."""

    def __init__(self) -> None:
        self.store: Dict[str, str] = {}
        self.ttls: Dict[str, int] = {}
        self.get_calls: List[str] = []
        self.set_calls: List[tuple] = []
        self.delete_calls: List[tuple] = []
        self.fail_get: Optional[BaseException] = None
        self.fail_set: Optional[BaseException] = None
        self.fail_delete: Optional[BaseException] = None
        self.get_delay_sec: float = 0.0
        self.set_delay_sec: float = 0.0

    async def get(self, key: str) -> Optional[str]:
        self.get_calls.append(key)
        if self.get_delay_sec:
            await asyncio.sleep(self.get_delay_sec)
        if self.fail_get is not None:
            raise self.fail_get
        return self.store.get(key)

    async def set(
        self, key: str, value: str, ex: Optional[int] = None, nx: bool = False
    ) -> bool:
        self.set_calls.append((key, value, ex, nx))
        if self.set_delay_sec:
            await asyncio.sleep(self.set_delay_sec)
        if self.fail_set is not None:
            raise self.fail_set
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        self.delete_calls.append(keys)
        if self.fail_delete is not None:
            raise self.fail_delete
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                self.ttls.pop(key, None)
                removed += 1
        return removed


@pytest.fixture
def redis_mock() -> InMemoryRedis:
    return InMemoryRedis()


@pytest.fixture
def service(monkeypatch, redis_mock: InMemoryRedis) -> ScannerCacheService:
    set_scanner_cache_enabled(monkeypatch, True)
    monkeypatch.setattr(settings, "scanner_latest_cache_ttl_seconds", 300)
    monkeypatch.setattr(settings, "redis_cache_read_timeout_ms", 50)
    monkeypatch.setattr(settings, "redis_cache_write_timeout_ms", 100)
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )
    return ScannerCacheService()


# ---------------------------------------------------------------------------
# Feature flag / disabled path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_disabled_returns_none(monkeypatch, redis_mock: InMemoryRedis):
    """FR-001: When SCANNER_LATEST_CACHE_ENABLED is False, get_latest_scan returns None."""
    set_scanner_cache_enabled(monkeypatch, False)
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: redis_mock,
    )
    service = ScannerCacheService()
    redis_mock.store["scanner:latest:v1"] = '{"available": true}'

    result = await service.get_latest_scan("scanner:latest:v1")

    assert result is None
    assert redis_mock.get_calls == []


@pytest.mark.asyncio
async def test_cache_disabled_does_not_require_redis(monkeypatch):
    """Flag OFF must not attempt Redis client usage for reads."""
    set_scanner_cache_enabled(monkeypatch, False)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        raise AssertionError("get_redis_client must not be called when cache disabled")

    monkeypatch.setattr("app.services.scanner_cache_service.get_redis_client", boom)
    service = ScannerCacheService()
    assert await service.get_latest_scan("scanner:latest:v1") is None
    assert called["n"] == 0


# ---------------------------------------------------------------------------
# Hit / Miss / Set with TTL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_returns_payload(service: ScannerCacheService, redis_mock: InMemoryRedis):
    """FR-003: Cache hit returns pre-serialized JSON string from Redis."""
    payload = json.dumps({"available": True, "items": [{"symbol": "RELIANCE"}]})
    redis_mock.store["scanner:latest:v1"] = payload

    result = await service.get_latest_scan("scanner:latest:v1")

    assert result == payload
    assert redis_mock.get_calls == ["scanner:latest:v1"]


@pytest.mark.asyncio
async def test_cache_miss_returns_none(service: ScannerCacheService, redis_mock: InMemoryRedis):
    """FR-004 path: empty Redis yields None (caller queries DB)."""
    result = await service.get_latest_scan("scanner:latest:v1")
    assert result is None
    assert redis_mock.get_calls == ["scanner:latest:v1"]


@pytest.mark.asyncio
async def test_set_and_get_roundtrip(service: ScannerCacheService, redis_mock: InMemoryRedis):
    """Verify set_latest_scan stores payload and get_latest_scan retrieves it."""
    test_key = "scanner:latest:v1"
    test_payload = '{"available": true, "items": [{"symbol": "RELIANCE"}]}'

    set_success = await service.set_latest_scan(test_key, test_payload, ttl_seconds=60)
    result = await service.get_latest_scan(test_key)

    assert set_success is True
    assert result == test_payload
    assert redis_mock.ttls[test_key] == 60


@pytest.mark.asyncio
async def test_set_uses_default_ttl_from_settings(
    service: ScannerCacheService, redis_mock: InMemoryRedis, monkeypatch
):
    """FR-004: Default TTL is SCANNER_LATEST_CACHE_TTL_SECONDS (300)."""
    monkeypatch.setattr(settings, "scanner_latest_cache_ttl_seconds", 300)
    ok = await service.set_latest_scan("scanner:latest:v1", '{"a":1}')
    assert ok is True
    assert redis_mock.set_calls[-1][2] == 300  # ex=TTL


@pytest.mark.asyncio
async def test_set_empty_payload_with_short_ttl(
    service: ScannerCacheService, redis_mock: InMemoryRedis
):
    """Edge: empty/null scan may be cached with short TTL (10s)."""
    empty = json.dumps({"available": False})
    ok = await service.set_latest_scan("analysis:scan:latest:v1", empty, ttl_seconds=10)
    assert ok is True
    assert redis_mock.ttls["analysis:scan:latest:v1"] == 10
    assert await service.get_latest_scan("analysis:scan:latest:v1") == empty


# ---------------------------------------------------------------------------
# Invalidate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_purges_keys(service: ScannerCacheService, redis_mock: InMemoryRedis):
    """FR-005/US2: invalidate_scan_cache removes specified keys."""
    redis_mock.store["scanner:latest:v1"] = "{}"
    redis_mock.store["analysis:scan:latest:v1"] = "{}"

    ok = await service.invalidate_scan_cache(
        ["scanner:latest:v1", "analysis:scan:latest:v1"]
    )

    assert ok is True
    assert "scanner:latest:v1" not in redis_mock.store
    assert "analysis:scan:latest:v1" not in redis_mock.store


@pytest.mark.asyncio
async def test_invalidate_empty_keys_returns_false(
    service: ScannerCacheService, redis_mock: InMemoryRedis
):
    assert await service.invalidate_scan_cache([]) is False
    assert redis_mock.delete_calls == []


# ---------------------------------------------------------------------------
# Redis unavailable / errors / timeouts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_none_when_redis_client_unavailable(monkeypatch):
    """FR-008: Unavailable Redis client must not raise; returns None."""
    set_scanner_cache_enabled(monkeypatch, True)
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: None,
    )
    service = ScannerCacheService()
    assert await service.get_latest_scan("scanner:latest:v1") is None


@pytest.mark.asyncio
async def test_set_returns_false_when_redis_client_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.services.scanner_cache_service.get_redis_client",
        lambda: None,
    )
    service = ScannerCacheService()
    assert await service.set_latest_scan("k", "{}") is False


@pytest.mark.asyncio
async def test_get_connection_error_returns_none(
    service: ScannerCacheService, redis_mock: InMemoryRedis
):
    """FR-008: Connection errors are swallowed; None returned for DB fallback."""
    redis_mock.fail_get = ConnectionError("Simulated Redis Outage")
    assert await service.get_latest_scan("scanner:latest:v1") is None


@pytest.mark.asyncio
async def test_get_timeout_returns_none(
    service: ScannerCacheService, redis_mock: InMemoryRedis, monkeypatch
):
    """Edge/FR: Redis read timeout (> configured ms) falls back without raising."""
    monkeypatch.setattr(settings, "redis_cache_read_timeout_ms", 20)
    redis_mock.get_delay_sec = 0.15  # exceed 20ms timeout

    result = await service.get_latest_scan("scanner:latest:v1")

    assert result is None


@pytest.mark.asyncio
async def test_set_timeout_returns_false(
    service: ScannerCacheService, redis_mock: InMemoryRedis, monkeypatch
):
    """Write timeout returns False; caller still serves DB response."""
    monkeypatch.setattr(settings, "redis_cache_write_timeout_ms", 20)
    redis_mock.set_delay_sec = 0.15

    ok = await service.set_latest_scan("scanner:latest:v1", '{"x":1}', ttl_seconds=60)

    assert ok is False


@pytest.mark.asyncio
async def test_set_write_error_returns_false(
    service: ScannerCacheService, redis_mock: InMemoryRedis
):
    redis_mock.fail_set = ConnectionError("write refused")
    assert await service.set_latest_scan("k", "{}") is False


@pytest.mark.asyncio
async def test_invalidate_error_returns_false(
    service: ScannerCacheService, redis_mock: InMemoryRedis
):
    redis_mock.fail_delete = ConnectionError("delete failed")
    redis_mock.store["scanner:latest:v1"] = "{}"
    assert await service.invalidate_scan_cache(["scanner:latest:v1"]) is False


# ---------------------------------------------------------------------------
# Singleflight / stampede
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_singleflight_execution(service: ScannerCacheService, redis_mock: InMemoryRedis):
    """FR-010: singleflight executes DB fetch on miss and returns MISS status."""
    call_count = 0

    async def mock_db_fetch():
        nonlocal call_count
        call_count += 1
        return '{"data": "fresh_from_db"}'

    res_data, status = await service.execute_singleflight(
        "test:singleflight:v1", mock_db_fetch
    )

    assert status == "MISS"
    assert res_data == '{"data": "fresh_from_db"}'
    assert call_count == 1


@pytest.mark.asyncio
async def test_singleflight_returns_hit_when_filled_under_lock(
    service: ScannerCacheService, redis_mock: InMemoryRedis
):
    """Inside lock, if cache was filled by peer, return HIT without calling DB."""
    redis_mock.store["lock-key"] = '{"from": "cache"}'
    called = 0

    async def mock_db_fetch():
        nonlocal called
        called += 1
        return '{"from": "db"}'

    res_data, status = await service.execute_singleflight("lock-key", mock_db_fetch)

    assert status == "HIT"
    assert res_data == '{"from": "cache"}'
    assert called == 0


@pytest.mark.asyncio
async def test_singleflight_stampede_only_one_db_fetch(
    service: ScannerCacheService, redis_mock: InMemoryRedis
):
    """Edge: concurrent miss — only one DB fetch executes under the key lock.

    Note: callers waiting outside the lock re-check cache; this test validates
    mutual exclusion so concurrent fetch_coro executions do not overlap.
    """
    call_count = 0
    in_flight = 0
    max_in_flight = 0

    async def mock_db_fetch():
        nonlocal call_count, in_flight, max_in_flight
        call_count += 1
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        # Populate cache so subsequent lock holders can HIT
        redis_mock.store["stampede:key"] = json.dumps({"n": call_count})
        return redis_mock.store["stampede:key"]

    results = await asyncio.gather(
        *[
            service.execute_singleflight("stampede:key", mock_db_fetch)
            for _ in range(20)
        ]
    )

    assert max_in_flight == 1
    # First waiter runs DB; others should observe HIT after cache fill
    statuses = [s for _, s in results]
    assert statuses.count("MISS") == 1
    assert statuses.count("HIT") == 19
    assert call_count == 1


# ---------------------------------------------------------------------------
# Serialization parity (service-level)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cached_payload_is_byte_for_byte_identical(
    service: ScannerCacheService, redis_mock: InMemoryRedis
):
    """SC-003: Cached payload is exact serialized string written to Redis."""
    original = json.dumps(
        {
            "available": True,
            "scan_timestamp": "2026-07-27T09:45:00Z",
            "buy_candidates": [{"symbol": "TCS", "score": 91.2}],
            "watch_candidates": [],
            "rejected_candidates": [],
        },
        separators=(",", ":"),
    )
    await service.set_latest_scan("scanner:latest:v1", original, ttl_seconds=300)
    cached = await service.get_latest_scan("scanner:latest:v1")
    assert cached == original
    assert json.loads(cached) == json.loads(original)


@pytest.mark.asyncio
async def test_corrupt_json_evicted_returns_none(
    service: ScannerCacheService, redis_mock: InMemoryRedis
):
    """Corrupt payload is deleted and treated as miss."""
    redis_mock.store["scanner:latest:v1"] = "{broken"
    result = await service.lookup_latest_scan("scanner:latest:v1")
    assert result.payload is None
    assert result.status == "MISS"
    assert "scanner:latest:v1" not in redis_mock.store


@pytest.mark.asyncio
async def test_lookup_redis_error_status_fallback(
    service: ScannerCacheService, redis_mock: InMemoryRedis
):
    redis_mock.fail_get = ConnectionError("down")
    result = await service.lookup_latest_scan("scanner:latest:v1")
    assert result.payload is None
    assert result.status == "FALLBACK"
    assert result.redis_error is True


@pytest.mark.asyncio
async def test_resolve_hit_and_miss(
    service: ScannerCacheService, redis_mock: InMemoryRedis
):
    redis_mock.store["k"] = json.dumps({"ok": True})
    payload, status = await service.resolve_latest_scan(
        "k", AsyncMock(return_value='{"db":true}')
    )
    assert status == "HIT"
    assert json.loads(payload)["ok"] is True

    redis_mock.store.clear()
    produce = AsyncMock(return_value=json.dumps({"db": True}))

    async def produce_and_set() -> str:
        body = await produce()
        await service.set_latest_scan("k", body)
        return body

    payload2, status2 = await service.resolve_latest_scan("k", produce_and_set)
    assert status2 == "MISS"
    assert json.loads(payload2)["db"] is True
    produce.assert_awaited_once()


@pytest.mark.asyncio
async def test_typed_exceptions_are_used_on_timeout(
    service: ScannerCacheService, redis_mock: InMemoryRedis, monkeypatch
):
    """L3: Redis timeouts surface as RedisCacheTimeoutException internally."""
    from app.core.exceptions import RedisCacheTimeoutException

    monkeypatch.setattr(settings, "redis_cache_read_timeout_ms", 20)
    redis_mock.get_delay_sec = 0.15
    with pytest.raises(RedisCacheTimeoutException):
        await service._redis_get(redis_mock, "scanner:latest:v1")


@pytest.mark.asyncio
async def test_lock_key_naming_matches_contract():
    from app.services.scanner_cache_service import lock_key_for

    assert lock_key_for("scanner:latest:v1") == "lock:scanner:latest:v1"
    assert lock_key_for("analysis:scan:latest:v1") == "lock:analysis:scan:latest:v1"
