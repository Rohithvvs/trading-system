"""Integration tests for FEAT-011 Spec 1 shadow orchestrator hook.

Spec source: specs/006-shadow-infra-foundation/spec.md
  - Insertion point: OrchestratorAgent._analyze_symbol_post_bulk
  - FR-005 / FR-006: no production scoring or API response mutation
  - Exception-safe envelope: shadow failures degrade gracefully
"""
from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents import orchestrator_agent as orchestrator_module
from app.agents.orchestrator_agent import OrchestratorAgent
from app.config import settings
from app.schemas.analysis import (
    AnalysisMode,
    AnalysisRequest,
    BacktestResult,
    FinalRecommendation,
    MarketRegimeResult,
    OHLCVPoint,
    RecommendationReasoning,
    ShadowExecutionContext,
    ShadowExecutionResult,
    TechnicalAnalysisResult,
)
from app.services.shadow_executor_interface import IShadowExecutor


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _build_request(symbol: str = "RELIANCE-EQ") -> AnalysisRequest:
    return AnalysisRequest(symbols=[symbol], mode=AnalysisMode.swing)


def _candles(n: int = 5) -> list[OHLCVPoint]:
    base = datetime.datetime(2023, 1, 1)
    return [
        OHLCVPoint(
            timestamp=base + datetime.timedelta(days=i),
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=1000,
        )
        for i in range(n)
    ]


def _market_regime() -> MarketRegimeResult:
    return MarketRegimeResult(
        market_state="FAVORABLE",
        trend_state="BULLISH",
        breadth_state="HEALTHY",
        volatility_state="NORMAL",
        data_quality_flags={},
        reasons=[],
        new_entry_allowed=True,
        risk_multiplier=1.0,
        manual_review_flag=False,
    )


def _wire_agent_mocks(orchestrator: OrchestratorAgent) -> FinalRecommendation:
    orchestrator.news_agent = MagicMock()
    orchestrator.news_agent.run.return_value = ([], 0.5, "NEUTRAL", "No recent news found")

    orchestrator.backtest_agent = MagicMock()
    orchestrator.backtest_agent.run.return_value = BacktestResult(
        mode=AnalysisMode.swing,
        strategy_name="test_strat",
        total_return=15.0,
        max_drawdown=5.0,
        win_rate=0.6,
        profit_factor=1.5,
        trade_count=10,
        verdict="PASSED",
        equity_curve=[],
    )

    orchestrator.fundamental_agent = MagicMock()
    orchestrator.fundamental_agent.run.return_value = None

    reasoning = RecommendationReasoning(
        bullets=["Test bullet"],
        risk_factors=["Test risk"],
        invalidation_signals=["Test invalidation"],
    )
    recommendation = FinalRecommendation(
        action="BUY",
        confidence=0.8,
        score=75.0,
        reasoning=reasoning,
        trade_plans=[],
        summary="Test summary",
    )
    orchestrator.recommendation_agent = MagicMock()
    orchestrator.recommendation_agent.run.return_value = recommendation
    orchestrator._persist_analysis = AsyncMock()
    return recommendation


async def _run_post_bulk(
    orchestrator: OrchestratorAgent,
    *,
    symbol: str = "RELIANCE-EQ",
):
    candles = _candles()
    tech_res = TechnicalAnalysisResult(
        mode=AnalysisMode.swing,
        signal="BUY",
        score=75.0,
        indicators={"rsi": 60.0},
        summary="Test summary",
    )
    return await orchestrator._analyze_symbol_post_bulk(
        symbol=symbol,
        request=_build_request(symbol),
        candles_by_mode={AnalysisMode.swing: candles},
        bulk_technical_results={AnalysisMode.swing: {symbol: tech_res}},
        feat004_config={},
        benchmark_ohlcv=None,
        benchmark_failure_reason=None,
        benchmark_symbol=None,
        feat007_config={},
        stock_id=1,
        market_regime=_market_regime(),
    )


