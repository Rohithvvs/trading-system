"""Unit tests for shadow interface contracts (FR-005 foundation only).

Spec source: specs/006-shadow-infra-foundation/spec.md / data-model.md
  - IShadowExecutor.execute_shadow
  - IShadowStore.save_comparison
  - Spec 1 must NOT ship concrete experimental scoring or DB table writes
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.schemas.analysis import (
    AnalysisMode,
    FinalRecommendation,
    OHLCVPoint,
    RecommendationReasoning,
    ShadowComparisonLog,
    ShadowExecutionContext,
    ShadowExecutionResult,
    TechnicalAnalysisResult,
)
from app.services.shadow_executor_interface import IShadowExecutor
from app.services.shadow_store_interface import IShadowStore


def _minimal_context() -> ShadowExecutionContext:
    return ShadowExecutionContext(
        symbol="RELIANCE-EQ",
        candles=[
            OHLCVPoint(
                timestamp=datetime(2023, 1, 1),
                open=100.0,
                high=105.0,
                low=95.0,
                close=101.0,
                volume=1000,
            )
        ],
        technical_results=[
            TechnicalAnalysisResult(
                mode=AnalysisMode.swing,
                signal="BUY",
                score=70.0,
                indicators={},
                summary="ok",
            )
        ],
        sentiment_score=0.1,
        production_recommendation=FinalRecommendation(
            action="BUY",
            confidence=0.7,
            score=70.0,
            reasoning=RecommendationReasoning(
                bullets=["b"],
                risk_factors=["r"],
                invalidation_signals=["i"],
            ),
            trade_plans=[],
            summary="ok",
        ),
    )


def test_ishadow_executor_is_abstract() -> None:
    """FR-005: IShadowExecutor cannot be instantiated without implementation."""
    with pytest.raises(TypeError):
        IShadowExecutor()  # type: ignore[abstract]


def test_ishadow_store_is_abstract() -> None:
    """FR-005: IShadowStore cannot be instantiated without implementation."""
    with pytest.raises(TypeError):
        IShadowStore()  # type: ignore[abstract]


@pytest.mark.asyncio
async def test_concrete_executor_stub_implements_contract() -> None:
    """Contract: a minimal concrete executor satisfies execute_shadow."""

    class StubExecutor(IShadowExecutor):
        async def execute_shadow(self, context: ShadowExecutionContext) -> ShadowExecutionResult:
            return ShadowExecutionResult(
                ruleset_name="experimental_v1",
                score=context.production_recommendation.score - 1.0,
                action="WATCH",
                reasoning=["stub"],
            )

    ctx = _minimal_context()
    result = await StubExecutor().execute_shadow(ctx)
    assert isinstance(result, ShadowExecutionResult)
    assert result.action == "WATCH"
    assert result.ruleset_name == "experimental_v1"
    # Production context is still intact after stub execution.
    assert ctx.production_recommendation.action == "BUY"


@pytest.mark.asyncio
async def test_concrete_store_stub_implements_contract() -> None:
    """Contract: a minimal concrete store satisfies save_comparison."""
    saved: list[ShadowComparisonLog] = []

    class StubStore(IShadowStore):
        async def save_comparison(self, comparison: ShadowComparisonLog) -> None:
            saved.append(comparison)

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
    await StubStore().save_comparison(log)
    assert len(saved) == 1
    assert saved[0].is_mismatch is True


def test_executor_missing_method_still_abstract() -> None:
    """Failure: incomplete subclass remains abstract and cannot instantiate."""

    class Incomplete(IShadowExecutor):
        pass

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_store_missing_method_still_abstract() -> None:
    """Failure: incomplete store subclass remains abstract."""

    class Incomplete(IShadowStore):
        pass

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]
