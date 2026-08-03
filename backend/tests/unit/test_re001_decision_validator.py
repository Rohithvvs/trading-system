from app.schemas.re001 import Re001DecisionObject
from app.services.re001.decision_validator import coerce_state_for_reasons, validate_decision_object


def test_valid_reject_object():
    obj = Re001DecisionObject(
        recommendation_id="r1",
        recommendation_state="REJECT",
        confidence_score=0.1,
        reason_codes=["missing_market_context"],
        market_regime="UNKNOWN",
        explanation="missing",
        evidence={"x": 1},
    )
    ok, errs = validate_decision_object(obj)
    assert ok, errs


def test_buy_with_missing_regime_invalid():
    obj = Re001DecisionObject(
        recommendation_id="r2",
        recommendation_state="BUY",
        confidence_score=0.8,
        strategy_name="Trend Following",
        strategy_family="Trend Following",
        reason_codes=["missing_market_context"],
        market_regime="UNKNOWN",
        explanation="bad",
        evidence={"x": 1},
    )
    ok, errs = validate_decision_object(obj)
    assert not ok
    assert any("missing_market" in e or "unknown_regime" in e for e in errs)


def test_coerce_missing_market_to_reject():
    assert coerce_state_for_reasons("BUY", ["missing_market_context"]) == "REJECT"


def test_coerce_portfolio_buy_to_watch():
    assert coerce_state_for_reasons("BUY", ["portfolio_context_unavailable"]) == "WATCH"
