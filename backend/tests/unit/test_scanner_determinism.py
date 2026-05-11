from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.agents.orchestrator_agent import OrchestratorAgent
from backend.app.schemas import (
    FullAnalysisResponse,
    RankingsResponse,
    ScreenerConditionResult,
    ScreenerRequest,
)
from backend.app.services.ranking_service import RankingService
from backend.app.services.screener_service import ScreenerService


def _screen_result(symbol: str, score: float) -> ScreenerConditionResult:
    return ScreenerConditionResult(
        symbol=symbol,
        close=100.0,
        ema_20=99.0,
        sma_30=98.0,
        sma_50=97.0,
        sma_100=96.0,
        sma_200=95.0,
        macd=1.0,
        macd_signal=0.5,
        supertrend=94.0,
        volume=100000,
        previous_volume=90000,
        screener_score=score,
        technical_signal="bullish",
        technical_score=80.0,
        candles_fetched=260,
        conditions={"broad_trend_eligibility": True},
        matched=True,
    )


@pytest.mark.unit
def test_screener_results_are_stable_across_repeated_runs(monkeypatch):
    service = ScreenerService()
    scores = {"TCS-EQ": 82.0, "INFY-EQ": 82.0, "RELIANCE-EQ": 79.0}
    monkeypatch.setattr(
        service,
        "_process_symbol_safe",
        lambda symbol, lookback_window, stage_name: _screen_result(symbol, scores[symbol]),
    )

    first = [item.symbol for item in service.screen_symbols_swing(list(scores), 260, "test")]
    second = [item.symbol for item in service.screen_symbols_swing(list(reversed(scores)), 260, "test")]

    assert first == ["INFY-EQ", "TCS-EQ", "RELIANCE-EQ"]
    assert second == first


@pytest.mark.unit
def test_screener_ignores_future_completion_order(monkeypatch):
    service = ScreenerService()
    scores = {"TCS-EQ": 82.0, "INFY-EQ": 82.0, "RELIANCE-EQ": 79.0}
    monkeypatch.setattr(
        service,
        "_process_symbol_safe",
        lambda symbol, lookback_window, stage_name: _screen_result(symbol, scores[symbol]),
    )
    monkeypatch.setattr(
        "backend.app.services.screener_service.as_completed",
        lambda futures: list(reversed(list(futures))),
    )

    ordered = [item.symbol for item in service.screen_symbols_swing(list(scores), 260, "test")]

    assert ordered == ["INFY-EQ", "TCS-EQ", "RELIANCE-EQ"]


@pytest.mark.unit
def test_shortlist_breaks_equal_screener_scores_by_symbol():
    orchestrator = object.__new__(OrchestratorAgent)
    orchestrator.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    orchestrator.screener_service = SimpleNamespace(
        screen_symbols_swing=lambda symbols, lookback_window, stage_name: [
            _screen_result("TCS-EQ", 82.0),
            _screen_result("INFY-EQ", 82.0),
        ]
    )
    orchestrator.ranking_agent = SimpleNamespace(
        run=lambda items: RankingsResponse(
            rankings=[],
            buy_rankings=[],
            watch_rankings=[],
            best_intraday_candidate=None,
            best_swing_candidate=None,
            disclaimer="test",
        )
    )
    orchestrator.run_full = lambda request: FullAnalysisResponse(
        items=[],
        rankings=orchestrator.ranking_agent.run([]),
        disclaimer="test",
        generated_at=datetime(2026, 5, 17, tzinfo=timezone.utc),
    )
    orchestrator._data_source_label = lambda *args, **kwargs: "test"
    orchestrator._data_warning = lambda: None
    orchestrator._market_context = lambda: {}

    response = orchestrator._run_screener_stage(
        request=ScreenerRequest(top_n=2),
        stage_name="test",
        source_universe=["TCS-EQ", "INFY-EQ"],
        duplicate_symbols_skipped=0,
    )

    assert response.shortlisted_symbols == ["INFY-EQ", "TCS-EQ"]


@pytest.mark.unit
def test_ranking_service_breaks_score_ties_by_symbol():
    service = RankingService()
    items = [
        SimpleNamespace(
            symbol="TCS-EQ",
            recommendation=SimpleNamespace(score=80.0, action="BUY"),
            technical=[SimpleNamespace(mode=SimpleNamespace(value="swing"))],
        ),
        SimpleNamespace(
            symbol="INFY-EQ",
            recommendation=SimpleNamespace(score=80.0, action="BUY"),
            technical=[SimpleNamespace(mode=SimpleNamespace(value="swing"))],
        ),
    ]

    rankings = service.rank(items)

    assert [item.symbol for item in rankings.rankings] == ["INFY-EQ", "TCS-EQ"]
    assert rankings.best_swing_candidate == "INFY-EQ"
