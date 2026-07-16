"""
FEAT-007 Batch 2 regression — R21 (complete logging schema) + R22 (explanation template).

R21: Verifies every mandatory FEAT-007 §11.2 log field exists and carries
     the correct value, including the three previously-missing fields:
     sector_index_symbol, sector_roc20, benchmark_roc20.

R22: Verifies the explanation string matches the FEAT-007 §11.3 template
     for STRENGTH, WEAK (with and without downgrade), and UNKNOWN states.

Scope: R21 and R22 only. No scoring, classification, SHADOW/ACTIVE logic,
FEAT-004, FEAT-008, or orchestrator flow is exercised or changed here.
"""
from __future__ import annotations

import json

from app.services.recommendation_service import RecommendationService


# ---------------------------------------------------------------------------
# Mandatory log fields per FEAT-007 spec §11.2
# ---------------------------------------------------------------------------
REQUIRED_LOG_KEYS = {
    "feat007_enabled",
    "feat007_stage",
    "sector_regime_state",
    "sector_index_symbol",
    "sector_roc20",
    "benchmark_roc20",
    "sector_rs_value",
    "feat007_pre_adjustment_score",
    "feat007_score_adjustment",
    "feat007_post_adjustment_score",
    "feat007_watch_downgrade_applied",
    "feat007_abstained_reason",
    "feat007_explanation",
    "feat007_adjusted_label",
}

_CFG = {"enabled": True, "stage": "ACTIVE"}


def _overlay(**kwargs):
    """Call _apply_feat007_overlay with defaults; override via kwargs."""
    defaults = dict(
        composite_score=80.0,
        current_label="BUY",
        symbol="TEST",
        sector_rs_value=5.0,
        feat007_config=_CFG,
        sector_index_symbol="NIFTYIT",
        sector_roc20=4.8,
        benchmark_roc20=3.8,
    )
    defaults.update(kwargs)
    svc = RecommendationService()
    return svc._apply_feat007_overlay(**defaults)


# ===========================================================================
# R21 — Complete FEAT-007 logging schema
# ===========================================================================

def test_r21_all_mandatory_fields_present_strength():
    """Every §11.2 field must exist in the STRENGTH success-path dict."""
    log = _overlay(sector_rs_value=5.0)
    missing = REQUIRED_LOG_KEYS - set(log.keys())
    assert not missing, f"Missing R21 fields: {missing}"


def test_r21_all_mandatory_fields_present_weak():
    """Every §11.2 field must exist in the WEAK success-path dict."""
    log = _overlay(sector_rs_value=-5.0)
    missing = REQUIRED_LOG_KEYS - set(log.keys())
    assert not missing, f"Missing R21 fields: {missing}"


def test_r21_all_mandatory_fields_present_unknown():
    """Every §11.2 field must exist in the UNKNOWN abstain-path dict."""
    log = _overlay(sector_rs_value=None)
    missing = REQUIRED_LOG_KEYS - set(log.keys())
    assert not missing, f"Missing R21 fields: {missing}"


def test_r21_all_mandatory_fields_present_exception():
    """Every §11.2 field must exist in the exception-path dict."""
    log = _overlay(sector_rs_value=object())
    missing = REQUIRED_LOG_KEYS - set(log.keys())
    assert not missing, f"Missing R21 fields: {missing}"


def test_r21_sector_index_symbol_populated_strength():
    log = _overlay(sector_rs_value=5.0, sector_index_symbol="NIFTYIT")
    assert log["sector_index_symbol"] == "NIFTYIT"


def test_r21_sector_roc20_populated_strength():
    log = _overlay(sector_rs_value=5.0, sector_roc20=4.8)
    assert log["sector_roc20"] == 4.8


def test_r21_benchmark_roc20_populated_strength():
    log = _overlay(sector_rs_value=5.0, benchmark_roc20=3.8)
    assert log["benchmark_roc20"] == 3.8


def test_r21_metadata_none_when_abstained():
    """When sector_rs_value is None, the three new fields must be None."""
    log = _overlay(sector_rs_value=None)
    assert log["sector_index_symbol"] is None
    assert log["sector_roc20"] is None
    assert log["benchmark_roc20"] is None


def test_r21_metadata_none_on_exception():
    """On exception, the three new fields must be None."""
    log = _overlay(sector_rs_value=object())
    assert log["sector_index_symbol"] is None
    assert log["sector_roc20"] is None
    assert log["benchmark_roc20"] is None


