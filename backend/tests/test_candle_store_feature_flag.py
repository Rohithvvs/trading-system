"""Unit tests for Authoritative Candle Store feature flag toggle routing.

Spec: specs/020-authoritative-candle-store/spec.md
  FR-005 Read Preference & Fallback
  FR-009 Instant Rollback Behavior
Spec section 8 (Feature Flag Strategy) state matrix:
  | flag value | read target          | write target        |
  | false (OFF)| Legacy / Direct FYERS| Legacy stores        |
  | true  (ON) | Authoritative Store  | Authoritative + dual |

Task: T012 [P][US2] (tasks.md)

These tests verify that runtime toggling of AUTHORITATIVE_CANDLE_STORE_ENABLED
immediately routes subsequent reads to the authoritative path or legacy path
through dynamic flag evaluation, with NO service restart.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from backend.app.config.settings import settings
from backend.app.schemas.analysis import OHLCVPoint
from backend.app.services.authoritative_candle_store import AuthoritativeCandleStore
from backend.app.services.l1_candle_cache import L1CandleCache


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _candles() -> list[OHLCVPoint]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        OHLCVPoint(
            timestamp=base + timedelta(days=i),
            open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=10_000 + i,
        )
        for i in range(3)
    ]


@pytest.fixture(autouse=True)
def isolated_flag():
    """Snapshot flag + env so tests can mutate freely without leaking state."""
    saved_attr = settings.authoritative_candle_store_enabled
    saved_env = os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)
    object.__setattr__(settings, "authoritative_candle_store_enabled", False)
    yield
    object.__setattr__(settings, "authoritative_candle_store_enabled", saved_attr)
    if saved_env is not None:
        os.environ["AUTHORITATIVE_CANDLE_STORE_ENABLED"] = saved_env
    else:
        os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)


def _set_flag(value: bool) -> None:
    object.__setattr__(settings, "authoritative_candle_store_enabled", value)


def _set_env(value: str) -> None:
    os.environ["AUTHORITATIVE_CANDLE_STORE_ENABLED"] = value


def _clear_env() -> None:
    os.environ.pop("AUTHORITATIVE_CANDLE_STORE_ENABLED", None)


def _build_store() -> AuthoritativeCandleStore:
    """AuthoritativeCandleStore with provider/db edges stubbed as AsyncMocks."""
    store = AuthoritativeCandleStore(cache=L1CandleCache(max_capacity=10))
    store._query_db_candles = AsyncMock(return_value=[])  # type: ignore[assignment]
    store._fetch_provider_candles = AsyncMock(return_value=[])  # type: ignore[assignment]
    store._legacy_get_candles = AsyncMock(return_value=_candles())  # type: ignore[assignment]
    return store


# ===========================================================================
# is_enabled() reads the flag live
# ===========================================================================

class TestIsEnabledLiveRead:
    def test_attribute_off_returns_false(self):
        _set_flag(False)
        _clear_env()
        assert AuthoritativeCandleStore().is_enabled() is False

    def test_attribute_on_returns_true(self):
        _set_flag(True)
        _clear_env()
        assert AuthoritativeCandleStore().is_enabled() is True

    @pytest.mark.parametrize(
        "raw,expected",
        [("true", True), ("1", True), ("yes", True), ("on", True),
         ("false", False), ("0", False), ("off", False), ("", False)],
    )
    def test_env_override_parses_truthy_strings(self, raw: str, expected: bool):
        _set_flag(not expected)  # Intentionally contradict env to prove priority
        _set_env(raw)
        # Empty string is treated as "unset" -> falls back to attribute.
        if raw == "":
            _set_flag(expected)
        assert AuthoritativeCandleStore().is_enabled() is expected

    def test_env_cleared_falls_back_to_attribute(self):
        _set_flag(True)
        _clear_env()
        assert AuthoritativeCandleStore().is_enabled() is True


# ===========================================================================
# FR-005 read routing swap based on flag state
# ===========================================================================

class TestFlagRoutingSwap:
    async def test_flag_off_routes_to_legacy(self):
        _set_flag(False)
        store = _build_store()
        out = await store.get_candles("RELIANCE-EQ", "1D")
        assert out == _candles()
        store._legacy_get_candles.assert_awaited_once()
        store._query_db_candles.assert_not_awaited()

    async def test_flag_on_routes_to_authoritative_path(self):
        _set_flag(True)
        store = _build_store()
        # Pre-seed L1 so we don't depend on DB
        store.cache.set("RELIANCE-EQ", "1D", _candles())
        out = await store.get_candles("RELIANCE-EQ", "1D")
        assert out == _candles()
        store._legacy_get_candles.assert_not_awaited()
        store._query_db_candles.assert_not_awaited()  # L1 hit


# ===========================================================================
# FR-009: Instant rollback (flag toggle during active use)
# ===========================================================================

class TestInstantRollbackToggle:
    async def test_toggle_off_to_on_to_off_rerouting(self):
        """US2 AC1: setting flag=false instantly routes reads to legacy path."""
        store = _build_store()

        # 1. Flag ON -> authoritative path (L1 hit)
        _set_flag(True)
        store.cache.set("RELIANCE-EQ", "1D", _candles())
        first = await store.get_candles("RELIANCE-EQ", "1D")
        store._legacy_get_candles.assert_not_awaited()
        assert first == _candles()

        # 2. Toggle to OFF -> next call MUST instantly use legacy path
        _set_flag(False)
        second = await store.get_candles("RELIANCE-EQ", "1D")
        store._legacy_get_candles.assert_awaited_once()
        assert second == _candles()

        # 3. Toggle back ON -> legacy no longer called; authoritative resumes
        store._legacy_get_candles.reset_mock()
        _set_flag(True)
        third = await store.get_candles("RELIANCE-EQ", "1D")
        store._legacy_get_candles.assert_not_awaited()
        assert third == _candles()

    async def test_env_var_toggle_takes_effect_without_restart(self):
        """US2 AC2: providers must succeed across toggles without exceptions/restart."""
        _clear_env()
        store = _build_store()

        # Start env OFF -> legacy
        _set_env("false")
        out_off = await store.get_candles("RELIANCE-EQ", "1D")
        assert out_off == _candles()
        store._legacy_get_candles.assert_awaited_once()

        # Flip env to ON at runtime
        store._legacy_get_candles.reset_mock()
        _set_env("true")
        store.cache.set("RELIANCE-EQ", "1D", _candles())
        out_on = await store.get_candles("RELIANCE-EQ", "1D")
        assert out_on == _candles()
        store._legacy_get_candles.assert_not_awaited()

    async def test_toggle_does_not_raise_exceptions(self):
        """US2 AC2: responses succeed without exceptions during toggles."""
        _set_flag(False)
        store = _build_store()
        # Seed cache so authoritative path also works when ON
        store.cache.set("SYMBOL-EQ", "1D", _candles())

        for value in (True, False, True, False, True):
            _set_flag(value)
            # Should never raise on toggling
            result = await store.get_candles("SYMBOL-EQ", "1D")
            assert result == _candles()


# ===========================================================================
# CANDLE_STORE_DUAL_WRITE flag (Phase 1 dual-write behavior, FR-004)
# ===========================================================================

class TestDualWriteFlag:
    async def test_dual_write_disabled_skips_secondary_sync(self):
        _set_flag(True)
        object.__setattr__(settings, "candle_store_dual_write", False)
        store = _build_store()

        # Patch _sync_legacy_dual_write to detect calls
        store._sync_legacy_dual_write = AsyncMock(return_value=None)  # type: ignore[assignment]
        # Make upsert succeed returning (inserted, updated)
        store._upsert_db_candles = AsyncMock(return_value=(3, 1))  # type: ignore[assignment]

        result = await store.ingest_candles("SYMBOL-EQ", "1D", _candles(), source="FYERS")
        assert result.dual_write_status == "SKIPPED"
        store._sync_legacy_dual_write.assert_not_awaited()

    async def test_dual_write_enabled_succeeds(self):
        """FR-004: dual-write is scheduled non-blocking; primary returns SUCCESS."""
        import asyncio

        _set_flag(True)
        object.__setattr__(settings, "candle_store_dual_write", True)
        store = _build_store()
        store._sync_legacy_dual_write = AsyncMock(return_value=None)  # type: ignore[assignment]
        store._upsert_db_candles = AsyncMock(return_value=(3, 1))  # type: ignore[assignment]

        result = await store.ingest_candles("SYMBOL-EQ", "1D", _candles(), source="FYERS")
        assert result.dual_write_status == "SUCCESS"
        # Drain supervised background dual-write task
        if store._background_tasks:
            await asyncio.gather(*list(store._background_tasks), return_exceptions=True)
        store._sync_legacy_dual_write.assert_awaited_once()

    async def test_dual_write_failure_is_not_blocking(self):
        """FR-004: secondary legacy write failure must NOT fail the primary request."""
        import asyncio

        _set_flag(True)
        object.__setattr__(settings, "candle_store_dual_write", True)
        store = _build_store()
        store._sync_legacy_dual_write = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[assignment]
        store._upsert_db_candles = AsyncMock(return_value=(3, 1))  # type: ignore[assignment]

        result = await store.ingest_candles("SYMBOL-EQ", "1D", _candles(), source="FYERS")
        # Primary succeeds immediately; dual-write runs in background.
        assert result.dual_write_status == "SUCCESS"
        assert result.inserted_count == 3
        assert result.updated_count == 1
        if store._background_tasks:
            await asyncio.gather(*list(store._background_tasks), return_exceptions=True)