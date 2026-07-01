from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

T = TypeVar("T")


def retry_on_db_error(fn: Callable[[], T], db, retries: int = 1) -> T:
    attempts = retries + 1
    for attempt in range(attempts):
        try:
            return fn()
        except OperationalError:
            try:
                db.rollback()
            except Exception:
                pass
            if attempt >= retries:
                raise HTTPException(
                    status_code=503,
                    detail="Database temporarily unavailable, retry",
                )
    raise HTTPException(status_code=503, detail="Database temporarily unavailable, retry")
