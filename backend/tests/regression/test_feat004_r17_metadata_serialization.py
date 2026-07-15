"""
R17 regression — FEAT-004 metadata serialization.

Verifies that FEAT-004 metadata attached by the overlay is part of the
official API contract: it survives model_dump() and JSON serialization
on the FinalRecommendation schema.

Scope: R17 only. No other requirements touched.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.schemas.analysis import (
    AnalysisMode,
    BacktestResult,
    FinalRecommendation,
    OHLCVPoint,
    RecommendationReasoning,
    TechnicalAnalysisResult,
)
from app.agents.recommendation_agent import RecommendationAgent


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _bm_rising_300() -> pd.DataFrame:
    """300 daily candles with rising close (FAVORABLE regime), fresh timestamps."""
    base = datetime.now(timezone.utc) - timedelta(days=299)
    rows = []
    for i in range(300):
        p = 100.0 + i * 0.5
        rows.append({
            "timestamp": base + timedelta(days=i),
            "open": p - 1.0, "high": p + 2.0,
            "low": p - 2.0, "close": p, "volume": 1000000,
        })
    return pd.DataFrame(rows).set_index("timestamp").sort_index()


def _bm_falling_300() -> pd.DataFrame:
    """300 daily candles with falling close (DEFENSIVE regime), fresh timestamps."""
    base = datetime.now(timezone.utc) - timedelta(days=299)
    rows = []
    for i in range(300):
        p = 200.0 - i * 0.5
        rows.append({
            "timestamp": base + timedelta(days=i),
            "open": p + 1.0, "high": p + 2.0,
            "low": p - 2.0, "close": p, "volume": 1000000,
        })
    return pd.DataFrame(rows).set_index("timestamp").sort_index()


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


def _run(
    agent: RecommendationAgent,
    feat004_config: dict | None = None,
    benchmark_ohlcv: pd.DataFrame | None = None,
) -> FinalRecommendation:
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
        sector_mapping=None,
        sector_ohlcv_cache=None,
    )


# ---------------------------------------------------------------------------
# 1. Disabled FEAT-004 — all FEAT-004 fields serialize correctly
# ---------------------------------------------------------------------------

def test_r17_disabled_feat004_serializes():
    agent = RecommendationAgent()
    result = _run(agent, feat004_config={"enabled": False, "stage": "SHADOW"})

    dumped = result.model_dump(mode="json")
    assert "feat004" in dumped
    assert dumped["feat004"] is not None
    assert dumped["feat004"]["feat004_enabled"] is False
    assert dumped["feat004"]["feat004_abstained_reason"] == "feat004_disabled"


# ---------------------------------------------------------------------------
# 2. SHADOW mode — metadata serialized, score unchanged
# ---------------------------------------------------------------------------

def test_r17_shadow_mode_metadata_serialized():
    agent = RecommendationAgent()
    result = _run(
        agent,
        feat004_config={"enabled": True, "stage": "SHADOW"},
        benchmark_ohlcv=_bm_rising_300(),
    )

    dumped = result.model_dump(mode="json")
    assert dumped["feat004"] is not None
    assert dumped["feat004"]["feat004_enabled"] is True
    assert dumped["feat004"]["feat004_stage"] == "SHADOW"
    assert dumped["feat004"]["market_regime_state"] in {"FAV", "NEU", "CAU", "DEF", "ABS"}
    assert dumped["feat004"]["feat004_score_adjustment"] == 0.0
    assert dumped["feat004"]["feat004_pre_adjustment_score"] == dumped["feat004"]["feat004_post_adjustment_score"]


# ---------------------------------------------------------------------------
# 3. ACTIVE mode — metadata serialized, score modified
# ---------------------------------------------------------------------------

def test_r17_active_mode_metadata_serialized():
    agent = RecommendationAgent()
    result = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=_bm_falling_300(),
    )

    dumped = result.model_dump(mode="json")
    assert dumped["feat004"] is not None
    assert dumped["feat004"]["feat004_enabled"] is True
    assert dumped["feat004"]["feat004_stage"] == "ACTIVE"
    assert dumped["feat004"]["feat004_score_adjustment"] != 0.0 or dumped["feat004"]["market_regime_state"] == "NEU"
    assert "feat004_pre_adjustment_score" in dumped["feat004"]
    assert "feat004_post_adjustment_score" in dumped["feat004"]


# ---------------------------------------------------------------------------
# 4. Benchmark unavailable — abstained reason serialized
# ---------------------------------------------------------------------------

def test_r17_benchmark_unavailable_abstained_serialized():
    agent = RecommendationAgent()
    result = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=None,
    )

    dumped = result.model_dump(mode="json")
    assert dumped["feat004"] is not None
    assert dumped["feat004"]["market_regime_state"] == "ABS"
    assert dumped["feat004"]["feat004_abstained_reason"] == "benchmark_unavailable"


# ---------------------------------------------------------------------------
# 5. API model_dump() — all FEAT-004 fields present
# ---------------------------------------------------------------------------

def test_r17_model_dump_all_fields_present():
    agent = RecommendationAgent()
    result = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=_bm_rising_300(),
    )

    dumped = result.model_dump(mode="json")
    feat004 = dumped["feat004"]
    expected_keys = {
        "feat004_enabled", "feat004_stage", "market_regime_state",
        "benchmark_symbol_used", "benchmark_trend_inputs",
        "feat004_pre_adjustment_score", "feat004_score_adjustment",
        "feat004_post_adjustment_score", "feat004_watch_downgrade_applied",
        "feat004_abstained_reason", "sector_mapped", "sector_index_symbol",
        "sector_roc20", "sector_relative_strength_ratio",
        "sector_regime_state", "feat004_sector_abstained_reason",
        "feat004_explanation",
    }
    assert expected_keys.issubset(set(feat004.keys())), (
        f"Missing keys: {expected_keys - set(feat004.keys())}"
    )


# ---------------------------------------------------------------------------
# 6. JSON serialization — fields survive
# ---------------------------------------------------------------------------

def test_r17_json_serialization_survives():
    agent = RecommendationAgent()
    result = _run(
        agent,
        feat004_config={"enabled": True, "stage": "ACTIVE"},
        benchmark_ohlcv=_bm_rising_300(),
    )

    dumped = result.model_dump(mode="json")
    json_str = json.dumps(dumped)
    parsed = json.loads(json_str)

    assert "feat004" in parsed
    assert parsed["feat004"]["feat004_enabled"] is True
    assert parsed["feat004"]["market_regime_state"] in {"FAV", "NEU", "CAU", "DEF", "ABS"}
    assert "benchmark_trend_inputs" in parsed["feat004"]
    assert "feat004_explanation" in parsed["feat004"]


# ---------------------------------------------------------------------------
# 7. Backward compatibility — existing consumers unaffected
# ---------------------------------------------------------------------------

def test_r17_backward_compat_getattr_still_works():
    """Existing code that reads feat004 via getattr must still work."""
    agent = RecommendationAgent()
    result = _run(
        agent,
        feat004_config={"enabled": True, "stage": "SHADOW"},
        benchmark_ohlcv=_bm_rising_300(),
    )

    assert hasattr(result, "feat004")
    log = getattr(result, "feat004")
    assert isinstance(log, dict)
    assert log["feat004_enabled"] is True


def test_r17_backward_compat_default_none_when_not_set():
    """FinalRecommendation constructed without feat004 must default to None."""
    rec = FinalRecommendation(
        action="BUY", confidence=0.8, score=75.0,
        reasoning=RecommendationReasoning(bullets=[], risk_factors=[], invalidation_signals=[]),
        trade_plans=[], summary="test",
    )
    assert rec.feat004 is None
    dumped = rec.model_dump()
    assert dumped["feat004"] is None


def test_r17_backward_compat_existing_fields_preserved():
    """All pre-existing schema fields must still be present and correct."""
    agent = RecommendationAgent()
    result = _run(
        agent,
        feat004_config={"enabled": False, "stage": "SHADOW"},
    )

    dumped = result.model_dump(mode="json")
    for key in ("action", "confidence", "score", "reasoning", "trade_plans", "summary"):
        assert key in dumped, f"Existing field {key} missing from model_dump"
    for key in ("feat007_enabled", "feat007_stage", "feat007_explanation"):
        assert key in dumped, f"FEAT-007 field {key} missing from model_dump"
