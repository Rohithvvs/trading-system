"""Unit: Decision Object builder + trade guidance from production (FR-004, FR-015)."""

from types import SimpleNamespace

from app.services.re001.context import build_lab_context
from app.services.re001.decision_builder import build_decision_object


class _Bull:
    market_state = "FAVORABLE"
    trend_state = "BULLISH"
    new_entry_allowed = True


def test_builder_stamps_engine_identity():
    ctx = build_lab_context(symbol="ABC", market_regime=_Bull(), scan_run_id="scan-1")
    result = {
        "recommendation_state": "REJECT",
        "market_regime": "Bull",
        "confidence_score": 0.2,
        "strategy_family": None,
        "strategy_name": None,
        "reason_codes": ["no_primary_strategy"],
        "evidence": {},
        "explanation": "none",
        "portfolio_decision": {"status": "ok"},
        "risk_profile": {},
        "primary_strategy": None,
        "supporting_strategies": [],
        "rejected_strategies": [],
        "evaluation_status": "rejected_by_rules",
    }
    obj = build_decision_object(ctx, result)
    assert obj.engine_id == "RE-001"
    assert obj.engine_version
    assert obj.symbol == "ABC"
    assert obj.scan_run_id == "scan-1"
    assert obj.recommendation_state == "REJECT"


def test_builder_copies_complete_production_trade_guidance():
    plan = SimpleNamespace(
        entry_low=100.0,
        entry_high=102.0,
        stop_loss=95.0,
        target_1=110.0,
        risk_reward_ratio=1.5,
    )
    prod = SimpleNamespace(action="BUY", score=78.0, trade_plans=[plan])
    ctx = build_lab_context(
        symbol="XYZ",
        market_regime=_Bull(),
        production_recommendation=prod,
    )
    result = {
        "recommendation_state": "WATCH",
        "market_regime": "Bull",
        "confidence_score": 0.6,
        "strategy_family": "Trend Following",
        "strategy_name": "Trend Following",
        "reason_codes": [],
        "evidence": {},
        "explanation": "watch",
        "portfolio_decision": {},
        "risk_profile": {},
        "primary_strategy": "Trend Following",
        "supporting_strategies": [],
        "rejected_strategies": [],
        "evaluation_status": "success",
    }
    obj = build_decision_object(ctx, result)
    assert obj.trade_guidance is not None
    assert obj.trade_guidance.complete is True
    assert obj.production_action == "BUY"
    assert obj.is_mismatch is True  # BUY vs WATCH


def test_missing_market_reason_forces_reject_even_if_engine_said_buy():
    ctx = build_lab_context(symbol="Z", market_regime=None)
    result = {
        "recommendation_state": "BUY",
        "market_regime": "UNKNOWN",
        "confidence_score": 0.9,
        "strategy_family": "Trend Following",
        "strategy_name": "Trend Following",
        "reason_codes": ["missing_market_context"],
        "evidence": {},
        "explanation": "bad",
        "portfolio_decision": {},
        "risk_profile": {},
        "primary_strategy": "Trend Following",
        "supporting_strategies": [],
        "rejected_strategies": [],
        "evaluation_status": "success",
    }
    obj = build_decision_object(ctx, result)
    assert obj.recommendation_state == "REJECT"