# ===========================================================================
# Happy / graceful paths
# ===========================================================================


def _enable_shadow_hook(monkeypatch, *, stage: str = "SHADOW") -> None:
    monkeypatch.setattr(settings, "shadow_mode_enabled", True)
    monkeypatch.setattr(settings, "shadow_mode_stage", stage)
    monkeypatch.setattr(settings, "shadow_mode_ruleset", "experimental_v1")
    # Candidate features submit to ShadowThreadPool after persist; stub so tests
    # do not spawn background DB retries against the non-test SessionLocal.
    monkeypatch.setattr(
        "app.services.shadow_executor.ShadowThreadPool.submit_task",
        MagicMock(return_value=None),
    )


def _capture_shadow_logger(monkeypatch) -> tuple[list[str], list[str]]:
    info_logs: list[str] = []
    warning_logs: list[str] = []
    mock = MagicMock()
    mock.info = lambda msg, *args, **kwargs: info_logs.append(msg % args if args else msg)
    mock.warning = lambda msg, *args, **kwargs: warning_logs.append(
        msg % args if args else msg
    )
    monkeypatch.setattr(orchestrator_module, "shadow_logger", mock)
    return info_logs, warning_logs


@pytest.mark.asyncio
async def test_shadow_mode_orchestrator_hook_graceful_degradation(
    db_session, monkeypatch
) -> None:
    """Enabled + no registered executor → warning, production still succeeds."""
    _enable_shadow_hook(monkeypatch)

    orchestrator = OrchestratorAgent(db_session)
    _wire_agent_mocks(orchestrator)
    _, warning_logs = _capture_shadow_logger(monkeypatch)

    result = await _run_post_bulk(orchestrator)

    assert result.symbol == "RELIANCE-EQ"
    assert result.recommendation is not None
    assert any("no ruleset executor is registered" in log for log in warning_logs)


@pytest.mark.asyncio
async def test_shadow_disabled_skips_executor_entirely(
    db_session, monkeypatch
) -> None:
    """FR-006: When shadow_mode_enabled=False, executor is never invoked."""
    monkeypatch.setattr(settings, "shadow_mode_enabled", False)
    monkeypatch.setattr(settings, "shadow_mode_stage", "SHADOW")

    orchestrator = OrchestratorAgent(db_session)
    _wire_agent_mocks(orchestrator)

    class TrackingExecutor(IShadowExecutor):
        def __init__(self) -> None:
            self.calls = 0

        async def execute_shadow(self, context: ShadowExecutionContext) -> ShadowExecutionResult:
            self.calls += 1
            return ShadowExecutionResult(
                ruleset_name="experimental_v1",
                score=1.0,
                action="REJECT",
            )

    tracker = TrackingExecutor()
    orchestrator.shadow_executor = tracker
    _capture_shadow_logger(monkeypatch)

    result = await _run_post_bulk(orchestrator)

    assert tracker.calls == 0
    assert result.recommendation.action in {"BUY", "WATCH", "REJECT"}


@pytest.mark.asyncio
async def test_shadow_stage_off_skips_executor_even_when_enabled(
    db_session, monkeypatch
) -> None:
    """M3: stage OFF disables the hook even if master toggle is True."""
    _enable_shadow_hook(monkeypatch, stage="OFF")

    orchestrator = OrchestratorAgent(db_session)
    _wire_agent_mocks(orchestrator)

    class TrackingExecutor(IShadowExecutor):
        def __init__(self) -> None:
            self.calls = 0

        async def execute_shadow(self, context: ShadowExecutionContext) -> ShadowExecutionResult:
            self.calls += 1
            return ShadowExecutionResult(
                ruleset_name="experimental_v1",
                score=1.0,
                action="REJECT",
            )

    tracker = TrackingExecutor()
    orchestrator.shadow_executor = tracker
    info_logs, warning_logs = _capture_shadow_logger(monkeypatch)

    await _run_post_bulk(orchestrator)

    assert tracker.calls == 0
    assert info_logs == []
    assert warning_logs == []


