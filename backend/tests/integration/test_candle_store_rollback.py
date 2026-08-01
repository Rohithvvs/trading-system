"""Integration tests for US2 â€” Instant Operational Rollback Capability.

Spec: specs/020-authoritative-candle-store/spec.md User Story 2
  AC1: Setting AUTHORITATIVE_CANDLE_STORE_ENABLED=false instantly routes all
       candle reads/writes to legacy paths.
  AC2: API requests under flag=false succeed without raising exceptions or
       requiring server restarts.

Task: T015 [P][US2] (tasks.md)

Approach
--------
A FakeMarketDataService is injected so the legacy _legacy_get_candles path
returns deterministic candles without a real FYERS dependency, mirroring
legacy contract behaviour. The flag is toggled at runtime between calls â€” no
re-deploy, no service restart â€” and we assert each call succeeds and is
served by the expected path.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from backend.app.config.settings import settings
from backend.app.db.session import AsyncSessionLocal
from backend.app.models.market_data import HistoricalCandle
from backend.app.schemas.analysis import OHLCVPoint
from backend.app.services.authoritative_candle_store import AuthoritativeCandleStore
from backend.app.services.l1_candle_cache import L1CandleCache


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

SYMBOL = "RELIANCE-EQ"
RESOLUTION = "1D"
CANDLE_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
CANDLE_DAYS = 5

LEGACY_CANDLES: list[OHLCVPoint] = [
    OHLCVPoint(
        timestamp=CANDLE_BASE + timedelta(days=i),
        open=200 + i, high=201 + i, low=199 + i, close=200 + i, volume=2_000 + i,
    )
    for i in range(CANDLE_DAYS)
]


class FakeMarketDataService:
    """Stand-in for MarketDataService that returns deterministic legacy candles.

    Mirrors the legacy contract that AuthoritativeCandleStore._legacy_get_candles
    delegates to: ``await market_data_service.get_candles(symbol=, timeframe=)``.
    """

    def __init__(self, candles: list[OHLCVPoint] | None = None) -> None:
        self.candles = candles if candles is not None else LEGACY_CANDLES
        self.calls: list[tuple[str, str]] = []

    async def get_candles(self, symbol: str = "", timeframe: str = "", **_: Any) -> list[OHLCVPoint]:
        self.calls.append((symbol, timeframe))
        return self.candles


@pytest.fixture(autouse=True)
def flag_snapshot():
    saved_attr = settings.authoritative_candle_store_enabled
    saved_env = os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)
    saved_dual = settings.candle_store_dual_write
    object.__setattr__(settings, "authoritative_candle_store_enabled", False)
    object.__setattr__(settings, "candle_store_dual_write", False)
    yield
    object.__setattr__(settings, "authoritative_candle_store_enabled", saved_attr)
    object.__setattr__(settings, "candle_store_dual_write", saved_dual)
    if saved_env is not None:
        os.environ["AUTHORITATIVE_CANDLE_STORE_ENABLED"] = saved_env
    else:
        os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)


async def _drain_seed() -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            for i in range(CANDLE_DAYS):
                db.add(
                    HistoricalCandle(
                        symbol=SYMBOL,
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


def _with_utc_db_candles(store: AuthoritativeCandleStore) -> AuthoritativeCandleStore:
    """SQLite returns naive datetimes; coerce DB-loaded candle timestamps to
    UTC so the production gap-comparison path runs without TypeError in the
    test harness (PostgreSQL returns tz-aware stamps in production so this
    wrapper is inert there).
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


def _set_env_flag(value: bool) -> None:
    """Toggle flag at runtime via environment variable (no restart)."""
    os.environ["AUTHORITATIVE_CANDLE_STORE_ENABLED"] = "true" if value else "false"


def _set_attr_flag(value: bool) -> None:
    object.__setattr__(settings, "authoritative_candle_store_enabled", value)


# ===========================================================================
# AC1: Setting flag=false instantly reverts to legacy path
# ===========================================================================

