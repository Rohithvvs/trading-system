"""L1 In-Memory LRU Cache for Authoritative Candle Store (Sprint 4).

Provides fast (< 2ms) bounded in-memory caching for active symbol OHLCV series.
Thread-safe LRU eviction with max capacity limit (default 2000 keys) and TTL.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
import logging

from ..schemas.analysis import OHLCVPoint
from .candle_validation_engine import normalize_resolution

logger = logging.getLogger(__name__)

# Default TTL matches Fyers OHLCV memory cache window (audit M3).
_DEFAULT_TTL_SECONDS = 300.0


@dataclass
class L1CacheEntry:
    symbol: str
    resolution: str
    candles: list[OHLCVPoint]
    stored_at: float
    last_accessed: float
    ttl_seconds: float


class L1CandleCache:
    """Thread-safe bounded LRU + TTL cache for candle series."""

    def __init__(
        self,
        max_capacity: int = 2000,
        default_ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self.max_capacity = max_capacity
        self.default_ttl_seconds = max(0.0, float(default_ttl_seconds))
        self._cache: OrderedDict[str, L1CacheEntry] = OrderedDict()
        self._lock = Lock()

    def _make_key(self, symbol: str, resolution: str) -> str:
        norm_res = normalize_resolution(resolution)
        return f"candle_l1:{symbol.strip().upper()}:{norm_res}"

    def _is_expired(self, entry: L1CacheEntry, now: float | None = None) -> bool:
        if entry.ttl_seconds <= 0:
            return False
        now = time.time() if now is None else now
        return (now - entry.stored_at) > entry.ttl_seconds

    def get(
        self,
        symbol: str,
        resolution: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[OHLCVPoint] | None:
        """Get candle series from cache if present, not expired, and covers the window."""
        key = self._make_key(symbol, resolution)
        with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]
            now = time.time()
            if self._is_expired(entry, now):
                self._cache.pop(key, None)
                logger.debug("L1 Candle Cache TTL expired: %s", key)
                return None

            # Move key to end (mark recently used)
            self._cache.pop(key)
            entry.last_accessed = now
            self._cache[key] = entry

            cached_candles = entry.candles
            if not cached_candles:
                return None

            if start_date:
                if start_date.tzinfo is None:
                    from datetime import timezone

                    start_date = start_date.replace(tzinfo=timezone.utc)
                if cached_candles[0].timestamp > start_date:
                    return None

            if end_date:
                if end_date.tzinfo is None:
                    from datetime import timezone

                    end_date = end_date.replace(tzinfo=timezone.utc)
                if cached_candles[-1].timestamp < end_date:
                    return None

            return list(cached_candles)

    def set(
        self,
        symbol: str,
        resolution: str,
        candles: list[OHLCVPoint],
        ttl_seconds: float | None = None,
    ) -> None:
        """Set or update candle series in L1 cache with LRU eviction and TTL."""
        if not candles:
            return

        key = self._make_key(symbol, resolution)
        now = time.time()
        ttl = self.default_ttl_seconds if ttl_seconds is None else max(0.0, float(ttl_seconds))

        entry = L1CacheEntry(
            symbol=symbol.strip().upper(),
            resolution=normalize_resolution(resolution),
            candles=list(candles),
            stored_at=now,
            last_accessed=now,
            ttl_seconds=ttl,
        )

        with self._lock:
            if key in self._cache:
                self._cache.pop(key)
            elif len(self._cache) >= self.max_capacity:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug("L1 Candle Cache evicted LRU entry: %s", evicted_key)

            self._cache[key] = entry

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Return current number of cached symbol-resolution series."""
        with self._lock:
            return len(self._cache)


# Global singleton instance for app runtime
l1_candle_cache = L1CandleCache()
