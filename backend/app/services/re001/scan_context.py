"""Scan-scoped context for RE-001 (stable scan_run_id, optional user)."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

_scan_run_id: ContextVar[str | None] = ContextVar("re001_scan_run_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("re001_user_id", default=None)


def new_scan_run_id(prefix: str = "scan") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{ts}-{uuid4().hex[:8]}"


def set_scan_run_id(scan_run_id: str | None) -> Any:
    return _scan_run_id.set(scan_run_id)


def get_scan_run_id() -> str | None:
    return _scan_run_id.get()


def reset_scan_run_id(token: Any) -> None:
    try:
        _scan_run_id.reset(token)
    except Exception:
        pass


def set_user_id(user_id: str | None) -> Any:
    return _user_id.set(user_id)


def get_user_id() -> str | None:
    return _user_id.get()


def reset_user_id(token: Any) -> None:
    try:
        _user_id.reset(token)
    except Exception:
        pass
