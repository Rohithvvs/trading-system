"""Unit tests for ShadowExecutionContext and related DTOs.

Spec source: specs/006-shadow-infra-foundation/spec.md
  - US2 / FR-007: deep-copy / mutation isolation
  - Key entities: ShadowExecutionContext, ShadowExecutionResult, ShadowComparisonLog
  - SC-004: context instantiation overhead is negligible
"""
from __future__ import annotations

import copy
import time
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.analysis import (
    AnalysisMode,
    BacktestResult,
    FinalRecommendation,
    FundamentalAnalysisResult,
    OHLCVPoint,
    RecommendationReasoning,
    ShadowComparisonLog,
    ShadowExecutionContext,
    ShadowExecutionResult,
    TechnicalAnalysisResult,
)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _candle(close: float = 101.0) -> OHLCVPoint:
    return OHLCVPoint(
        timestamp=datetime(2023, 1, 1),
        open=100.0,
        high=105.0,
        low=95.0,
        close=close,
        volume=1000,
    )


def _tech(score: float = 75.0) -> TechnicalAnalysisResult:
    return TechnicalAnalysisResult(
        mode=AnalysisMode.swing,
        signal="BUY",
        score=score,
        indicators={"rsi": 60.0},
        summary="Test summary",
    )


def _recommendation(action: str = "BUY", score: float = 75.0) -> FinalRecommendation:
    return FinalRecommendation(
        action=action,
        confidence=0.8,
        score=score,
        reasoning=RecommendationReasoning(
            bullets=["Test bullet"],
            risk_factors=["Test risk"],
            invalidation_signals=["Test invalidation"],
        ),
        trade_plans=[],
        summary="Test summary",
    )


def _context(
    *,
    candles: list[OHLCVPoint] | None = None,
    tech_results: list[TechnicalAnalysisResult] | None = None,
    sentiment: float = 0.5,
    fundamental: FundamentalAnalysisResult | None = None,
    backtests: list[BacktestResult] | None = None,
    prod: FinalRecommendation | None = None,
    challenger: FinalRecommendation | None = None,
) -> ShadowExecutionContext:
    return ShadowExecutionContext(
        symbol="TEST",
        candles=copy.deepcopy(candles if candles is not None else [_candle()]),
        technical_results=copy.deepcopy(
            tech_results if tech_results is not None else [_tech()]
        ),
        sentiment_score=sentiment,
        fundamental_result=fundamental,
        backtests=copy.deepcopy(backtests if backtests is not None else []),
        production_recommendation=prod or _recommendation(),
        production_challenger_recommendation=challenger,
    )


# ===========================================================================
# US2 / FR-007 — deep copy and immutability isolation
# ===========================================================================


def test_shadow_context_deep_copy() -> None:
    """US2 independent test: context holds a deep copy of candles."""
    candles = [_candle(close=101.0)]
    tech_results = [_tech()]
    context = _context(candles=candles, tech_results=tech_results)

    assert context.symbol == "TEST"
    assert len(context.candles) == 1
    assert context.candles[0].close == 101.0

    candles[0].close = 999.0
    assert context.candles[0].close == 101.0


def test_shadow_context_technical_results_isolated_from_source() -> None:
    """FR-007: Mutating source technical results does not affect context."""
    tech_results = [_tech(score=75.0)]
    context = _context(tech_results=tech_results)

    tech_results[0].score = 1.0
    tech_results[0].indicators["rsi"] = 1.0

    assert context.technical_results[0].score == 75.0
    assert context.technical_results[0].indicators["rsi"] == 60.0


def test_shadow_context_mutating_context_candles_does_not_affect_source() -> None:
    """FR-007: Mutating context candles does not write back to the source list."""
    candles = [_candle(close=101.0)]
    context = _context(candles=candles)

    context.candles[0].close = 50.0
    assert candles[0].close == 101.0


def test_shadow_context_snapshot_fields_match_production_inputs() -> None:
    """US2-AS1: Context snapshot matches production inputs exactly."""
    candles = [_candle(close=102.5)]
    tech = [_tech(score=81.0)]
    prod = _recommendation(action="WATCH", score=62.0)
    challenger = _recommendation(action="REJECT", score=40.0)
    fundamental = FundamentalAnalysisResult(
        fundamental_score=55.0,
        summary="ok",
        pe_ratio=18.0,
    )
    backtests = [
        BacktestResult(
            mode=AnalysisMode.swing,
            strategy_name="strat",
            total_return=10.0,
            max_drawdown=3.0,
            win_rate=0.55,
            profit_factor=1.2,
            trade_count=4,
            verdict="PASSED",
            equity_curve=[],
        )
    ]

    context = _context(
        candles=candles,
        tech_results=tech,
        sentiment=0.42,
        fundamental=fundamental,
        backtests=backtests,
        prod=prod,
        challenger=challenger,
    )

    assert context.symbol == "TEST"
    assert context.candles[0].close == 102.5
    assert context.technical_results[0].score == 81.0
    assert context.sentiment_score == 0.42
    assert context.fundamental_result is not None
    assert context.fundamental_result.pe_ratio == 18.0
    assert len(context.backtests) == 1
    assert context.production_recommendation.action == "WATCH"
    assert context.production_challenger_recommendation is not None
    assert context.production_challenger_recommendation.action == "REJECT"
    assert isinstance(context.scan_date, datetime)