def test_r21_metadata_values_reused_not_recomputed():
    """The overlay must reuse the values passed in, not recompute them."""
    log = _overlay(
        sector_rs_value=2.5,
        sector_index_symbol="NIFTYMETAL",
        sector_roc20=1.0,
        benchmark_roc20=4.0,
    )
    assert log["sector_rs_value"] == 2.5
    assert log["sector_index_symbol"] == "NIFTYMETAL"
    assert log["sector_roc20"] == 1.0
    assert log["benchmark_roc20"] == 4.0


def test_r21_serialization_includes_new_fields():
    """model_dump must carry the three new schema fields."""
    from app.agents.recommendation_agent import RecommendationAgent
    from app.schemas.analysis import (
        AnalysisMode, BacktestResult, TechnicalAnalysisResult,
    )

    agent = RecommendationAgent()
    tech = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, signal="buy", score=100.0,
        indicators={}, summary="test",
    )
    bt = BacktestResult(
        mode=AnalysisMode.swing, strategy_name="test", total_return=28.0,
        max_drawdown=5.0, win_rate=60.0, profit_factor=2.0,
        trade_count=8, verdict="favorable",
        equity_curve=[{"label": "Start", "equity": 100000.0}],
    )
    result = agent.run(
        symbol="TEST",
        technical_results=[tech],
        sentiment_label="positive",
        sentiment_score=0.0,
        fundamental_result=None,
        backtests=[bt],
        candles_by_mode={AnalysisMode.swing: []},
        feat007_config={"enabled": True, "stage": "ACTIVE"},
        sector_rs_value=5.0,
        sector_index_symbol="NIFTYIT",
        sector_roc20=4.8,
        benchmark_roc20=3.8,
    )
    dumped = result.model_dump(mode="json")
    assert dumped["sector_index_symbol"] == "NIFTYIT"
    assert dumped["sector_roc20"] == 4.8
    assert dumped["benchmark_roc20"] == 3.8
    # JSON round-trip
    json_str = json.dumps(dumped)
    parsed = json.loads(json_str)
    assert parsed["sector_index_symbol"] == "NIFTYIT"
    assert parsed["sector_roc20"] == 4.8
    assert parsed["benchmark_roc20"] == 3.8


# ===========================================================================
# R22 — Explanation template matches spec §11.3
# ===========================================================================

def test_r22_explanation_strength_matches_spec():
    """STRENGTH explanation must match §11.3 template:
    'Sector: {sector} — STRENGTH vs Nifty 500 (RS +X.X pp, sector ROC20 +X.X% vs benchmark +X.X%). Score adjusted by +X.X (XX.X → XX.X).'
    """
    log = _overlay(
        composite_score=79.0,
        sector_rs_value=1.0,
        sector_index_symbol="IT",
        sector_roc20=4.8,
        benchmark_roc20=3.8,
    )
    expected = (
        "Sector: IT — STRENGTH vs Nifty 500 "
        "(RS +1.0 pp, sector ROC20 +4.8% vs benchmark +3.8%). "
        "Score adjusted by +1.5 (79.0 → 80.5)."
    )
    assert log["feat007_explanation"] == expected


def test_r22_explanation_weak_matches_spec_with_downgrade():
    """WEAK explanation with downgrade must match §11.3 template:
    'Sector: {sector} — WEAK vs Nifty 500 (RS -X.X pp, ...). Score adjusted by -X.X (XX.X → XX.X). BUY downgraded to WATCH.'
    """
    log = _overlay(
        composite_score=76.0,
        current_label="BUY",
        sector_rs_value=-3.0,
        sector_index_symbol="METAL",
        sector_roc20=1.0,
        benchmark_roc20=4.0,
    )
    expected = (
        "Sector: METAL — WEAK vs Nifty 500 "
        "(RS -3.0 pp, sector ROC20 +1.0% vs benchmark +4.0%). "
        "Score adjusted by -3.0 (76.0 → 73.0). BUY downgraded to WATCH."
    )
    assert log["feat007_explanation"] == expected


def test_r22_explanation_weak_no_downgrade():
    """WEAK without downgrade must NOT append the downgrade suffix."""
    log = _overlay(
        composite_score=80.0,
        current_label="BUY",
        sector_rs_value=-1.0,
        sector_index_symbol="IT",
        sector_roc20=3.0,
        benchmark_roc20=4.0,
    )
    # 80 + (-3.0) = 77.0 >= 74 threshold → no downgrade
    assert "BUY downgraded to WATCH" not in log["feat007_explanation"]
    assert "WEAK vs Nifty 500" in log["feat007_explanation"]


