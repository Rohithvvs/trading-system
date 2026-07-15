"""
FEAT-004 regression — benchmark_symbol_used logging field.

Verifies the confirmed implementation gap fix: when a benchmark is
successfully resolved, ``benchmark_symbol_used`` is populated with the
resolved symbol ("NIFTY500" / "NIFTY50"); when FEAT-004 abstains it
remains ``None`` exactly as before.

Scope: only the ``benchmark_symbol_used`` field. No scoring,
classification, FEAT-007, FEAT-008, or benchmark selection logic is
exercised or changed here.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.services.feat004_regime_overlay import apply_feat004_regime_overlay
from app.agents.recommendation_agent import RecommendationAgent
from app.schemas.analysis import (
    AnalysisMode,
    BacktestResult,
    OHLCVPoint,
    TechnicalAnalysisResult,
)
from backend.app.agents.orchestrator_agent import OrchestratorAgent
from backend.app.config import settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _bm_rising_300() -> pd.DataFrame:
    """300 fresh rising daily candles — resolves to a non-ABS regime."""
    base = datetime.now(timezone.utc) - timedelta(days=299)
    rows = []
    for i in range(300):
        p = 100.0 + i * 0.5
        rows.append({
            "timestamp": base + timedelta(days=i),
            "open": p - 1.0, "high": p + 2.0,
            "low": p - 2.0, "close": p, "volume": 1_000_000,
        })
    return pd.DataFrame(rows).set_index("timestamp").sort_index()


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


def _tech(score: float = 80.0) -> TechnicalAnalysisResult:
    return TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=score,
        indicators={}, summary="test",
    )


def _backtest(ret: float = 15.0) -> BacktestResult:
    return BacktestResult(
        mode=AnalysisMode.swing, strategy_name="sma_rsi_macd",
        total_return=ret, max_drawdown=5.0, win_rate=60.0,
        profit_factor=2.0, trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )


def _enable_feat004(monkeypatch: pytest.MonkeyPatch, symbols: str = "NIFTY500") -> None:
    monkeypatch.setattr(settings, "feat004_enabled", True)
    monkeypatch.setattr(settings, "feat004_benchmark_symbols", symbols)
    monkeypatch.setattr(settings, "feat004_min_benchmark_candles", 220)
    monkeypatch.setattr(settings, "feat004_staleness_limit_days", 1)


def _run_agent(
    benchmark_ohlcv: pd.DataFrame | None,
    benchmark_symbol: str | None,
    feat004_config: dict,
) -> object:
    agent = RecommendationAgent()
    return agent.run(
        symbol="TEST",
        technical_results=[_tech()],
        sentiment_label="positive",
        sentiment_score=0.5,
        fundamental_result=None,
        backtests=[_backtest()],
        candles_by_mode={AnalysisMode.swing: []},
        feat004_config=feat004_config,
        benchmark_ohlcv=benchmark_ohlcv,
        benchmark_symbol=benchmark_symbol,
        sector_mapping=None,
        sector_ohlcv_cache=None,
    )


# ---------------------------------------------------------------------------
# 1. NIFTY500 resolution logs NIFTY500
# ---------------------------------------------------------------------------
def test_nifty500_resolution_logs_nifty500():
    _score, _label, log = apply_feat004_regime_overlay(
        composite_score=70.0,
        current_label="WATCH",
        symbol="TEST",
        benchmark_ohlcv=_bm_rising_300(),
        sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_symbol="NIFTY500",
    )
    assert log["benchmark_symbol_used"] == "NIFTY500"
    assert log["feat004_abstained_reason"] is None


# ---------------------------------------------------------------------------
# 2. NIFTY50 fallback logs NIFTY50
# ---------------------------------------------------------------------------
def test_nifty50_fallback_logs_nifty50():
    _score, _label, log = apply_feat004_regime_overlay(
        composite_score=70.0,
        current_label="WATCH",
        symbol="TEST",
        benchmark_ohlcv=_bm_rising_300(),
        sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_symbol="NIFTY50",
    )
    assert log["benchmark_symbol_used"] == "NIFTY50"
    assert log["feat004_abstained_reason"] is None


# ---------------------------------------------------------------------------
# 3. Benchmark unavailable logs None
# ---------------------------------------------------------------------------
def test_benchmark_unavailable_logs_none():
    _score, _label, log = apply_feat004_regime_overlay(
        composite_score=70.0,
        current_label="WATCH",
        symbol="TEST",
        benchmark_ohlcv=None,
        sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_symbol=None,
    )
    assert log["benchmark_symbol_used"] is None
    assert log["market_regime_state"] == "ABS"
    assert log["feat004_abstained_reason"] == "benchmark_unavailable"


# ---------------------------------------------------------------------------
# 4. Disabled mode still logs None
# ---------------------------------------------------------------------------
def test_disabled_mode_logs_none():
    _score, _label, log = apply_feat004_regime_overlay(
        composite_score=70.0,
        current_label="WATCH",
        symbol="TEST",
        benchmark_ohlcv=_bm_rising_300(),
        sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config={"enabled": False, "stage": "SHADOW"},
        benchmark_symbol="NIFTY500",
    )
    assert log["benchmark_symbol_used"] is None
    assert log["feat004_abstained_reason"] == "feat004_disabled"


# ---------------------------------------------------------------------------
# 5. Serialization includes benchmark_symbol_used
# ---------------------------------------------------------------------------
def test_serialization_includes_benchmark_symbol_used():
    result = _run_agent(
        benchmark_ohlcv=_bm_rising_300(),
        benchmark_symbol="NIFTY500",
        feat004_config={"enabled": True, "stage": "ACTIVE"},
    )
    dumped = result.model_dump(mode="json")
    assert "benchmark_symbol_used" in dumped["feat004"]
    assert dumped["feat004"]["benchmark_symbol_used"] == "NIFTY500"


def test_serialization_includes_none_when_abstained():
    result = _run_agent(
        benchmark_ohlcv=None,
        benchmark_symbol=None,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
    )
    dumped = result.model_dump(mode="json")
    assert "benchmark_symbol_used" in dumped["feat004"]
    assert dumped["feat004"]["benchmark_symbol_used"] is None


# ---------------------------------------------------------------------------
# 6. Backward compatibility preserved
# ---------------------------------------------------------------------------
def test_backward_compat_omitted_benchmark_symbol_defaults_none():
    """Callers that omit benchmark_symbol (old call sites) still get None."""
    _score, _label, log = apply_feat004_regime_overlay(
        composite_score=70.0,
        current_label="WATCH",
        symbol="TEST",
        benchmark_ohlcv=_bm_rising_300(),
        sector_mapping=None,
        sector_ohlcv_cache=None,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert log["benchmark_symbol_used"] is None


@pytest.mark.asyncio
async def test_backward_compat_orchestrator_returns_resolved_symbol(monkeypatch: pytest.MonkeyPatch):
    """Orchestrator threads the resolved symbol as the 4th return element."""
    _enable_feat004(monkeypatch, symbols="NIFTY500")
    fresh_last = datetime.now(timezone.utc) - timedelta(hours=2)
    candles = _make_candles(250, fresh_last)

    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(return_value=candles)

    df, _cache, reason, sym = await agent._resolve_feat004_benchmark()
    assert sym == "NIFTY500"
    assert reason is None
    assert df is not None


@pytest.mark.asyncio
async def test_backward_compat_orchestrator_unavailable_returns_none_symbol(monkeypatch: pytest.MonkeyPatch):
    """When no benchmark resolves, the 4th element stays None (abstain)."""
    _enable_feat004(monkeypatch, symbols="NIFTY500")
    agent = OrchestratorAgent(None)
    agent.fyers_service.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("network"))

    df, _cache, reason, sym = await agent._resolve_feat004_benchmark()
    assert sym is None
    assert reason == "benchmark_fetch_failed"
    assert df is None
