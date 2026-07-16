"""Request and error rate monitor for diagnostics dashboard.

Tracks request counts and error counts in a sliding 60-second window
to provide real-time request_rate_per_sec and error_rate_per_sec metrics
for the diagnostics dashboard (FR-005).
"""
from __future__ import annotations

import time
from collections import deque

_requests: deque[float] = deque()
_errors: deque[float] = deque()
_WINDOW_SECONDS = 60.0


def record_request() -> None:
    _requests.append(time.monotonic())


def record_error() -> None:
    _errors.append(time.monotonic())


def _prune(dq: deque[float], now: float) -> None:
    cutoff = now - _WINDOW_SECONDS
    while dq and dq[0] < cutoff:
        dq.popleft()


def get_request_rate_per_sec() -> float:
    now = time.monotonic()
    _prune(_requests, now)
    if len(_requests) == 0:
        return 0.0
    elapsed = min(now - _requests[0], _WINDOW_SECONDS)
    if elapsed <= 0:
        return float(len(_requests))
    return len(_requests) / elapsed


def get_error_rate_per_sec() -> float:
    now = time.monotonic()
    _prune(_errors, now)
    if len(_errors) == 0:
        return 0.0
    elapsed = min(now - _errors[0], _WINDOW_SECONDS)
    if elapsed <= 0:
        return float(len(_errors))
    return len(_errors) / elapsed