@pytest.mark.asyncio
async def test_shadow_enabled_invokes_registered_executor(
    db_session, monkeypatch
) -> None:
    """Integration: registered executor receives context and production continues."""
    _enable_shadow_hook(monkeypatch)

    orchestrator = OrchestratorAgent(db_session)
    _wire_agent_mocks(orchestrator)

    captured: list[ShadowExecutionContext] = []

    class CapturingExecutor(IShadowExecutor):
        async def execute_shadow(self, context: ShadowExecutionContext) -> ShadowExecutionResult:
            captured.append(context)
            return ShadowExecutionResult(
                ruleset_name="experimental_v1",
                score=10.0,
                action="REJECT",
                reasoning=["experimental stub"],
            )

    orchestrator.shadow_executor = CapturingExecutor()
    info_logs, _ = _capture_shadow_logger(monkeypatch)

    result = await _run_post_bulk(orchestrator)

    assert len(captured) == 1
    ctx = captured[0]
    assert ctx.symbol == "RELIANCE-EQ"
    assert len(ctx.candles) == 5
    assert ctx.production_recommendation is not None
    assert any("Shadow execution succeeded" in log for log in info_logs)

    # FR-005 / FR-006: client-facing result must not expose shadow fields or swap action
    dumped = result.model_dump()
    assert "shadow_action" not in dumped
    assert "shadow_score" not in dumped
    assert "shadow_comparison" not in dumped
    # Executor returned REJECT; production path must not adopt that action.
    assert result.recommendation.action != "REJECT" or ctx.production_recommendation.action == "REJECT"


@pytest.mark.asyncio
async def test_shadow_executor_exception_does_not_fail_production(
    db_session, monkeypatch
) -> None:
    """Failure path: executor exception is swallowed; production result returns."""
    _enable_shadow_hook(monkeypatch)

    orchestrator = OrchestratorAgent(db_session)
    _wire_agent_mocks(orchestrator)

    class ExplodingExecutor(IShadowExecutor):
        async def execute_shadow(self, context: ShadowExecutionContext) -> ShadowExecutionResult:
            raise RuntimeError("shadow boom")

    orchestrator.shadow_executor = ExplodingExecutor()
    _, warning_logs = _capture_shadow_logger(monkeypatch)

    result = await _run_post_bulk(orchestrator)

    assert result.symbol == "RELIANCE-EQ"
    assert result.recommendation is not None
    assert any("Shadow mode hook failed with exception" in log for log in warning_logs)
    assert any("shadow boom" in log for log in warning_logs)


@pytest.mark.asyncio
async def test_shadow_return_value_does_not_replace_production_action(
    db_session, monkeypatch
) -> None:
    """FR-006: ShadowExecutionResult.action is not written into the API recommendation."""
    _enable_shadow_hook(monkeypatch)

    orchestrator = OrchestratorAgent(db_session)
    _wire_agent_mocks(orchestrator)

    class NonMutatingExecutor(IShadowExecutor):
        async def execute_shadow(self, context: ShadowExecutionContext) -> ShadowExecutionResult:
            assert context.production_recommendation is not None
            return ShadowExecutionResult(
                ruleset_name="experimental_v1",
                score=0.0,
                action="REJECT",
            )

    orchestrator.shadow_executor = NonMutatingExecutor()
    _capture_shadow_logger(monkeypatch)

    result = await _run_post_bulk(orchestrator)

    # Production pipeline mock returns BUY; overlays may downgrade to WATCH only.
    assert result.recommendation.action != "REJECT"
    assert result.recommendation.score != 0.0


