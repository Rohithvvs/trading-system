"""In-process cache for AI research responses and computed research payloads.

Keyed by symbol + market data fingerprint so results refresh only when candles change.
Thread-safe for concurrent detail requests. Does not touch paper trading or broker APIs.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any


class ResearchCache:
    def __init__(self, ttl_seconds: int = 900, max_entries: int = 256) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, Any]] = {}

    def _evict_if_needed(self) -> None:
        if len(self._store) <= self._max:
            return
        # Drop oldest by timestamp
        ordered = sorted(self._store.items(), key=lambda kv: kv[1][0])
        for key, _ in ordered[: max(1, len(self._store) - self._max)]:
            self._store.pop(key, None)

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            ts, value = item
            if time.time() - ts > self._ttl:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.time(), value)
            self._evict_if_needed()

    @staticmethod
    def fingerprint(symbol: str, last_ts: str | None, candle_count: int, close: float | None) -> str:
        raw = f"{symbol}|{last_ts}|{candle_count}|{close}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def llm_key(symbol: str, purpose: str, context: dict[str, Any]) -> str:
        payload = json.dumps(context, sort_keys=True, default=str)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return f"llm:{symbol}:{purpose}:{digest}"


# Shared singleton for research module
research_cache = ResearchCache()
