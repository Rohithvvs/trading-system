"""RecommendationState is set only by deterministic engine path."""

from app.services.re001.context import build_lab_context
from app.services.re001.decision_builder import build_decision_object
from app.services.re001.engine import evaluate_re001


class _MR:
    market_state = "DEFENSIVE"
    trend_state = "BEARISH"
    new_entry_allowed = False


def test_same_inputs_same_state():
    ctx = build_lab_context(symbol="X", market_regime=_MR())
    r1 = evaluate_re001(ctx)
    r2 = evaluate_re001(ctx)
    assert r1["recommendation_state"] == r2["recommendation_state"]
    assert r1["recommendation_state"] == "REJECT"


def test_builder_does_not_use_llm_for_state():
    ctx = build_lab_context(symbol="X", market_regime=_MR())
    result = evaluate_re001(ctx)
    # Inject misleading LLM-like explanation — state must remain engine result
    result["explanation"] = "LLM says BUY now"
    obj = build_decision_object(ctx, result)
    assert obj.recommendation_state == "REJECT"
