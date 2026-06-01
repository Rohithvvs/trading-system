from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from .session import AsyncSessionLocal


def advisory_lock_key(name: str) -> int:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@dataclass
class SingletonLease:
    name: str
    acquired: bool
    _session: AsyncSession | None = None

    async def release(self) -> None:
        if self._session is not None:
            if self.acquired:
                await self._session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": advisory_lock_key(self.name)})
            await self._session.close()
            self._session = None
        self.acquired = False


async def acquire_singleton_lease(name: str) -> SingletonLease:
    session = AsyncSessionLocal()
    # Ensure it's PostgreSQL
    if session.bind and session.bind.dialect.name != "postgresql":
        await session.close()
        return SingletonLease(name=name, acquired=True)
        
    try:
        acquired = bool(await session.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": advisory_lock_key(name)}))
        if not acquired:
            await session.close()
            return SingletonLease(name=name, acquired=False)
        return SingletonLease(name=name, acquired=True, _session=session)
    except Exception:
        await session.close()
        raise


@asynccontextmanager
async def transaction_advisory_lock(db: AsyncSession, name: str) -> AsyncIterator[bool]:
    if db.bind and db.bind.dialect.name == "postgresql":
        acquired = bool(await db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": advisory_lock_key(name)}))
        yield acquired
    else:
        yield True

