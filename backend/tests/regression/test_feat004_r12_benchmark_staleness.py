"""
R12 regression — FEAT-004 live benchmark staleness enforcement.

Verifies that the orchestrator's _resolve_feat004_benchmark enforces the
configured staleness limit (settings.feat004_staleness_limit_days) so that
a stale benchmark causes the FEAT-004 overlay to ABSTAIN instead of
classifying the market regime on stale inputs.

Scope: R12 only. No other requirements touched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from backend.app.agents.orchestrator_agent import OrchestratorAgent
from backend.app.config import settings
from backend.app.schemas.analysis import OHLCVPoint


def _make_candles(n: int, last_ts: datetime, base: float = 100.0) -> list[OHLCVPoint]:
    candles: list[OHLCVPoint] = []
    for i in range(n):
        ts = last_ts - timedelta(days=(n - 1 - i))
        p = base + i * 0.5
        candles.append(
            OHLCVPoint(
                timestamp=ts,
                open=p - 1.0,
                high=p + 2.0,
                low=p - 2.0,
                close=p,
                volume=1_000_000,
            )
        )
    return candles


def _enable_feat004(monkeypatch: pytest.MonkeyPatch, staleness_limit_days: int = 1) -> None:
    monkeypatch.setattr(settings, "feat004_enabled", True)
    monkeypatch.setattr(settings, "feat004_benchmark_symbols", "NIFTY500")
    monkeypatch.setattr(settings, "feat004_min_benchmark_candles", 220)
    monkeypatch.setattr(settings, "feat004_staleness_limit_days", staleness_limit_days)


@pytest.mark.asyncio
async def test_r12_fresh_benchmark_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_feat004(monkeypatch, staleness_limit_days=1)
    fresh_last = datetime.now(timezone.utc) - timedelta(hours=2)
    candles = _make_candles(250, fresh_last)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(return_value=candles)

    df, cache, _reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is not None
    assert len(df) == 250
    assert cache is None


@pytest.mark.asyncio
async def test_r12_stale_benchmark_abstains(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_feat004(monkeypatch, staleness_limit_days=1)
    stale_last = datetime.now(timezone.utc) - timedelta(days=5)
    candles = _make_candles(250, stale_last)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(return_value=candles)

    df, cache, _reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is None
    assert cache is None


@pytest.mark.asyncio
async def test_r12_missing_benchmark_existing_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_feat004(monkeypatch, staleness_limit_days=1)
    fresh_last = datetime.now(timezone.utc) - timedelta(hours=2)
    candles = _make_candles(50, fresh_last)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(return_value=candles)

    df, cache, _reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is None
    assert cache is None


@pytest.mark.asyncio
async def test_r12_fetch_exception_existing_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_feat004(monkeypatch, staleness_limit_days=1)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("network"))

    df, cache, _reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is None
    assert cache is None


@pytest.mark.asyncio
async def test_r12_disabled_feat004_byte_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "feat004_enabled", False)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(return_value=[])

    df, cache, _reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is None
    assert cache is None
    agent.fyers_service.fetch_ohlcv.assert_not_called()


@pytest.mark.asyncio
async def test_r12_deterministic_repeated_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_feat004(monkeypatch, staleness_limit_days=1)
    stale_last = datetime.now(timezone.utc) - timedelta(days=5)
    candles = _make_candles(250, stale_last)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(return_value=candles)

    df1, cache1, _r1, _s1 = await agent._resolve_feat004_benchmark()
    df2, cache2, _r2, _s2 = await agent._resolve_feat004_benchmark()
    assert (df1, cache1) == (df2, cache2)
    assert df1 is None


@pytest.mark.asyncio
async def test_r12_fallback_symbol_when_primary_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "feat004_enabled", True)
    monkeypatch.setattr(settings, "feat004_benchmark_symbols", "NIFTY500,NIFTY50")
    monkeypatch.setattr(settings, "feat004_min_benchmark_candles", 220)
    monkeypatch.setattr(settings, "feat004_staleness_limit_days", 1)

    stale_last = datetime.now(timezone.utc) - timedelta(days=5)
    fresh_last = datetime.now(timezone.utc) - timedelta(hours=2)
    stale_candles = _make_candles(250, stale_last)
    fresh_candles = _make_candles(250, fresh_last)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(side_effect=[stale_candles, fresh_candles])

    df, cache, _reason, _sym = await agent._resolve_feat004_benchmark()
    assert df is not None
    assert len(df) == 250
    assert agent.fyers_service.fetch_ohlcv.await_count == 2


def test_r12_stale_benchmark_overlay_abstains() -> None:
    from backend.app.services.feat004_regime_overlay import apply_feat004_regime_overlay

    score, label, log = apply_feat004_regime_overlay(
        composite_score=75.0,
        current_label="BUY",
        symbol="TEST",
        benchmark_ohlcv=None,
        sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert log["market_regime_state"] == "ABS"
    assert log["feat004_abstained_reason"] == "benchmark_unavailable"
    assert score == 75.0
    assert label == "BUY"
