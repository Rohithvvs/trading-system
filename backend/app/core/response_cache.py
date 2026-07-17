"""
Lightweight in-process TTL cache for read-heavy, low-churn API responses.

Used for:
- Token status (DB-only, no FYERS call)
- Market status
- Health-ish probes

Does NOT cache user-specific trading state that mutates frequently.
Thread-safe for use from async and sync workers.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}

DEFAULT_TTL_SECONDS = 300.0  # 5 minutes
_SWEEP_INTERVAL = 60.0  # sweep every 60 seconds
_last_sweep: float = 0.0


def _evict_expired() -> None:
    """Periodic sweep to remove expired entries from the cache."""
    global _last_sweep
    now = time.monotonic()
    if now - _last_sweep < _SWEEP_INTERVAL:
        return
    _last_sweep = now
    expired = [k for k, v in _store.items() if now > v[0]]
    for k in expired:
        _store.pop(k, None)


def cache_get(key: str) -> Any | None:
    with _lock:
        item = _store.get(key)
        if not item:
            return None
        expires_at, value = item
        if time.monotonic() > expires_at:
            del _store[key]
            return None
        return value


def cache_set(key: str, value: Any, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
    with _lock:
        _store[key] = (time.monotonic() + ttl_seconds, value)
        _evict_expired()


def cache_invalidate(prefix: str | None = None) -> None:
    with _lock:
        if prefix is None:
            _store.clear()
            return
        for k in list(_store.keys()):
            if k.startswith(prefix):
                del _store[k]


def cached(key: str, producer: Callable[[], T], ttl_seconds: float = DEFAULT_TTL_SECONDS) -> T:
    hit = cache_get(key)
    if hit is not None:
        return hit  # type: ignore[return-value]
    value = producer()
    cache_set(key, value, ttl_seconds)
    return value


async def cached_async(key: str, producer, ttl_seconds: float = DEFAULT_TTL_SECONDS):
    hit = cache_get(key)
    if hit is not None:
        return hit
    value = await producer()
    cache_set(key, value, ttl_seconds)
    return value
