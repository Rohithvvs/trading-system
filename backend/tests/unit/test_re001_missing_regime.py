"""US1: missing market regime → REJECT + missing_market_context."""

from app.services.re001.context import build_lab_context
from app.services.re001.engine import evaluate_re001


def test_missing_regime_rejects():
    ctx = build_lab_context(symbol="TEST", candles=[], technical_results=[], market_regime=None)
    result = evaluate_re001(ctx)
    assert result["recommendation_state"] == "REJECT"
    assert "missing_market_context" in result["reason_codes"]
    assert result["market_regime"] == "UNKNOWN"
