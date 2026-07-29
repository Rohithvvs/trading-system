"""Integration tests for US3 â€” Automatic Gap Filling & Backfill.

Spec: specs/020-authoritative-candle-store/spec.md User Story 3
  AC1: Symbol has candles in DB through 2026-06-01; user queries 2026-01-01 to
       2026-07-27. Authoritative Store detects missing tail range, fetches it
       from FYERS, persists to DB, and returns the unified continuous series.

Task: T020 [P][US3] (tasks.md)

The FYERS provider edge is stubbed via a FakeFyersService whose `fetch_ohlcv`
returns the missing day range, simulating a real provider fetch without an
external network dependency. The DB-backed ON CONFLICT DO UPDATE upsert path
runs against the per-test SQLite instance (SQLite supports the
`ON CONFLICT (...) DO UPDATE SET ...` dialect since 3.24).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

from backend.app.config.settings import settings
from backend.app.db.session import AsyncSessionLocal
from backend.app.models.market_data import HistoricalCandle
from backend.app.schemas.analysis import OHLCVPoint
from backend.app.services.authoritative_candle_store import AuthoritativeCandleStore
from backend.app.services.l1_candle_cache import L1CandleCache


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SYMBOL = "RELIANCE-EQ"
RESOLUTION = "1D"
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
# Per spec AC1: existing DB coverage up to 2026-06-01.
DB_LAST = datetime(2026, 6, 1, tzinfo=timezone.utc)
# Per spec AC1: requested range end 2026-07-27 (inclusive).
END = datetime(2026, 7, 27, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

def _candle(ts: datetime, i: int) -> OHLCVPoint:
    return OHLCVPoint(
        timestamp=ts,
        open=Decimal(100 + i),
        high=Decimal(101 + i),
        low=Decimal(99 + i),
        close=Decimal(100 + i),
        volume=Decimal(10_000 + i),
    )


class FakeFyersService:
    """Provider fetch stub. Returns OHLCVPoints spanning the full requested
    window START..END (mirrors a real provider returning its full lookback).
    The Authoritative Store deduplicates against existing DB candles via
    validate_candle_series, then upserts only the missing rows idempotently.
    """

    def __init__(self) -> None:
        self.fetch_calls = 0

    async def fetch_ohlcv(self, *args: Any, **kwargs: Any) -> list[OHLCVPoint]:
        self.fetch_calls += 1
        out: list[OHLCVPoint] = []
        i = 0
        cur = START
        while cur <= END:
            out.append(_candle(cur, i))
            cur += timedelta(days=1)
            i += 1
        return out


@pytest.fixture(autouse=True)
def acs_enabled():
    saved_attr = settings.authoritative_candle_store_enabled
    saved_env = os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)
    saved_dual = settings.candle_store_dual_write
    object.__setattr__(settings, "authoritative_candle_store_enabled", True)
    object.__setattr__(settings, "candle_store_dual_write", False)
    yield
    object.__setattr__(settings, "authoritative_candle_store_enabled", saved_attr)
    object.__setattr__(settings, "candle_store_dual_write", saved_dual)
    if saved_env is not None:
        os.environ["AUTHORITATIVE_CANDLE_STORE_ENABLED"] = saved_env


@pytest.fixture()
def fake_fyers() -> FakeFyersService:
    return FakeFyersService()


async def _drain_pending() -> None:
    """Allow fire-and-forget ingest tasks scheduled by the store to complete.

    The implementation dispatches the L3 gap-fill ingestion via
    ``asyncio.create_task(...)`` (non-blocking). Before DB assertions, we
    gather any pending tasks so the upsert has actually flushed into SQLite.
    """
    pending = asyncio.all_tasks() - {asyncio.current_task()}
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _with_utc_db_candles(store: AuthoritativeCandleStore) -> AuthoritativeCandleStore:
    """Coerce SQLite-returned naive DB timestamps to UTC aware so that the
    production gap-comparison path runs without ``TypeError`` in the test
    harness. Postgres returns tz-aware stamps in production, so this wrapper
    is inert there.
    """
    real_query = store._query_db_candles

    async def _utc_query(symbol, resolution, start_dt=None, end_dt=None):
        out = await real_query(symbol, resolution, start_dt, end_dt)
        return [
            c.model_copy(update={"timestamp": c.timestamp.replace(tzinfo=timezone.utc)})
            if c.timestamp.tzinfo is None
            else c
            for c in out
        ]

    store._query_db_candles = _utc_query  # type: ignore[assignment]
    return store


async def _drain_seed_db() -> None:
    """Seed DB with candles from START through DB_LAST inclusive."""
    async with AsyncSessionLocal() as db:
        async with db.begin():
            cursor = START
            i = 0
            while cursor <= DB_LAST:
                db.add(
                    HistoricalCandle(
                        symbol=SYMBOL,
                        resolution=RESOLUTION,
                        timestamp=cursor,
                        open=Decimal(100 + i),
                        high=Decimal(101 + i),
                        low=Decimal(99 + i),
                        close=Decimal(100 + i),
                        volume=Decimal(10_000 + i),
                        source="FYERS",
                    )
                )
                cursor += timedelta(days=1)
                i += 1


async def _db_count(symbol: str, resolution: str) -> int:
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(HistoricalCandle).where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.resolution == resolution,
            )
        )
        return len(res.scalars().all())


def _dt_of(ts: datetime | None) -> datetime.date:
    """Normalize a possibly-naive DB datetime to its UTC date for comparison."""
    from datetime import date
    if ts is None:
        return date.min
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.date()


async def _db_min_ts(symbol: str, resolution: str) -> datetime | None:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(HistoricalCandle.timestamp)
            .where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.resolution == resolution,
            )
            .order_by(HistoricalCandle.timestamp.asc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()


async def _db_max_ts(symbol: str, resolution: str) -> datetime | None:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(HistoricalCandle.timestamp)
            .where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.resolution == resolution,
            )
            .order_by(HistoricalCandle.timestamp.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()


# ===========================================================================
# AC1: Gap detection triggers provider tail-fetch, persist, unified return
# ===========================================================================

async def test_tail_gap_fill_persists_and_returns_continuous_series(
    test_engine, fake_fyers
):
    """US3 AC1: missing tail fetched from FYERS, persisted, returned unified.

    Initial DB coverage: START..DB_LAST.
    Requested range: START..END.
    Expected outcome: candles returned cover START..END with no gaps.
    """
    await _drain_seed_db()
    initial_count = await _db_count(SYMBOL, RESOLUTION)
    assert initial_count > 0
    initial_max = await _db_max_ts(SYMBOL, RESOLUTION)
    # SQLite stores datetimes naive; coerce comparison to a date for tz robustness.
    assert _dt_of(initial_max) == DB_LAST.date()

    cache = L1CandleCache(max_capacity=10)
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache, fyers_service=fake_fyers))

    merged = await store.get_candles(SYMBOL, RESOLUTION, START, END)
    # Drain the fire-and-forget ingest task so DB assertions see the new rows.
    await _drain_pending()

    # Provider must have been called exactly once to fill the tail gap.
    assert fake_fyers.fetch_calls == 1

    # Output must cover the full requested range continuously.
    assert merged[0].timestamp <= START
    assert merged[-1].timestamp >= END
    # Continuous daily cadence enforced through the merged series.
    gaps = []
    for prev, cur in zip(merged, merged[1:]):
        delta = cur.timestamp - prev.timestamp
        if delta != timedelta(days=1):
            gaps.append((prev.timestamp, cur.timestamp, delta))
    assert gaps == [], f"Found date gaps in merged series: {gaps[:5]}"
    assert merged[-1].timestamp == END

    # DB now spans END (the missing tail persisted) with row growth.
    after_count = await _db_count(SYMBOL, RESOLUTION)
    assert after_count > initial_count
    assert _dt_of(await _db_max_ts(SYMBOL, RESOLUTION)) == END.date()


async def test_tail_gapFill_idempotent_on_repeat_query(
    test_engine, fake_fyers
):
    """Repeating the same range query must NOT trigger a second provider fetch.

    After the first query populates both L2 DB and L1 cache, the second query
    is a pure L1 hit â€” no provider round trip and no extra DB writes.
    """
    await _drain_seed_db()
    cache = L1CandleCache(max_capacity=10)
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache, fyers_service=fake_fyers))

    first = await store.get_candles(SYMBOL, RESOLUTION, START, END)
    await _drain_pending()
    assert fake_fyers.fetch_calls == 1

    # Second identical query MUST be served from L1 (or DB) â€” no provider call.
    second = await store.get_candles(SYMBOL, RESOLUTION, START, END)
    await _drain_pending()

    assert fake_fyers.fetch_calls == 1, "Repeat query triggered a second provider fetch"
    assert [c.timestamp for c in first] == [c.timestamp for c in second]
    # L1 cache populated
    assert cache.get(SYMBOL, RESOLUTION) is not None


# ===========================================================================
# FR-007: Head gap fetch (start earlier than DB start)
# ===========================================================================

async def test_head_gap_fill_when_request_precedes_db_start(
    test_engine, fake_fyers
):
    """FR-007: missing head range [start, db_start] fetched from provider."""
    await _drain_seed_db()
    # Request earlier than DB start.
    earlier_start = START - timedelta(days=10)

    # Provider returns the pre-START window.
    head_provider = [_candle(START - timedelta(days=d), d) for d in range(10, 0, -1)]

    async def fetch_ohlcv(*a, **kw):
        fake_fyers.fetch_calls += 1
        return head_provider

    fake_fyers.fetch_ohlcv = fetch_ohlcv  # type: ignore[assignment]

    cache = L1CandleCache(max_capacity=10)
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache, fyers_service=fake_fyers))

    merged = await store.get_candles(SYMBOL, RESOLUTION, earlier_start, DB_LAST)
    await _drain_pending()

    assert fake_fyers.fetch_calls == 1
    # Merged series must include dates from earlier_start through DB_LAST
    assert merged[0].timestamp == earlier_start
    assert merged[-1].timestamp == DB_LAST


# ===========================================================================
# FR-003 / FR-007: Idempotent upsert (ON CONFLICT DO UPDATE)
# ===========================================================================

async def test_ingest_candles_persists_idempotently(test_engine):
    """Idempotent upsert: ingesting twice produces the same DB row count.

    Verifies `ON CONFLICT (symbol, resolution, timestamp) DO UPDATE` does not
    create duplicates when the same candle window is provided twice.
    """
    await _drain_seed_db()
    base_count = await _db_count(SYMBOL, RESOLUTION)

    cache = L1CandleCache(max_capacity=10)
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache))

    candles_to_ingest = [_candle(START + timedelta(days=i), i) for i in range(20)]

    first = await store.ingest_candles(SYMBOL, RESOLUTION, candles_to_ingest, source="FYERS")
    after_first = await _db_count(SYMBOL, RESOLUTION)
    assert after_first >= base_count  # No rows lost; some upserted.

    second = await store.ingest_candles(SYMBOL, RESOLUTION, candles_to_ingest, source="FYERS")
    after_second = await _db_count(SYMBOL, RESOLUTION)

    # Idempotency: re-ingesting identical candles must not inflate row count.
    assert after_second == after_first, (
        f"Idempotency violated: {after_first} -> {after_second} rows after re-ingest"
    )
    # Inserted_count must be non-zero only on first flush (or zero on re-run).
    assert second.inserted_count + second.updated_count == 20


# ===========================================================================
# FR-007: Empty DB falls back entirely to provider for full backfill
# ===========================================================================

async def test_empty_db_full_backfill(test_engine, fake_fyers):
    """Empty DB + provider full coverage must still yield a continuous series."""
    # Verify clean DB state
    assert await _db_count(SYMBOL, RESOLUTION) == 0

    cache = L1CandleCache(max_capacity=10)
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache, fyers_service=fake_fyers))

    out = await store.get_candles(SYMBOL, RESOLUTION, START, END)
    await _drain_pending()

    assert len(out) > 0
    assert out[0].timestamp >= START
    assert out[-1].timestamp <= END
    # Provider fetched at least once to fill the empty DB.
    assert fake_fyers.fetch_calls >= 1
    # DB now populated by the fire-and-forget ingest.
    assert await _db_count(SYMBOL, RESOLUTION) > 0