async def test_authoritative_then_legacy_then_authoritative(test_engine):
    """US2 AC1: toggling flag=false instantly routes reads to legacy path."""
    await _drain_seed()
    cache = L1CandleCache(max_capacity=10)
    legacy = FakeMarketDataService()
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache, market_data_service=legacy))

    start = CANDLE_BASE
    end = CANDLE_BASE + timedelta(days=CANDLE_DAYS - 1)

    # 1. Flag ON -> authoritative serves from DB / L1
    _set_attr_flag(True)
    os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)
    authoritative_candles = await store.get_candles(SYMBOL, RESOLUTION, start, end)
    assert len(authoritative_candles) == CANDLE_DAYS
    assert legacy.calls == []  # legacy path NOT used

    # 2. Instant rollback via flag flip â€” no restart, no exceptions
    _set_env_flag(False)
    legacy_candles = await store.get_candles(SYMBOL, RESOLUTION)
    assert len(legacy_candles) == CANDLE_DAYS
    assert legacy.calls == [(SYMBOL, RESOLUTION)]  # legacy path USED

    # 3. Recovery â€” toggle flag back ON; legacy no longer called.
    _set_env_flag(True)
    authoritative_again = await store.get_candles(SYMBOL, RESOLUTION, start, end)
    assert len(authoritative_again) == CANDLE_DAYS
    assert legacy.calls == [(SYMBOL, RESOLUTION)]  # still just the single legacy call


# ===========================================================================
# AC2: API requests succeed without exceptions across flag transitions
# ===========================================================================

async def test_requests_succeed_across_toggle_cycles(test_engine):
    """US2 AC2: calls succeed without exceptions through True/False cycles."""
    await _drain_seed()
    cache = L1CandleCache(max_capacity=10)
    legacy = FakeMarketDataService()
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache, market_data_service=legacy))
    start = CANDLE_BASE
    end = CANDLE_BASE + timedelta(days=CANDLE_DAYS - 1)

    # Cycle the flag several times. All calls must complete without raising.
    no_exceptions = True
    for state in [True, False, True, False, True, False, True]:
        _set_env_flag(state)
        if state:
            candles = await store.get_candles(SYMBOL, RESOLUTION, start, end)
        else:
            candles = await store.get_candles(SYMBOL, RESOLUTION)
        if candles is None or len(candles) == 0:
            no_exceptions = False
            break

    assert no_exceptions
    # Legacy path was exercised at least once during the off cycles.
    assert any(call == (SYMBOL, RESOLUTION) for call in legacy.calls)


async def test_legacy_path_does_not_touch_authoritative_db(test_engine):
    """Legacy fallback must NOT invoke Authoritative DB queries."""
    await _drain_seed()
    cache = L1CandleCache(max_capacity=10)
    legacy = FakeMarketDataService()
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache, market_data_service=legacy))

    db_call_count = {"n": 0}
    real_query = store._query_db_candles

    async def _counting_query(symbol, resolution, start_dt=None, end_dt=None):
        db_call_count["n"] += 1
        return await real_query(symbol, resolution, start_dt, end_dt)

    store._query_db_candles = _counting_query  # type: ignore[assignment]

    _set_env_flag(False)
    out = await store.get_candles(SYMBOL, RESOLUTION)
    assert out == LEGACY_CANDLES
    # Legacy path must not have hit the Authoritative DB query path.
    assert db_call_count["n"] == 0


async def test_env_false_overrides_attribute_true(test_engine):
    """Env var takes priority over attribute â€” instant rollback works even if
    attribute was left True from a prior canary."""
    await _drain_seed()
    cache = L1CandleCache(max_capacity=10)
    legacy = FakeMarketDataService()
    store = _with_utc_db_candles(AuthoritativeCandleStore(cache=cache, market_data_service=legacy))

    _set_attr_flag(True)  # canary phase left attribute True
    _set_env_flag(False)  # operator rolls back via env var
    out = await store.get_candles(SYMBOL, RESOLUTION)
    assert out == LEGACY_CANDLES
    assert legacy.calls == [(SYMBOL, RESOLUTION)]