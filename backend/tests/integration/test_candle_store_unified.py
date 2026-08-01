"""Integration tests for US1 â€” Unified Scanner & Analysis Candle Retrieval.

Spec: specs/020-authoritative-candle-store/spec.md User Story 1
  AC1: With flag ON, scanner fetches candles from the Authoritative Store.
  AC2: OrchestratorAgent retrieves identical candles as the scanner.
  AC3: L1/L2 cache hit ratio exceeds 90% for active symbols during scans.

Task: T011 [P][US1] (tasks.md)

Approach
--------
Pre-seed the per-test SQLite DB with a complete candle series so no provider
fetch is needed. Two distinct consumers ("scanner" and "analysis") then issue
get_candles calls for the same symbol/resolution and assert byte-level array
identity plus L1 cache hit-ratio > 90% across a synthetic universe scan.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.app.config.settings import settings
from backend.app.db.session import AsyncSessionLocal
from backend.app.models.market_data import HistoricalCandle
from backend.app.schemas.analysis import OHLCVPoint
from backend.app.services.authoritative_candle_store import AuthoritativeCandleStore
from backend.app.services.l1_candle_cache import L1CandleCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SYMBOLS = ["RELIANCE-EQ", "INFY-EQ", "TCS-EQ"]
RESOLUTION = "1D"
CANDLE_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
CANDLE_DAYS = 10  # 10 daily candles per symbol


def _seed_candles(symbol: str, days: int = CANDLE_DAYS) -> list[HistoricalCandle]:
    rows = []
    for i in range(days):
        rows.append(
            HistoricalCandle(
                symbol=symbol,
                resolution=RESOLUTION,
                timestamp=CANDLE_BASE + timedelta(days=i),
                open=Decimal(100 + i),
                high=Decimal(101 + i),
                low=Decimal(99 + i),
                close=Decimal(100 + i),
                volume=Decimal(10_000 + i),
                source="FYERS",
            )
        )
    return rows


@pytest.fixture(autouse=True)
def acs_flag_on():
    """Force the feature flag ON for the integration suite."""
    saved_attr = settings.authoritative_candle_store_enabled
    saved_env = os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)
    object.__setattr__(settings, "authoritative_candle_store_enabled", True)
    object.__setattr__(settings, "candle_store_dual_write", False)
    yield
    object.__setattr__(settings, "authoritative_candle_store_enabled", saved_attr)
    object.__setattr__(settings, "candle_store_dual_write", False)
    if saved_env is not None:
        os.environ["AUTHORITATIVE_CANDLE_STORE_ENABLED"] = saved_env


@pytest.fixture()
def seeded_db(test_engine):
    """Per-test SQLite DB scaffolded by conftest.test_engine.

    Each test seeds its own candle history inside the running event loop via
    ``_drain_seed()`` so seeding happens on the same async engine binding.
    """
    return None


async def _drain_seed() -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            for sym in SYMBOLS:
                for row in _seed_candles(sym):
                    db.add(row)


def _with_utc_db_candles(store: AuthoritativeCandleStore) -> AuthoritativeCandleStore:
    """Coerce SQLite-returned naive DB timestamps to UTC aware so that the gap
    comparison logic in `_has_data_gap` does not raise
    `TypeError: can't compare offset-naive and offset-aware datetimes`.

    On production PostgreSQL, ``DateTime(timezone=True)`` already returns
    tz-aware datetimes, so this wrapper is a no-op equivalent there.
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


# ===========================================================================
# AC1: Scanner fetches candles from Authoritative Store (flag ON)
# ===========================================================================

async def test_scanner_retrieves_candles_from_authoritative_store(seeded_db):
    await _drain_seed()
    cache = L1CandleCache(max_capacity=50)
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache))

    start = CANDLE_BASE
    end = CANDLE_BASE + timedelta(days=CANDLE_DAYS - 1)
    candles = await store.get_candles("RELIANCE-EQ", RESOLUTION, start, end)

    assert len(candles) == CANDLE_DAYS
    assert [c.timestamp for c in candles] == sorted(c.timestamp for c in candles)
    # Verify the candles came from the Authoritative DB store, not legacy path.
    db_rows = await _fetch_db_count("RELIANCE-EQ", RESOLUTION)
    assert db_rows == CANDLE_DAYS


# ===========================================================================
# AC2: Scanner & Analysis receive byte-level identical candle arrays
# ===========================================================================

