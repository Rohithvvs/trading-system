"""Regression tests for score-based BUY/WATCH/REJECT classification.

Production signal policy (after full analysis pipeline completes):
  score >= 70 → BUY
  55 <= score < 70 → WATCH
  score < 55 → REJECT

Mandatory preconditions (any failure → REJECT, reason=Analysis Failed):
  - Market data available / OHLC valid / trusted source
  - Score calculated (finite)
  - Confidence calculated (finite)
  - Trade plan with entry, stop loss, target
  - Analysis completed (technical results present)

Informational only (must NOT change final signal):
  Risk:Reward, conviction, AI confidence thresholds, market regime, breakouts.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.agents.orchestrator_agent import OrchestratorAgent, _TRUSTED_OHLCV_SOURCES
from app.schemas import (
    AnalysisMode,
    BacktestResult,
    FinalRecommendation,
    OHLCVPoint,
    RecommendationReasoning,
    TechnicalAnalysisResult,
    TradePlan,
)
from app.services.recommendation_service import (
    ANALYSIS_FAILED_REASON,
    BUY_SCORE_THRESHOLD,
    WATCH_SCORE_THRESHOLD,
    RecommendationService,
    analysis_preconditions_ok,
    classify_signal_from_score,
    is_trade_plan_complete,
)


def _make_candles(n: int = 25, base: float = 100.0) -> list[OHLCVPoint]:
    return [
        OHLCVPoint(
            timestamp=datetime.now(),
            open=base,
            high=base + 5,
            low=base - 1,
            close=base + 4,
            volume=10_000 + i * 10,
        )
        for i in range(n)
    ]


def test_classify_signal_from_score_thresholds():
    """Canonical score → signal mapping (BUY threshold = 70)."""
    cases = [
        (82.0, "BUY"),
        (75.0, "BUY"),
        (71.0, "BUY"),
        (70.0, "BUY"),
        (69.0, "WATCH"),
        (69.99, "WATCH"),
        (63.0, "WATCH"),
        (58.0, "WATCH"),
        (55.0, "WATCH"),
        (54.0, "REJECT"),
        (54.99, "REJECT"),
        (40.0, "REJECT"),
        (0.0, "REJECT"),
        (100.0, "BUY"),
    ]
    for score, expected in cases:
        assert classify_signal_from_score(score) == expected, f"score={score}"
    assert BUY_SCORE_THRESHOLD == 70.0
    assert WATCH_SCORE_THRESHOLD == 55.0


def test_fundamental_neutral_score_mapping():
    """Neutral fundamental 0.0 maps to 50/100 so strong tech can reach BUY (>=70)."""
    rec_service = RecommendationService()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="bullish", score=90.0, indicators={}, summary=""
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing,
        strategy_name="test",
        total_return=15.0,
        cagr=15.0,
        max_drawdown=-5.0,
        win_rate=0.6,
        profit_factor=1.5,
        trade_count=10,
        verdict="favorable",
        equity_curve=[],
    )
    candles = {AnalysisMode.swing: _make_candles(25)}

    res = rec_service.build("TEST_SYM", [tech], 0.0, None, [bt], candles, {})
    assert res.score >= 70.0
    assert res.action == "BUY"
    assert res.trade_plans  # trade plan still generated
    assert is_trade_plan_complete(res.trade_plans[0])


def test_sentiment_neutral_maps_to_mid_score_when_weighted():
    """With news catalyst, neutral sentiment 0.0 must contribute ~50 not 0."""
    rec_service = RecommendationService()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="bullish", score=80.0, indicators={}, summary=""
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing,
        strategy_name="test",
        total_return=10.0,
        cagr=10.0,
        max_drawdown=-5.0,
        win_rate=0.55,
        profit_factor=1.3,
        trade_count=10,
        verdict="favorable",
        equity_curve=[],
    )
    candles = {
        AnalysisMode.swing: [
            OHLCVPoint(
                timestamp=datetime.now(),
                open=100,
                high=105,
                low=99,
                close=104,
                volume=1000 if i < 19 else 5000,
            )
            for i in range(25)
        ]
    }
    res = rec_service.build("TEST_SYM", [tech], 0.0, None, [bt], candles, {})
    assert res.score > 40.0
    assert 0.0 <= res.score <= 100.0


def test_recommendation_build_classifies_by_score_only():
    """build() assigns BUY/WATCH/REJECT purely from composite score thresholds.

    Baseline weights (no catalyst): tech 0.50 | backtest 0.25 | fund 0.25 | news 0.0
    raw_backtest = clamp(total_return * 4, -20, 100)
    raw_fund (neutral 0.0) = 50
    """
    rec_service = RecommendationService()
    candles = {AnalysisMode.swing: _make_candles(25)}

    def _bt(total_return: float, verdict: str = "mixed") -> BacktestResult:
        return BacktestResult(
            mode=AnalysisMode.swing,
            strategy_name="test",
            total_return=total_return,
            cagr=total_return,
            max_drawdown=-5.0,
            win_rate=0.5,
            profit_factor=1.1,
            trade_count=10,
            verdict=verdict,
            equity_curve=[],
        )

    # BUY: tech 90 * 0.5 + (15*4=60)*0.25 + 50*0.25 = 45 + 15 + 12.5 = 72.5
    strong = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="bullish", score=90.0, indicators={}, summary=""
    )
    buy_res = rec_service.build(
        "BUY_SYM", [strong], 0.0, None, [_bt(15.0, "favorable")], candles, {}
    )
    assert buy_res.score >= 70.0
    assert buy_res.action == "BUY"

    # WATCH: tech 75 * 0.5 + (5*4=20)*0.25 + 50*0.25 = 37.5 + 5 + 12.5 = 55.0
    mid = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="bullish", score=75.0, indicators={}, summary=""
    )
    watch_res = rec_service.build(
        "WATCH_SYM", [mid], 0.0, None, [_bt(5.0, "mixed")], candles, {}
    )
    assert 55.0 <= watch_res.score < 70.0
    assert watch_res.action == "WATCH"

    # REJECT: tech 30 * 0.5 + 0 + 50*0.25 = 15 + 12.5 = 27.5
    weak = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="bearish", score=30.0, indicators={}, summary=""
    )
    reject_res = rec_service.build(
        "REJECT_SYM", [weak], 0.0, None, [_bt(0.0, "unfavorable")], candles, {}
    )
    assert reject_res.score < 55.0
    assert reject_res.action == "REJECT"


def test_score_69_is_watch_not_buy():
    """Boundary: 69.x is WATCH under BUY threshold 70."""
    assert classify_signal_from_score(69.0) == "WATCH"
    assert classify_signal_from_score(69.99) == "WATCH"
    assert classify_signal_from_score(70.0) == "BUY"


def _score_rec(
    *,
    score: float,
    action: str | None = None,
    with_plan: bool = True,
    rr: float = 1.0,
    incomplete_plan: bool = False,
    confidence: float | None = None,
) -> FinalRecommendation:
    """Recommendation fixture; action defaults to score-based classification."""
    resolved_action = action or classify_signal_from_score(score)
    plans = []
    if with_plan:
        if incomplete_plan:
            plans = [
                TradePlan(
                    mode=AnalysisMode.swing,
                    strategy_name="t",
                    setup_type="pullback",
                    timeframe="swing",
                    bias="long",
                    entry_low=0.0,
                    entry_high=0.0,
                    stop_loss=0.0,
                    target_1=0.0,
                    target_2=0.0,
                    target_3=0.0,
                    risk_reward_ratio=rr,
                    notes="",
                )
            ]
        else:
            plans = [
                TradePlan(
                    mode=AnalysisMode.swing,
                    strategy_name="t",
                    setup_type="pullback",
                    timeframe="swing",
                    bias="long",
                    entry_low=100.0,
                    entry_high=101.0,
                    stop_loss=95.0,
                    target_1=110.0,
                    target_2=115.0,
                    target_3=120.0,
                    risk_reward_ratio=rr,
                    notes="",
                )
            ]
    conf = confidence if confidence is not None else min(0.95, max(0.35, score / 100))
    return FinalRecommendation(
        action=resolved_action,
        score=score,
        confidence=conf,
        reasoning=RecommendationReasoning(
            bullets=[], risk_factors=[], invalidation_signals=[]
        ),
        trade_plans=plans,
        summary="test rec",
        technical_score=score,
        backtest_score=50.0,
        fundamental_score=50.0,
    )


def _trusted_dq(**overrides) -> dict:
    base = {
        "source": "CANDLE_CACHE_DB",
        "mock_warning": False,
        "minimum_swing_candles_met": True,
        "candles": 250,
    }
    base.update(overrides)
    return base


def test_strict_buy_gate_accepts_candle_cache_db():
    """Trusted CANDLE_CACHE_DB + score >= 70 + complete plan → BUY (no R:R gate)."""
    orch = OrchestratorAgent(db=MagicMock())
    mock_rec = _score_rec(score=80.0, rr=0.5)
    result = orch._enforce_strict_buy_gate(
        symbol="TEST",
        request=MagicMock(),
        recommendation=mock_rec,
        technical_results=[MagicMock(score=80.0)],
        backtests=[MagicMock(verdict="favorable", total_return=15.0, trade_count=10)],
        candles_by_mode={},
        data_quality=_trusted_dq(),
    )
    assert result.action == "BUY"


def test_strict_buy_gate_rejects_true_mock():
    """MOCK_FALLBACK fails mandatory data validation → REJECT Analysis Failed, score cleared."""
    orch = OrchestratorAgent(db=MagicMock())
    mock_rec = _score_rec(score=80.0)
    result = orch._enforce_strict_buy_gate(
        symbol="TEST",
        request=MagicMock(),
        recommendation=mock_rec,
        technical_results=[MagicMock(score=80.0)],
        backtests=[MagicMock(verdict="favorable", total_return=15.0, trade_count=10)],
        candles_by_mode={},
        data_quality={
            "source": "MOCK_FALLBACK",
            "mock_warning": True,
            "minimum_swing_candles_met": True,
            "candles": 250,
        },
    )
    assert result.action == "REJECT"
    assert result.score == 0.0
    assert result.confidence == 0.0
    assert result.trade_plans == []
    assert any(ANALYSIS_FAILED_REASON in r for r in result.reasoning.risk_factors)


def test_unknown_source_with_full_data_allows_buy():
    """Prefetch path: unknown→trusted with candles must NOT wipe a valid composite score."""
    orch = OrchestratorAgent(db=MagicMock())
    rec = _score_rec(score=71.7)
    # Simulate data quality after our payload remap
    result = orch._enforce_strict_buy_gate(
        "PREFETCH_OK",
        MagicMock(),
        rec,
        [MagicMock(score=80.0)],
        [MagicMock(verdict="favorable", total_return=15.0, trade_count=10)],
        {},
        _trusted_dq(source="CANDLE_CACHE_DB"),
    )
    assert result.action == "BUY"
    assert result.score == 71.7
    assert result.trade_plans
    assert result.confidence > 0


def test_data_quality_payload_cache_db_not_mock():
    orch = OrchestratorAgent(db=MagicMock())
    candles = {AnalysisMode.swing: _make_candles(250)}
    request = MagicMock()
    request.timeframe.swing = "1d"

    with patch.object(
        orch.fyers_service, "get_ohlcv_source", return_value="CANDLE_CACHE_DB"
    ):
        dq = orch._data_quality_payload(candles, request, "INFY-EQ")

    assert dq["source"] == "CANDLE_CACHE_DB"
    assert dq["mock_warning"] is False
    assert dq["minimum_swing_candles_met"] is True
    assert dq["source"] in _TRUSTED_OHLCV_SOURCES


def test_data_quality_payload_unknown_with_full_candles_is_trusted():
    """Prefetched shortlist candles often report source=unknown; with ≥220 bars treat as real."""
    orch = OrchestratorAgent(db=MagicMock())
    candles = {AnalysisMode.swing: _make_candles(250)}
    request = MagicMock()
    request.timeframe.swing = "1d"

    with patch.object(orch.fyers_service, "get_ohlcv_source", return_value="unknown"):
        dq = orch._data_quality_payload(candles, request, "EICHERMOT-EQ")

    assert dq["source"] == "CANDLE_CACHE_DB"
    assert dq["mock_warning"] is False
    assert dq["minimum_swing_candles_met"] is True


def test_data_quality_payload_unknown_empty_is_mock():
    orch = OrchestratorAgent(db=MagicMock())
    candles = {AnalysisMode.swing: []}
    request = MagicMock()
    request.timeframe.swing = "1d"

    with patch.object(orch.fyers_service, "get_ohlcv_source", return_value="unknown"):
        dq = orch._data_quality_payload(candles, request, "EMPTY-EQ")

    assert dq["mock_warning"] is True


def test_data_quality_payload_fyers_primary_not_mock():
    orch = OrchestratorAgent(db=MagicMock())
    candles = {AnalysisMode.swing: _make_candles(250)}
    request = MagicMock()
    request.timeframe.swing = "1d"

    with patch.object(
        orch.fyers_service, "get_ohlcv_source", return_value="FYERS_PRIMARY"
    ):
        dq = orch._data_quality_payload(candles, request, "RELIANCE-EQ")

    assert dq["source"] == "FYERS_PRIMARY"
    assert dq["mock_warning"] is False


def test_score_policy_allows_weak_technical_if_score_is_buy():
    """Technical score < 70 must NOT block BUY when composite score >= 70."""
    orch = OrchestratorAgent(db=MagicMock())
    mock_rec = _score_rec(score=73.0)
    result = orch._enforce_strict_buy_gate(
        symbol="WEAKTECH",
        request=MagicMock(),
        recommendation=mock_rec,
        technical_results=[MagicMock(score=65.0)],
        backtests=[MagicMock(verdict="favorable", total_return=15.0, trade_count=10)],
        candles_by_mode={},
        data_quality=_trusted_dq(),
    )
    assert result.action == "BUY"


def test_score_policy_allows_weak_risk_reward():
    """R:R < 1.15 must NOT block BUY under score-based policy."""
    orch = OrchestratorAgent(db=MagicMock())
    weak_rr = _score_rec(score=75.0, rr=0.8)
    out_rr = orch._enforce_strict_buy_gate(
        "WEAK_RR",
        MagicMock(),
        weak_rr,
        [MagicMock(score=75.0)],
        [MagicMock(verdict="favorable", total_return=15.0, trade_count=10)],
        {},
        _trusted_dq(),
    )
    assert out_rr.action == "BUY"


def test_score_policy_rejects_insufficient_candles():
    orch = OrchestratorAgent(db=MagicMock())
    valid_rec = _score_rec(score=80.0)
    out_candles = orch._enforce_strict_buy_gate(
        "FEW_CANDLES",
        MagicMock(),
        valid_rec,
        [MagicMock(score=80.0)],
        [MagicMock(verdict="favorable", total_return=15.0, trade_count=10)],
        {},
        _trusted_dq(minimum_swing_candles_met=False, candles=150),
    )
    assert out_candles.action == "REJECT"
    assert out_candles.score == 0.0
    assert out_candles.trade_plans == []
    assert any(ANALYSIS_FAILED_REASON in r for r in out_candles.reasoning.risk_factors)


def test_score_policy_rejects_missing_trade_plan():
    orch = OrchestratorAgent(db=MagicMock())
    no_plan = _score_rec(score=80.0, with_plan=False)
    result = orch._enforce_strict_buy_gate(
        "NO_PLAN",
        MagicMock(),
        no_plan,
        [MagicMock(score=80.0)],
        [MagicMock(verdict="favorable", total_return=15.0, trade_count=10)],
        {},
        _trusted_dq(),
    )
    assert result.action == "REJECT"
    assert result.score == 0.0
    assert any(ANALYSIS_FAILED_REASON in r for r in result.reasoning.risk_factors)


def test_score_policy_rejects_incomplete_trade_plan():
    """Missing entry/SL/target → REJECT Analysis Failed."""
    orch = OrchestratorAgent(db=MagicMock())
    bad = _score_rec(score=80.0, incomplete_plan=True)
    result = orch._enforce_strict_buy_gate(
        "BAD_PLAN",
        MagicMock(),
        bad,
        [MagicMock(score=80.0)],
        [MagicMock(verdict="favorable", total_return=15.0, trade_count=10)],
        {},
        _trusted_dq(),
    )
    assert result.action == "REJECT"
    assert result.score == 0.0
    assert any(ANALYSIS_FAILED_REASON in r for r in result.reasoning.risk_factors)


def test_score_policy_rejects_missing_analysis():
    """No technical results → Analysis Failed."""
    orch = OrchestratorAgent(db=MagicMock())
    rec = _score_rec(score=80.0)
    result = orch._enforce_strict_buy_gate(
        "NO_TECH",
        MagicMock(),
        rec,
        [],
        [MagicMock(verdict="favorable", total_return=15.0, trade_count=10)],
        {},
        _trusted_dq(),
    )
    assert result.action == "REJECT"
    assert result.score == 0.0


def test_score_policy_watch_and_reject_bands():
    """Gate reclassifies purely by score bands when data + plan are valid."""
    orch = OrchestratorAgent(db=MagicMock())

    for score, expected in [
        (82.0, "BUY"),
        (75.0, "BUY"),
        (71.0, "BUY"),
        (70.0, "BUY"),
        (69.0, "WATCH"),
        (63.0, "WATCH"),
        (58.0, "WATCH"),
        (55.0, "WATCH"),
        (54.0, "REJECT"),
        (40.0, "REJECT"),
    ]:
        out = orch._enforce_strict_buy_gate(
            f"S{score}",
            MagicMock(),
            _score_rec(score=score),
            [MagicMock(score=score)],
            [MagicMock(verdict="mixed", total_return=5.0, trade_count=5)],
            {},
            _trusted_dq(),
        )
        assert out.action == expected, f"score={score} expected={expected} got={out.action}"


def test_analysis_preconditions_helper():
    plan = TradePlan(
        mode=AnalysisMode.swing,
        strategy_name="t",
        setup_type="p",
        timeframe="s",
        bias="long",
        entry_low=100,
        entry_high=101,
        stop_loss=95,
        target_1=110,
        target_2=115,
        target_3=120,
        risk_reward_ratio=1.5,
        notes="",
    )
    ok, reason = analysis_preconditions_ok(
        score=80.0,
        confidence=0.8,
        trade_plans=[plan],
        data_quality=_trusted_dq(),
    )
    assert ok and reason == ""

    bad, reason2 = analysis_preconditions_ok(
        score=80.0,
        confidence=0.8,
        trade_plans=[],
        data_quality=_trusted_dq(),
    )
    assert not bad and reason2 == ANALYSIS_FAILED_REASON


def test_recommendation_stores_component_scores():
    rec_service = RecommendationService()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="bullish", score=90.0, indicators={}, summary=""
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing,
        strategy_name="test",
        total_return=15.0,
        cagr=15.0,
        max_drawdown=-5.0,
        win_rate=0.6,
        profit_factor=1.5,
        trade_count=10,
        verdict="favorable",
        equity_curve=[],
    )
    res = rec_service.build(
        "TEST_SYM", [tech], 0.0, None, [bt], {AnalysisMode.swing: _make_candles(25)}, {}
    )
    assert res.technical_score == 90.0
    assert res.backtest_score is not None and res.backtest_score > 0
    assert res.fundamental_score == 50.0


def test_trade_plan_risk_reward_varies_with_structure():
    """R:R is still calculated for UI/display; does not drive signal."""
    rec_service = RecommendationService()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="bullish", score=85.0, indicators={}, summary=""
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing,
        strategy_name="test",
        total_return=12.0,
        cagr=12.0,
        max_drawdown=-4.0,
        win_rate=0.6,
        profit_factor=1.4,
        trade_count=12,
        verdict="favorable",
        equity_curve=[],
    )

    wide = [
        OHLCVPoint(
            timestamp=datetime.now(),
            open=100 + i,
            high=110 + i,
            low=90 + i,
            close=105 + i,
            volume=10000,
        )
        for i in range(25)
    ]
    tight = [
        OHLCVPoint(
            timestamp=datetime.now(),
            open=200.0,
            high=201.0,
            low=199.5,
            close=200.5,
            volume=10000,
        )
        for i in range(25)
    ]

    r_wide = rec_service.build(
        "WIDE", [tech], 0.0, None, [bt], {AnalysisMode.swing: wide}, {}
    )
    r_tight = rec_service.build(
        "TIGHT", [tech], 0.0, None, [bt], {AnalysisMode.swing: tight}, {}
    )
    assert r_wide.trade_plans and r_tight.trade_plans
    assert r_wide.trade_plans[0].risk_reward_ratio > 0
    assert r_tight.trade_plans[0].risk_reward_ratio > 0


def test_feat004_active_does_not_override_production_action():
    """FEAT-004 telemetry must not change production action."""
    rec_service = RecommendationService()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="bullish", score=90.0, indicators={}, summary=""
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing,
        strategy_name="test",
        total_return=15.0,
        cagr=15.0,
        max_drawdown=-5.0,
        win_rate=0.6,
        profit_factor=1.5,
        trade_count=10,
        verdict="favorable",
        equity_curve=[],
    )
    feat004_config = {
        "enabled": True,
        "stage": "ACTIVE",
        "score_deltas": {"FAV": 2.0, "NEU": 0.0, "CAU": -10.0, "DEF": -15.0, "ABS": 0.0},
        "buy_downgrade_thresholds": {"CAU": 74.0, "DEF": 77.0},
        "buy_threshold": 70.0,
        "favorable_cap_below_buy": True,
        "sector_mapping_enabled": False,
        "sector_min_candles": 50,
    }
    res = rec_service.build(
        "FEAT004_SYM",
        [tech],
        0.0,
        None,
        [bt],
        {AnalysisMode.swing: _make_candles(25)},
        {},
        feat004_config=feat004_config,
        benchmark_ohlcv=None,
        benchmark_failure_reason="no_benchmark_for_test",
    )
    assert res.score >= 70.0
    assert res.action == "BUY"
