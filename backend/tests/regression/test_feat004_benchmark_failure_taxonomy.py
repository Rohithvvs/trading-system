"""
FEAT-004 regression — benchmark failure taxonomy.

Verifies the confirmed implementation gap fix: the orchestrator's
``_resolve_feat004_benchmark`` returns the specific failure reason
(``benchmark_fetch_failed`` / ``benchmark_data_stale`` /
``insufficient_benchmark_history``) instead of always collapsing to
``benchmark_fetch_failed``.

Scope: only the failure reason returned by ``_resolve_feat004_benchmark``.
No benchmark selection, fallback order, overlay, FEAT-007, or FEAT-008
logic is exercised or changed here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from backend.app.agents.orchestrator_agent import OrchestratorAgent
from backend.app.config import settings
from backend.app.schemas.analysis import OHLCVPoint


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _make_candles(n: int, last_ts: datetime, base: float = 100.0) -> list[OHLCVPoint]:
    candles: list[OHLCVPoint] = []
    for i in range(n):
        ts = last_ts - timedelta(days=(n - 1 - i))
        p = base + i * 0.5
        candles.append(OHLCVPoint(
            timestamp=ts, open=p - 1.0, high=p + 2.0,
            low=p - 2.0, close=p, volume=1_000_000,
        ))
    return candles


def _enable_feat004(monkeypatch: pytest.MonkeyPatch, symbols: str = "NIFTY500") -> None:
    monkeypatch.setattr(settings, "feat004_enabled", True)
    monkeypatch.setattr(settings, "feat004_benchmark_symbols", symbols)
    monkeypatch.setattr(settings, "feat004_min_benchmark_candles", 220)
    monkeypatch.setattr(settings, "feat004_staleness_limit_days", 1)


# ---------------------------------------------------------------------------
# 1. Stale benchmark returns benchmark_data_stale
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_benchmark_returns_data_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_feat004(monkeypatch, symbols="NIFTY500")
    stale_last = datetime.now(timezone.utc) - timedelta(days=5)
    candles = _make_candles(250, stale_last)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(return_value=candles)

    df, _cache, reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is None
    assert reason == "benchmark_data_stale"


# ---------------------------------------------------------------------------
# 2. Insufficient history returns insufficient_benchmark_history
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_insufficient_history_returns_insufficient_benchmark_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_feat004(monkeypatch, symbols="NIFTY500")
    fresh_last = datetime.now(timezone.utc) - timedelta(hours=2)
    candles = _make_candles(50, fresh_last)  # below min_candles=220

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(return_value=candles)

    df, _cache, reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is None
    assert reason == "insufficient_benchmark_history"


# ---------------------------------------------------------------------------
# 3. Fetch exception returns benchmark_fetch_failed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_exception_returns_benchmark_fetch_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_feat004(monkeypatch, symbols="NIFTY500")

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("network"))

    df, _cache, reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is None
    assert reason == "benchmark_fetch_failed"


# ---------------------------------------------------------------------------
# 4. Fallback success clears previous failure reason
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fallback_success_clears_previous_failure_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "feat004_enabled", True)
    monkeypatch.setattr(settings, "feat004_benchmark_symbols", "NIFTY500,NIFTY50")
    monkeypatch.setattr(settings, "feat004_min_benchmark_candles", 220)
    monkeypatch.setattr(settings, "feat004_staleness_limit_days", 1)

    stale_last = datetime.now(timezone.utc) - timedelta(days=5)
    fresh_last = datetime.now(timezone.utc) - timedelta(hours=2)
    stale_candles = _make_candles(250, stale_last)   # NIFTY500 -> stale
    fresh_candles = _make_candles(250, fresh_last)    # NIFTY50  -> resolves

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(side_effect=[stale_candles, fresh_candles])

    df, _cache, reason, sym = await agent._resolve_feat004_benchmark()
    assert df is not None
    assert reason is None                 # cleared on success
    assert sym == "NIFTY50"
    assert agent.fyers_service.fetch_ohlcv.await_count == 2


@pytest.mark.asyncio
async def test_fallback_success_clears_fetch_failure_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fetch exception on the primary, then a successful fallback, must
    return reason=None (not benchmark_fetch_failed)."""
    monkeypatch.setattr(settings, "feat004_enabled", True)
    monkeypatch.setattr(settings, "feat004_benchmark_symbols", "NIFTY500,NIFTY50")
    monkeypatch.setattr(settings, "feat004_min_benchmark_candles", 220)
    monkeypatch.setattr(settings, "feat004_staleness_limit_days", 1)

    fresh_last = datetime.now(timezone.utc) - timedelta(hours=2)
    fresh_candles = _make_candles(250, fresh_last)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(
        side_effect=[RuntimeError("network"), fresh_candles]
    )

    df, _cache, reason, sym = await agent._resolve_feat004_benchmark()
    assert df is not None
    assert reason is None
    assert sym == "NIFTY50"


# ---------------------------------------------------------------------------
# 5. Disabled mode unchanged
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disabled_mode_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "feat004_enabled", False)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(return_value=[])

    df, cache, reason, sym = await agent._resolve_feat004_benchmark()
    assert df is None
    assert cache is None
    assert reason is None
    assert sym is None
    agent.fyers_service.fetch_ohlcv.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Backward compatibility preserved
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_backward_compat_all_fail_reason_is_specific_not_generic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When every candidate fails, the returned reason must reflect the last
    candidate's specific failure (here: stale) rather than the legacy
    generic benchmark_fetch_failed."""
    monkeypatch.setattr(settings, "feat004_enabled", True)
    monkeypatch.setattr(settings, "feat004_benchmark_symbols", "NIFTY500,NIFTY50")
    monkeypatch.setattr(settings, "feat004_min_benchmark_candles", 220)
    monkeypatch.setattr(settings, "feat004_staleness_limit_days", 1)

    stale_last = datetime.now(timezone.utc) - timedelta(days=5)
    stale_candles = _make_candles(250, stale_last)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(
        side_effect=[stale_candles, stale_candles]
    )

    df, _cache, reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is None
    assert reason == "benchmark_data_stale"


@pytest.mark.asyncio
async def test_backward_compat_zero_symbols_returns_legacy_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty configured symbol list: no candidate is tried, so the legacy
    default benchmark_fetch_failed must be preserved (unchanged behaviour)."""
    _enable_feat004(monkeypatch, symbols="")

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(return_value=[])

    df, _cache, reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is None
    assert reason == "benchmark_fetch_failed"
    agent.fyers_service.fetch_ohlcv.assert_not_called()


@pytest.mark.asyncio
async def test_backward_compat_empty_candles_returns_insufficient_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fetch that returns [] (no exception) is an insufficient-history
    failure, not a fetch failure — preserves the distinction in the taxonomy."""
    _enable_feat004(monkeypatch, symbols="NIFTY500")

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(return_value=[])

    df, _cache, reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is None
    assert reason == "insufficient_benchmark_history"