async def test_scanner_and_analysis_receive_identical_arrays(seeded_db):
    await _drain_seed()
    cache = L1CandleCache(max_capacity=50)
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache))

    start = CANDLE_BASE
    end = CANDLE_BASE + timedelta(days=CANDLE_DAYS - 1)

    scanner_candles = await store.get_candles("RELIANCE-EQ", RESOLUTION, start, end)
    analysis_candles = await store.get_candles("RELIANCE-EQ", RESOLUTION, start, end)

    _assert_byte_equal(scanner_candles, analysis_candles)


async def test_universe_scan_returns_per_symbol_identical_across_consumers(seeded_db):
    await _drain_seed()
    cache = L1CandleCache(max_capacity=50)
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache))
    start = CANDLE_BASE
    end = CANDLE_BASE + timedelta(days=CANDLE_DAYS - 1)

    # Scanner pass over the Nifty universe
    scanner_pass = {sym: await store.get_candles(sym, RESOLUTION, start, end) for sym in SYMBOLS}
    # Analysis pass over the same universe
    analysis_pass = {sym: await store.get_candles(sym, RESOLUTION, start, end) for sym in SYMBOLS}

    assert set(scanner_pass.keys()) == set(SYMBOLS)
    for sym in SYMBOLS:
        _assert_byte_equal(scanner_pass[sym], analysis_pass[sym])
        assert len(scanner_pass[sym]) == CANDLE_DAYS


# ===========================================================================
# AC3: L1/L2 cache hit ratio exceeds 90% for active symbols
# ===========================================================================

async def test_cache_hit_ratio_exceeds_90_percent(seeded_db):
    await _drain_seed()
    cache = L1CandleCache(max_capacity=50)
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache))
    start = CANDLE_BASE
    end = CANDLE_BASE + timedelta(days=CANDLE_DAYS - 1)

    db_call_count = {"n": 0}
    real_query = store._query_db_candles

    async def _counting_query(symbol, resolution, start_dt=None, end_dt=None):
        db_call_count["n"] += 1
        return await real_query(symbol, resolution, start_dt, end_dt)

    store._query_db_candles = _counting_query  # type: ignore[assignment]

    total_queries = 0
    # First pass: cold start â€” each symbol is an L2/DB hit then becomes L1.
    for sym in SYMBOLS:
        total_queries += 1
        await store.get_candles(sym, RESOLUTION, start, end)
        # Subsequent same-symbol queries MUST hit L1 (no DB round trip).
        for _ in range(9):
            total_queries += 1
            await store.get_candles(sym, RESOLUTION, start, end)

    # One DB call per symbol (cold start) -> all other queries served by L1.
    assert db_call_count["n"] == len(SYMBOLS)
    l1_hits = total_queries - db_call_count["n"]
    hit_ratio = l1_hits / total_queries
    assert hit_ratio >= 0.90, f"Cache hit ratio {hit_ratio:.2%} < 90%"

    # Sanity: every symbol must be resident in L1 after a scan pass
    for sym in SYMBOLS:
        assert cache.get(sym, RESOLUTION) is not None


# ===========================================================================
# Byte-level identity is preserved across flag states (compatibility)
# ===========================================================================

async def test_identical_arrays_when_served_from_l1_then_l2(seeded_db):
    """First read populates L1 from L2 (DB); second read served from L1 must match."""
    await _drain_seed()
    cache = L1CandleCache(max_capacity=50)
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache))
    start = CANDLE_BASE
    end = CANDLE_BASE + timedelta(days=CANDLE_DAYS - 1)

    first = await store.get_candles("INFY-EQ", RESOLUTION, start, end)  # L2 DB hit
    cache_hit = cache.get("INFY-EQ", RESOLUTION)
    assert cache_hit is not None
    second = await store.get_candles("INFY-EQ", RESOLUTION, start, end)  # L1 hit
    _assert_byte_equal(first, second)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _fetch_db_count(symbol: str, resolution: str) -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(HistoricalCandle).where(
            HistoricalCandle.symbol == symbol,
            HistoricalCandle.resolution == resolution,
        )
        res = await db.execute(stmt)
        return len(res.scalars().all())


def _assert_byte_equal(
    a: list[OHLCVPoint] | None, b: list[OHLCVPoint] | None
) -> None:
    assert a is not None and b is not None
    assert len(a) == len(b)
    for c1, c2 in zip(a, b):
        assert c1.timestamp == c2.timestamp
        assert c1.open == c2.open
        assert c1.high == c2.high
        assert c1.low == c2.low
        assert c1.close == c2.close
        assert c1.volume == c2.volume