def test_r22_explanation_unknown_matches_spec():
    """UNKNOWN explanation must match §11.3 template:
    'Sector: UNKNOWN (no sector mapping for {symbol}). No adjustment applied.'
    """
    log = _overlay(sector_rs_value=None, symbol="RELIANCE")
    expected = "Sector: UNKNOWN (no sector mapping for RELIANCE). No adjustment applied."
    assert log["feat007_explanation"] == expected


def test_r22_explanation_shadow_uses_spec_template():
    """SHADOW mode must use the same §11.3 template (calculated but not applied)."""
    log = _overlay(
        composite_score=80.0,
        current_label="BUY",
        sector_rs_value=5.0,
        sector_index_symbol="IT",
        sector_roc20=4.8,
        benchmark_roc20=3.8,
        feat007_config={"enabled": True, "stage": "SHADOW"},
    )
    assert "Sector: IT — STRENGTH vs Nifty 500" in log["feat007_explanation"]
    assert "Score adjusted by +1.5" in log["feat007_explanation"]


# ===========================================================================
# Behavioral unchanged — SHADOW / ACTIVE / BUY downgrade
# ===========================================================================

def test_shadow_behavior_unchanged():
    """SHADOW: score and label must not change."""
    log = _overlay(
        composite_score=80.0,
        current_label="BUY",
        sector_rs_value=-5.0,
        feat007_config={"enabled": True, "stage": "SHADOW"},
    )
    assert log["feat007_post_adjustment_score"] == 80.0
    assert log["feat007_adjusted_label"] == "BUY"
    assert log["feat007_watch_downgrade_applied"] is False


def test_active_strength_applies_delta():
    """ACTIVE STRENGTH: +1.5 delta applied."""
    log = _overlay(
        composite_score=80.0,
        current_label="BUY",
        sector_rs_value=5.0,
        feat007_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert log["feat007_score_adjustment"] == 1.5
    assert log["feat007_post_adjustment_score"] == 81.5


def test_active_weak_downgrade_unchanged():
    """ACTIVE WEAK BUY downgrade still fires when score < 74."""
    log = _overlay(
        composite_score=76.0,
        current_label="BUY",
        sector_rs_value=-5.0,
        feat007_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert log["feat007_watch_downgrade_applied"] is True
    assert log["feat007_adjusted_label"] == "WATCH"
    assert log["feat007_post_adjustment_score"] == 73.0


def test_active_weak_no_downgrade_unchanged():
    """ACTIVE WEAK BUY: no downgrade when score >= 74."""
    log = _overlay(
        composite_score=80.0,
        current_label="BUY",
        sector_rs_value=-1.0,
        feat007_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert log["feat007_watch_downgrade_applied"] is False
    assert log["feat007_adjusted_label"] == "BUY"


def test_reject_immutability_unchanged():
    """REJECT label must never be modified."""
    log = _overlay(
        composite_score=50.0,
        current_label="REJECT",
        sector_rs_value=5.0,
        feat007_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert log["feat007_adjusted_label"] == "REJECT"
    assert log["feat007_score_adjustment"] == 0.0
    assert log["feat007_post_adjustment_score"] == 50.0


def test_strength_cap_unchanged():
    """STRENGTH cap: WATCH cannot become BUY."""
    log = _overlay(
        composite_score=70.0,
        current_label="WATCH",
        sector_rs_value=5.0,
        feat007_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert log["feat007_adjusted_label"] == "WATCH"
    assert log["feat007_post_adjustment_score"] < 72.0


# ===========================================================================
# Backward compatibility — omitted kwargs default to None
# ===========================================================================

def test_backward_compat_omitted_metadata_defaults_none():
    """Callers that omit the three new kwargs must get None for them."""
    svc = RecommendationService()
    log = svc._apply_feat007_overlay(
        composite_score=80.0,
        current_label="BUY",
        symbol="TEST",
        sector_rs_value=5.0,
        feat007_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert log["sector_index_symbol"] is None
    assert log["sector_roc20"] is None
    assert log["benchmark_roc20"] is None


def test_backward_compat_disabled_returns_none():
    """Disabled overlay still returns None (unchanged)."""
    svc = RecommendationService()
    log = svc._apply_feat007_overlay(
        composite_score=80.0,
        current_label="BUY",
        symbol="TEST",
        sector_rs_value=5.0,
        feat007_config={"enabled": False, "stage": "SHADOW"},
    )
    assert log is None


def test_backward_compat_config_none_returns_none():
    """None config still returns None (unchanged)."""
    svc = RecommendationService()
    log = svc._apply_feat007_overlay(
        composite_score=80.0,
        current_label="BUY",
        symbol="TEST",
        sector_rs_value=5.0,
        feat007_config=None,
    )
    assert log is None
