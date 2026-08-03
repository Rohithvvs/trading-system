"""Concurrency safety for AsyncSession / asyncpg.

Guarantees scanner-style parallel workers never share one AsyncSession and
that concurrent upserts complete without ``another operation is in progress``.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pandas as pd
import pytest
from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.db.session import is_asyncpg_concurrency_error


Base = declarative_base()


class _CandleStub(Base):
    __tablename__ = "hist_candle_stub"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    resolution = Column(String(8), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    close = Column(Float, nullable=False)


@pytest.mark.asyncio
async def test_parallel_workers_use_distinct_sessions():
    """Each concurrent worker must use a distinct AsyncSession instance."""
    pytest.importorskip("aiosqlite")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    seen: list[int] = []
    lock = asyncio.Lock()

    async def worker(i: int):
        async with maker() as db:
            async with lock:
                seen.append(id(db))
            db.add(
                _CandleStub(
                    symbol=f"S{i}",
                    resolution="1D",
                    timestamp=datetime.now(timezone.utc),
                    close=float(i),
                )
            )
            await db.commit()

    await asyncio.gather(*(worker(i) for i in range(12)))
    assert len(seen) == 12
    assert len(set(seen)) == 12, "Workers shared AsyncSession instances"
    await engine.dispose()


@pytest.mark.asyncio
async def test_is_asyncpg_concurrency_error_detection():
    class Fake(Exception):
        pass

    assert is_asyncpg_concurrency_error(
        Fake("cannot switch to state 15; another operation (2) is in progress")
    )
    assert is_asyncpg_concurrency_error(
        Fake("cannot switch to state 12; another operation (2) is in progress")
    )
    assert not is_asyncpg_concurrency_error(Fake("relation does not exist"))


@pytest.mark.asyncio
async def test_upsert_candles_multi_parallel_own_sessions(monkeypatch):
    """MarketDataService.upsert_candles_multi must fan out per-symbol (own session path)."""
    from app.services.market_data_service import MarketDataService

    svc = MarketDataService()
    calls = {"n": 0}
    active = {"n": 0}
    max_active = {"n": 0}

    async def fake_upsert(symbol, timeframe, df):
        calls["n"] += 1
        active["n"] += 1
        max_active["n"] = max(max_active["n"], active["n"])
        await asyncio.sleep(0.02)
        active["n"] -= 1
        return None

    monkeypatch.setattr(svc, "upsert_candles", fake_upsert)

    frames = [
        (
            f"SYM{i}",
            "1D",
            pd.DataFrame(
                {
                    "open": [1.0],
                    "high": [1.0],
                    "low": [1.0],
                    "close": [1.0],
                    "volume": [100],
                },
                index=[datetime.now(timezone.utc)],
            ),
        )
        for i in range(16)
    ]
    written = await svc.upsert_candles_multi(frames)
    assert written == 16
    assert calls["n"] == 16
    # Concurrency capped at _UPSERT_MAX_CONCURRENCY (4)
    assert max_active["n"] <= 4
    assert max_active["n"] >= 2  # actually ran in parallel under load
