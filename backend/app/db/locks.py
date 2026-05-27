from __future__ import annotations

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from sqlalchemy import text

from .session import engine


def advisory_lock_key(name: str) -> int:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@dataclass
class SingletonLease:
    name: str
    acquired: bool
    _conn: object | None = None

    def release(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self.acquired = False


def acquire_singleton_lease(name: str) -> SingletonLease:
    if engine.dialect.name != "postgresql":
        return SingletonLease(name=name, acquired=True)
    conn = engine.connect()
    acquired = bool(conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": advisory_lock_key(name)}).scalar())
    if not acquired:
        conn.close()
        return SingletonLease(name=name, acquired=False)
    return SingletonLease(name=name, acquired=True, _conn=conn)


@contextmanager
def transaction_advisory_lock(db, name: str) -> Iterator[bool]:
    if db.bind and db.bind.dialect.name == "postgresql":
        acquired = bool(db.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": advisory_lock_key(name)}).scalar())
        yield acquired
    else:
        yield True

