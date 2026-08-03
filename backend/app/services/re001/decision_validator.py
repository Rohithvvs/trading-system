"""Decision Object completeness and fail-closed rules (FR-004/025/026)."""

from __future__ import annotations

import math
from typing import Any

from ...schemas.re001 import Re001DecisionObject, RecommendationState


ALLOWED_STATES = frozenset({"BUY", "WATCH", "REJECT"})


def validate_decision_object(obj: Re001DecisionObject | dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (ok, errors)."""
    errors: list[str] = []
    if isinstance(obj, Re001DecisionObject):
        data = obj.model_dump()
    else:
        data = obj

    state = str(data.get("recommendation_state") or "")
    if state not in ALLOWED_STATES:
        errors.append("invalid_recommendation_state")

    engine_id = str(data.get("engine_id") or "")
    if engine_id != "RE-001":
        errors.append("invalid_engine_id")

    if not str(data.get("recommendation_id") or "").strip():
        errors.append("missing_recommendation_id")

    if not str(data.get("engine_version") or "").strip():
        errors.append("missing_engine_version")

    try:
        conf = float(data.get("confidence_score"))
        if math.isnan(conf) or math.isinf(conf):
            errors.append("invalid_confidence")
    except (TypeError, ValueError):
        errors.append("invalid_confidence")

    reasons = data.get("reason_codes") or []
    if not isinstance(reasons, list):
        errors.append("invalid_reason_codes")

    if state in {"BUY", "WATCH"}:
        if not data.get("strategy_name") and not data.get("strategy_family"):
            errors.append("missing_primary_strategy")

    if state == "BUY":
        if "missing_market_context" in (reasons or []):
            errors.append("buy_with_missing_market_context")
        if "portfolio_context_unavailable" in (reasons or []):
            errors.append("buy_with_portfolio_unavailable")
        regime = str(data.get("market_regime") or "UNKNOWN")
        if regime == "UNKNOWN":
            errors.append("buy_with_unknown_regime")

    status = str(data.get("evaluation_status") or "success")
    if status in {"error", "timeout"} and state == "BUY":
        errors.append("buy_on_error_status")

    return (len(errors) == 0, errors)


def coerce_state_for_reasons(
    state: RecommendationState,
    reason_codes: list[str],
) -> RecommendationState:
    """Hard fail-closed overrides."""
    if "missing_market_context" in reason_codes:
        return "REJECT"
    if state == "BUY" and "portfolio_context_unavailable" in reason_codes:
        return "WATCH"
    return state
