"""Lightweight in-process RE-001 counters for ops (M6)."""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_counters: dict[str, int] = {
    "runs": 0,
    "success": 0,
    "timeout": 0,
    "error": 0,
    "buy": 0,
    "watch": 0,
    "reject": 0,
    "persist_ok": 0,
    "persist_fail": 0,
    "persist_idempotent": 0,
}


def incr(key: str, n: int = 1) -> None:
    with _lock:
        _counters[key] = int(_counters.get(key, 0)) + n


def snapshot() -> dict[str, Any]:
    with _lock:
        return dict(_counters)