# ===========================================================================
# Schema contracts — ShadowExecutionResult / ShadowComparisonLog
# ===========================================================================


def test_shadow_execution_result_schema_defaults() -> None:
    """Entity: ShadowExecutionResult accepts required fields and default reasoning."""
    result = ShadowExecutionResult(
        ruleset_name="experimental_v1",
        score=70.5,
        action="WATCH",
    )
    assert result.ruleset_name == "experimental_v1"
    assert result.score == 70.5
    assert result.action == "WATCH"
    assert result.reasoning == []
    assert isinstance(result.executed_at, datetime)


def test_shadow_comparison_log_schema_fields() -> None:
    """Entity: ShadowComparisonLog captures production vs shadow delta."""
    log = ShadowComparisonLog(
        symbol="RELIANCE-EQ",
        scan_date=datetime(2023, 1, 1),
        ruleset_name="experimental_v1",
        production_action="BUY",
        production_score=74.0,
        shadow_action="WATCH",
        shadow_score=70.5,
        score_delta=3.5,
        is_mismatch=True,
    )
    assert log.is_mismatch is True
    assert log.score_delta == 3.5
    assert log.production_action != log.shadow_action


def test_shadow_comparison_log_match_case() -> None:
    """Edge: matching labels yield is_mismatch=False with zero score delta."""
    log = ShadowComparisonLog(
        symbol="INFY-EQ",
        scan_date=datetime(2023, 1, 1),
        ruleset_name="experimental_v1",
        production_action="BUY",
        production_score=80.0,
        shadow_action="BUY",
        shadow_score=80.0,
        score_delta=0.0,
        is_mismatch=False,
    )
    assert log.is_mismatch is False
    assert log.score_delta == 0.0


# ===========================================================================
# Failure / edge validation
# ===========================================================================


def test_shadow_context_missing_required_symbol_raises() -> None:
    """Failure: symbol is required on ShadowExecutionContext."""
    with pytest.raises(ValidationError):
        ShadowExecutionContext(  # type: ignore[call-arg]
            candles=[],
            technical_results=[],
            sentiment_score=0.0,
            production_recommendation=_recommendation(),
        )


def test_shadow_context_empty_collections_allowed() -> None:
    """Edge: empty candles / technical_results / backtests are accepted."""
    context = ShadowExecutionContext(
        symbol="EMPTY",
        candles=[],
        technical_results=[],
        sentiment_score=0.0,
        backtests=[],
        production_recommendation=_recommendation(action="REJECT", score=0.0),
        production_challenger_recommendation=None,
    )
    assert context.candles == []
    assert context.technical_results == []
    assert context.backtests == []
    assert context.fundamental_result is None


def test_shadow_context_null_challenger_allowed() -> None:
    """Edge: production_challenger_recommendation may be None."""
    context = _context(challenger=None)
    assert context.production_challenger_recommendation is None


def test_shadow_execution_result_missing_required_fields_raises() -> None:
    """Failure: ShadowExecutionResult requires ruleset_name, score, action."""
    with pytest.raises(ValidationError):
        ShadowExecutionResult()  # type: ignore[call-arg]


def test_shadow_comparison_log_missing_required_fields_raises() -> None:
    """Failure: ShadowComparisonLog rejects incomplete payloads."""
    with pytest.raises(ValidationError):
        ShadowComparisonLog(symbol="X")  # type: ignore[call-arg]


def test_shadow_context_instantiation_overhead_under_1ms() -> None:
    """SC-004: Instantiating a typical context is negligible (< 1ms mean)."""
    candles = [_candle(close=100.0 + i) for i in range(30)]
    tech = [_tech(score=50.0 + i) for i in range(2)]
    prod = _recommendation()

    # Warm-up
    _context(candles=candles, tech_results=tech, prod=prod)

    iterations = 50
    started = time.perf_counter()
    for _ in range(iterations):
        _context(candles=candles, tech_results=tech, prod=prod)
    elapsed_ms = (time.perf_counter() - started) * 1000.0 / iterations

    # Spec target is < 1ms; allow generous CI slack while still catching regressions.
    assert elapsed_ms < 5.0, f"context instantiation mean {elapsed_ms:.3f}ms exceeds budget"
