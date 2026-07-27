"""Scanner Cache Service: non-blocking Redis caching, active pre-warming,

singleflight stampede prevention (in-process + distributed Redis lock),
JSON validation, and graceful DB fallback.

Concurrency (audit M1 / FR-010 / SC-004):
  1. In-process ``asyncio.Lock`` serializes concurrent tasks in one worker.
  2. Redis ``SET lock:{key} NX EX`` serializes refills across workers/hosts.
  Waiters that do not acquire the distributed lock poll for the filled cache
  key instead of hammering PostgreSQL.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from app.config.settings import settings
from app.core.exceptions import (
    RedisCacheConnectionException,
    RedisCacheTimeoutException,
    ScannerCacheException,
)
from app.core.redis import get_redis_client
from app.observability.metrics import record_scanner_cache_error

logger = logging.getLogger("app.services.scanner_cache_service")

ProduceJson = Callable[[], Awaitable[str]]

# Spec §10.2 lock key prefix: lock:scanner:latest:v1 / lock:analysis:scan:latest:v1
_LOCK_KEY_PREFIX = "lock:"
# Bound how long a worker may hold the distributed refill lock (seconds).
_DISTRIBUTED_LOCK_TTL_SEC = 5
# Max time waiters poll for a peer-filled cache entry (seconds).
_CACHE_WAIT_MAX_SEC = 2.0
_CACHE_WAIT_POLL_SEC = 0.02


def wants_force_refresh(force: bool, cache_control_header: Optional[str] = None) -> bool:
    """True when ?force=true or Cache-Control includes no-cache."""
    header = (cache_control_header or "").lower()
    return bool(force) or ("no-cache" in header)


def lock_key_for(cache_key: str) -> str:
    """Redis lock key for stampede protection (contract naming)."""
    return f"{_LOCK_KEY_PREFIX}{cache_key}"


@dataclass(frozen=True)
class CacheLookupResult:
    """Result of a cache GET attempt (typed miss vs Redis failure — audit M4/H3)."""

    payload: Optional[str]
    status: str  # HIT | MISS | FALLBACK | BYPASS
    redis_error: bool = False


class ScannerCacheService:
    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_key_lock(self, key: str) -> asyncio.Lock:
        """Retrieve or create an in-process asyncio.Lock for the specified cache key."""
        async with self._global_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    @staticmethod
    def _is_valid_json(payload: str) -> bool:
        try:
            json.loads(payload)
            return True
        except (TypeError, ValueError, json.JSONDecodeError):
            return False

    def _read_timeout_sec(self) -> float:
        return max(0.005, settings.redis_cache_read_timeout_ms / 1000.0)

    def _write_timeout_sec(self) -> float:
        return max(0.010, settings.redis_cache_write_timeout_ms / 1000.0)

    async def _redis_get(self, client, key: str) -> Optional[str]:
        """Low-level GET; raises typed cache exceptions (audit L3)."""
        try:
            return await asyncio.wait_for(client.get(key), timeout=self._read_timeout_sec())
        except asyncio.TimeoutError as exc:
            raise RedisCacheTimeoutException(
                f"Redis GET timeout (>{settings.redis_cache_read_timeout_ms}ms) key={key}"
            ) from exc
        except RedisCacheTimeoutException:
            raise
        except Exception as exc:
            raise RedisCacheConnectionException(f"Redis GET failed key={key}: {exc}") from exc

    async def _redis_set(
        self, client, key: str, value: str, *, ex: Optional[int] = None, nx: bool = False
    ) -> bool:
        """Low-level SET; raises typed cache exceptions (audit L3)."""
        try:
            if nx:
                result = await asyncio.wait_for(
                    client.set(key, value, ex=ex, nx=True),
                    timeout=self._write_timeout_sec(),
                )
            else:
                result = await asyncio.wait_for(
                    client.set(key, value, ex=ex),
                    timeout=self._write_timeout_sec(),
                )
            # redis-py: NX miss returns None/False; success returns True
            return bool(result) if nx else True
        except asyncio.TimeoutError as exc:
            raise RedisCacheTimeoutException(
                f"Redis SET timeout (>{settings.redis_cache_write_timeout_ms}ms) key={key}"
            ) from exc
        except RedisCacheTimeoutException:
            raise
        except Exception as exc:
            raise RedisCacheConnectionException(f"Redis SET failed key={key}: {exc}") from exc

    async def _redis_delete(self, client, *keys: str) -> None:
        try:
            await asyncio.wait_for(client.delete(*keys), timeout=self._write_timeout_sec())
        except asyncio.TimeoutError as exc:
            raise RedisCacheTimeoutException(f"Redis DELETE timeout keys={keys}") from exc
        except RedisCacheTimeoutException:
            raise
        except Exception as exc:
            raise RedisCacheConnectionException(f"Redis DELETE failed keys={keys}: {exc}") from exc

    async def lookup_latest_scan(self, key: str) -> CacheLookupResult:
        """Fetch cache entry with status distinguishing miss vs Redis failure.

        On corrupt JSON: log, evict key, return MISS so caller refills from DB.
        """
        if not settings.is_scanner_latest_cache_enabled():
            logger.debug("Cache lookup bypassed | SCANNER_LATEST_CACHE_ENABLED=false")
            return CacheLookupResult(payload=None, status="BYPASS", redis_error=False)

        client = get_redis_client()
        if client is None:
            logger.warning("Redis client unavailable | falling back to DB read | key=%s", key)
            record_scanner_cache_error("get")
            return CacheLookupResult(payload=None, status="FALLBACK", redis_error=True)

        try:
            payload = await self._redis_get(client, key)
            if not payload:
                logger.debug("Cache MISS | key=%s", key)
                return CacheLookupResult(payload=None, status="MISS", redis_error=False)

            if not self._is_valid_json(payload):
                logger.error("Corrupted cache JSON | key=%s | evicting and falling back to DB", key)
                record_scanner_cache_error("corrupt")
                try:
                    await self._redis_delete(client, key)
                except ScannerCacheException as del_exc:
                    logger.warning("Failed to evict corrupted key | key=%s | err=%s", key, del_exc)
                    record_scanner_cache_error("delete")
                return CacheLookupResult(payload=None, status="MISS", redis_error=False)

            logger.debug("Cache HIT | key=%s | size=%d", key, len(payload))
            return CacheLookupResult(payload=payload, status="HIT", redis_error=False)
        except RedisCacheTimeoutException as exc:
            logger.warning("%s | falling back to DB", exc)
            record_scanner_cache_error("get")
            return CacheLookupResult(payload=None, status="FALLBACK", redis_error=True)
        except RedisCacheConnectionException as exc:
            logger.warning("%s | falling back to DB", exc)
            record_scanner_cache_error("get")
            return CacheLookupResult(payload=None, status="FALLBACK", redis_error=True)

    async def get_latest_scan(self, key: str) -> Optional[str]:
        """Fetch pre-serialized JSON string from Redis.

        Returns None on cache miss, feature flag disabled, corrupt payload, or Redis error.
        """
        result = await self.lookup_latest_scan(key)
        return result.payload

    async def set_latest_scan(
        self, key: str, payload_json: str, ttl_seconds: Optional[int] = None
    ) -> bool:
        """Store pre-serialized JSON string into Redis cache with TTL.

        Used for Cache Miss refills and background worker Active Pre-Warming.
        """
        client = get_redis_client()
        if client is None:
            logger.warning("Redis client unavailable for write | key=%s", key)
            record_scanner_cache_error("set")
            return False

        ttl = ttl_seconds if ttl_seconds is not None else settings.scanner_latest_cache_ttl_seconds

        try:
            await self._redis_set(client, key, payload_json, ex=ttl, nx=False)
            logger.debug(
                "Cache SET success | key=%s | ttl=%ds | size=%d", key, ttl, len(payload_json)
            )
            return True
        except RedisCacheTimeoutException as exc:
            logger.warning("%s", exc)
            record_scanner_cache_error("set")
            return False
        except RedisCacheConnectionException as exc:
            logger.warning("%s", exc)
            record_scanner_cache_error("set")
            return False

    async def invalidate_scan_cache(self, keys: List[str]) -> bool:
        """Purge specified cache keys from Redis."""
        client = get_redis_client()
        if client is None or not keys:
            if client is None and keys:
                record_scanner_cache_error("delete")
            return False

        try:
            await self._redis_delete(client, *keys)
            logger.info("Cache keys purged | keys=%s", keys)
            return True
        except ScannerCacheException as exc:
            logger.warning("Redis invalidate error | keys=%s | err=%s", keys, exc)
            record_scanner_cache_error("delete")
            return False

    async def _try_acquire_distributed_lock(self, cache_key: str) -> bool:
        """Acquire Redis SET NX lock for multi-worker singleflight.

        Returns True if this worker should execute the DB refill.
        On Redis unavailable / error: fail-open (True) so local singleflight
        still serves traffic (availability over perfect cross-process dedupe).
        """
        client = get_redis_client()
        if client is None:
            return True
        lock_key = lock_key_for(cache_key)
        try:
            acquired = await self._redis_set(
                client, lock_key, "1", ex=_DISTRIBUTED_LOCK_TTL_SEC, nx=True
            )
            if acquired:
                logger.debug("Distributed lock acquired | lock=%s", lock_key)
            else:
                logger.debug("Distributed lock held by peer | lock=%s", lock_key)
            return acquired
        except ScannerCacheException as exc:
            logger.warning(
                "Distributed lock acquire failed (fail-open) | lock=%s | err=%s", lock_key, exc
            )
            record_scanner_cache_error("lock")
            return True

    async def _release_distributed_lock(self, cache_key: str) -> None:
        client = get_redis_client()
        if client is None:
            return
        lock_key = lock_key_for(cache_key)
        try:
            await self._redis_delete(client, lock_key)
            logger.debug("Distributed lock released | lock=%s", lock_key)
        except ScannerCacheException as exc:
            # TTL expiry is the safety net
            logger.warning("Distributed lock release failed | lock=%s | err=%s", lock_key, exc)
            record_scanner_cache_error("lock")

    async def _wait_for_cache_fill(
        self, key: str, *, max_wait_sec: float = _CACHE_WAIT_MAX_SEC
    ) -> Optional[str]:
        """Poll Redis until peer singleflight populates ``key`` or timeout."""
        deadline = time.monotonic() + max_wait_sec
        while time.monotonic() < deadline:
            lookup = await self.lookup_latest_scan(key)
            if lookup.payload is not None:
                return lookup.payload
            if lookup.status == "FALLBACK":
                return None
            await asyncio.sleep(_CACHE_WAIT_POLL_SEC)
        return None

    async def execute_singleflight(
        self,
        key: str,
        fetch_coro: ProduceJson,
        *,
        prior_status: str = "MISS",
    ) -> Tuple[str, str]:
        """Singleflight: only ONE concurrent request executes the DB producer.

        Uses in-process lock + Redis ``lock:{key}`` NX so multi-worker deployments
        share one PostgreSQL refill (audit M1 / SC-004).

        ``fetch_coro`` must return a pre-serialized JSON string and is responsible
        for writing the cache (or the caller may write after). Waiters re-check
        Redis and share the filled payload as HIT.

        ``prior_status`` preserves FALLBACK when the outer lookup failed on Redis.
        """
        status_on_miss = "FALLBACK" if prior_status == "FALLBACK" else "MISS"
        local_lock = await self._get_key_lock(key)
        async with local_lock:
            cached = await self.lookup_latest_scan(key)
            if cached.payload is not None:
                return cached.payload, "HIT"

            # When Redis itself is down, skip distributed lock dance — fetch once
            # under the in-process lock only.
            if prior_status == "FALLBACK":
                result_data = await fetch_coro()
                return result_data, "FALLBACK"

            acquired = await self._try_acquire_distributed_lock(key)
            if acquired:
                try:
                    # Peer may have filled between our miss and lock grant
                    cached = await self.lookup_latest_scan(key)
                    if cached.payload is not None:
                        return cached.payload, "HIT"
                    result_data = await fetch_coro()
                    return result_data, status_on_miss
                finally:
                    await self._release_distributed_lock(key)

            # Another worker holds the distributed lock — wait for cache fill
            filled = await self._wait_for_cache_fill(key)
            if filled is not None:
                return filled, "HIT"

            # Wait timed out: last-resort fetch (bounded residual stampede)
            logger.warning(
                "Singleflight wait timeout | key=%s | performing last-resort DB fetch",
                key,
            )
            result_data = await fetch_coro()
            return result_data, status_on_miss

    async def resolve_latest_scan(
        self,
        key: str,
        produce_json: ProduceJson,
        *,
        force: bool = False,
        cache_enabled: Optional[bool] = None,
    ) -> Tuple[str, str]:
        """High-level cache-aside resolver used by route handlers.

        Returns ``(payload_json, x_cache_status)`` where status is one of
        HIT | MISS | BYPASS | FALLBACK.
        """
        # Live flag evaluation (audit H5): re-read settings each resolve call.
        enabled = (
            settings.is_scanner_latest_cache_enabled()
            if cache_enabled is None
            else bool(cache_enabled)
        )

        if not enabled:
            return await produce_json(), "BYPASS"

        if force:
            # Force always bypasses cache read and reloads from DB under local lock.
            # (Distributed wait-on-stale would incorrectly return pre-force data.)
            local_lock = await self._get_key_lock(key)
            async with local_lock:
                return await produce_json(), "MISS"

        lookup = await self.lookup_latest_scan(key)
        if lookup.payload is not None:
            return lookup.payload, "HIT"

        prior = "FALLBACK" if lookup.status == "FALLBACK" else "MISS"
        return await self.execute_singleflight(key, produce_json, prior_status=prior)


scanner_cache_service = ScannerCacheService()