@pytest.mark.asyncio
async def test_shadow_mutating_recommendation_does_not_leak_to_production(
    db_session, monkeypatch
) -> None:
    """FR-007: production_recommendation is deep-copied into the shadow context."""
    _enable_shadow_hook(monkeypatch)

    orchestrator = OrchestratorAgent(db_session)
    _wire_agent_mocks(orchestrator)

    class MutatingExecutor(IShadowExecutor):
        async def execute_shadow(self, context: ShadowExecutionContext) -> ShadowExecutionResult:
            context.production_recommendation.action = "REJECT"
            context.production_recommendation.score = 0.0
            if context.production_challenger_recommendation is not None:
                context.production_challenger_recommendation.action = "REJECT"
                context.production_challenger_recommendation.score = 0.0
            return ShadowExecutionResult(
                ruleset_name="experimental_v1",
                score=0.0,
                action="REJECT",
            )

    orchestrator.shadow_executor = MutatingExecutor()
    _capture_shadow_logger(monkeypatch)

    result = await _run_post_bulk(orchestrator)

    # Mutations inside the shadow executor must not alter the returned production result.
    assert result.recommendation.action != "REJECT"
    assert result.recommendation.score != 0.0
    if result.challenger_recommendation is not None:
        # Score must not be forced to 0 by shadow mutation of the context copy.
        assert result.challenger_recommendation.score != 0.0


@pytest.mark.asyncio
async def test_shadow_context_built_with_deep_copied_candles(
    db_session, monkeypatch
) -> None:
    """US2 integration: context candles are deep-copied from the production set."""
    _enable_shadow_hook(monkeypatch)

    orchestrator = OrchestratorAgent(db_session)
    _wire_agent_mocks(orchestrator)

    source_candles = _candles()
    captured: list[ShadowExecutionContext] = []

    class CapturingExecutor(IShadowExecutor):
        async def execute_shadow(self, context: ShadowExecutionContext) -> ShadowExecutionResult:
            captured.append(context)
            context.candles[0].close = 0.01
            return ShadowExecutionResult(
                ruleset_name="experimental_v1",
                score=50.0,
                action="WATCH",
            )

    orchestrator.shadow_executor = CapturingExecutor()
    _capture_shadow_logger(monkeypatch)

    symbol = "RELIANCE-EQ"
    tech_res = TechnicalAnalysisResult(
        mode=AnalysisMode.swing,
        signal="BUY",
        score=75.0,
        indicators={"rsi": 60.0},
        summary="Test summary",
    )
    result = await orchestrator._analyze_symbol_post_bulk(
        symbol=symbol,
        request=_build_request(symbol),
        candles_by_mode={AnalysisMode.swing: source_candles},
        bulk_technical_results={AnalysisMode.swing: {symbol: tech_res}},
        feat004_config={},
        benchmark_ohlcv=None,
        benchmark_failure_reason=None,
        benchmark_symbol=None,
        feat007_config={},
        stock_id=1,
        market_regime=_market_regime(),
    )

    assert len(captured) == 1
    # Source production candles remain unchanged after shadow mutation.
    assert source_candles[0].close == 102.0
    assert result.ohlcv[0].close == 102.0


@pytest.mark.asyncio
async def test_persist_analysis_still_called_when_shadow_enabled(
    db_session, monkeypatch
) -> None:
    """Regression: production persistence path is unaffected by shadow hook."""
    _enable_shadow_hook(monkeypatch)

    orchestrator = OrchestratorAgent(db_session)
    _wire_agent_mocks(orchestrator)
    _capture_shadow_logger(monkeypatch)

    await _run_post_bulk(orchestrator)

    orchestrator._persist_analysis.assert_awaited_once()


@pytest.mark.asyncio
async def test_shadow_logger_name_is_app_shadow_executor(
    db_session, monkeypatch, caplog
) -> None:
    """M2: shadow hook messages use the dedicated app.shadow_executor logger."""
    _enable_shadow_hook(monkeypatch)

    orchestrator = OrchestratorAgent(db_session)
    _wire_agent_mocks(orchestrator)

    with caplog.at_level("WARNING", logger="app.shadow_executor"):
        await _run_post_bulk(orchestrator)

    assert any(
        r.name == "app.shadow_executor"
        and "no ruleset executor is registered" in r.getMessage()
        for r in caplog.records
    )
