"""
Scanner Cache Service — Redis-based caching for scanner results, OHLCV, and indicators.

Key design:
- Scanner results cached with 5-min TTL (invalidated sooner if market data changes)
- OHLCV data cached with 30-min TTL for daily data
- Automatic prefix-based invalidation when market session ends
- LRU-aware via Redis approximate LRU eviction
"""
from __future__ import annotations

import json
import time
import hashlib
import logging
from typing import Any
from datetime import datetime, timezone

logger = logging.getLogger("app.services.scanner_cache")


def _get_redis_client():
    """Resolve live Redis client (recreates after lifecycle close)."""
    try:
        from ..core.redis import get_redis_client

        return get_redis_client()
    except Exception:
        return None


CACHE_PREFIX = "scanner:"
OHLCV_PREFIX = "ohlcv:"
INDICATOR_PREFIX = "indicator:"
TREND_PREFIX = "trend:"

# TTLs in seconds
SCANNER_RESULT_TTL = 300  # 5 minutes
OHLCV_CACHE_TTL = 1800  # 30 minutes
INDICATOR_CACHE_TTL = 1800  # 30 minutes
TREND_CACHE_TTL = 600  # 10 minutes


def _cache_key(prefix: str, *parts: str) -> str:
    key = f"{CACHE_PREFIX}{prefix}{':'.join(parts)}"
    # Keep keys readable but bounded
    if len(key) > 200:
        key = f"{CACHE_PREFIX}{prefix}{hashlib.md5(key.encode()).hexdigest()}"
    return key


async def cache_scanner_result(
    universe: str,
    mode: str,
    timeframe: str,
    result: dict[str, Any],
    ttl: int = SCANNER_RESULT_TTL,
) -> None:
    client = _get_redis_client()
    if client is None:
        return
    try:
        key = _cache_key("result:", universe, mode, timeframe)
        await client.setex(key, ttl, json.dumps(result, default=str))
        logger.debug("Cached scanner result | key=%s | ttl=%s", key, ttl)
    except Exception as e:
        logger.warning("Failed to cache scanner result | error=%s", e)


async def get_cached_scanner_result(
    universe: str,
    mode: str,
    timeframe: str,
) -> dict[str, Any] | None:
    client = _get_redis_client()
    if client is None:
        return None
    try:
        key = _cache_key("result:", universe, mode, timeframe)
        data = await client.get(key)
        if data:
            logger.debug("Scanner result cache HIT | key=%s", key)
            return json.loads(data)
        logger.debug("Scanner result cache MISS | key=%s", key)
        return None
    except Exception as e:
        logger.warning("Failed to get cached scanner result | error=%s", e)
        return None


async def invalidate_scanner_cache(universe: str | None = None, mode: str | None = None) -> None:
    client = _get_redis_client()
    if client is None:
        return
    try:
        pattern = f"{CACHE_PREFIX}result:*"
        if universe:
            pattern = f"{CACHE_PREFIX}result:{universe}*"
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor, match=pattern, count=100)
            if keys:
                await client.delete(*keys)
            if cursor == 0:
                break
        logger.info("Invalidated scanner cache | pattern=%s", pattern)
    except Exception as e:
        logger.warning("Failed to invalidate scanner cache | error=%s", e)


async def clear_scanner_cache() -> None:
    client = _get_redis_client()
    if client is None:
        return
    try:
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor, match=f"{CACHE_PREFIX}*", count=100)
            if keys:
                await client.delete(*keys)
            if cursor == 0:
                break
        logger.info("Cleared all scanner cache")
    except Exception as e:
        logger.warning("Failed to clear scanner cache | error=%s", e)


async def cache_exists(universe: str, mode: str, timeframe: str) -> bool:
    client = _get_redis_client()
    if client is None:
        return False
    try:
        key = _cache_key("result:", universe, mode, timeframe)
        exists = await client.exists(key)
        return bool(exists)
    except Exception as e:
        logger.warning("Failed to check cache existence | error=%s", e)
        return False


async def cache_ohlcv(
    symbol: str,
    resolution: str,
    data: list[dict[str, Any]],
    ttl: int = OHLCV_CACHE_TTL,
) -> None:
    client = _get_redis_client()
    if client is None:
        return
    try:
        key = _cache_key(OHLCV_PREFIX, symbol, resolution)
        await client.setex(key, ttl, json.dumps(data, default=str))
    except Exception as e:
        logger.debug("Failed to cache OHLCV | symbol=%s | error=%s", symbol, e)


async def get_cached_ohlcv(
    symbol: str,
    resolution: str,
) -> list[dict[str, Any]] | None:
    client = _get_redis_client()
    if client is None:
        return None
    try:
        key = _cache_key(OHLCV_PREFIX, symbol, resolution)
        data = await client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.debug("Failed to get cached OHLCV | symbol=%s | error=%s", symbol, e)
        return None


async def cache_indicators(
    symbol: str,
    resolution: str,
    indicators: dict[str, Any],
    ttl: int = INDICATOR_CACHE_TTL,
) -> None:
    client = _get_redis_client()
    if client is None:
        return
    try:
        key = _cache_key(INDICATOR_PREFIX, symbol, resolution)
        await client.setex(key, ttl, json.dumps(indicators, default=str))
    except Exception as e:
        logger.debug("Failed to cache indicators | symbol=%s | error=%s", symbol, e)


async def get_cached_indicators(
    symbol: str,
    resolution: str,
) -> dict[str, Any] | None:
    client = _get_redis_client()
    if client is None:
        return None
    try:
        key = _cache_key(INDICATOR_PREFIX, symbol, resolution)
        data = await client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.debug("Failed to get cached indicators | symbol=%s | error=%s", symbol, e)
        return None


async def cache_trend(
    symbol: str,
    trend_data: dict[str, Any],
    ttl: int = TREND_CACHE_TTL,
) -> None:
    client = _get_redis_client()
    if client is None:
        return
    try:
        key = _cache_key(TREND_PREFIX, symbol)
        await client.setex(key, ttl, json.dumps(trend_data, default=str))
    except Exception as e:
        logger.debug("Failed to cache trend | symbol=%s | error=%s", symbol, e)


async def get_cached_trend(symbol: str) -> dict[str, Any] | None:
    client = _get_redis_client()
    if client is None:
        return None
    try:
        key = _cache_key(TREND_PREFIX, symbol)
        data = await client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.debug("Failed to get cached trend | symbol=%s | error=%s", symbol, e)
        return None


async def invalidate_symbol(symbol: str) -> None:
    client = _get_redis_client()
    if client is None:
        return
    try:
        await client.delete(
            _cache_key(OHLCV_PREFIX, symbol, "1D"),
            _cache_key(INDICATOR_PREFIX, symbol, "1D"),
            _cache_key(TREND_PREFIX, symbol),
        )
        logger.debug("Invalidated cache for symbol=%s", symbol)
    except Exception as e:
        logger.debug("Failed to invalidate symbol cache | symbol=%s | error=%s", symbol, e)
