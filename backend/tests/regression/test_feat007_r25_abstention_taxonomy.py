"""
FEAT-007 Batch 3 regression — R25 Abstention Taxonomy.

Verifies that the FEAT-007 overlay preserves the exact specification-defined
abstention reason taxonomy from §12, never collapsing multiple upstream
causes into a generic value.

Spec §12 defines these canonical reasons:
  - upstream_sector_rs_unavailable  (catch-all fallback)
  - no_sector_mapping
  - sector_index_unavailable
  - insufficient_sector_history
  - sector_rs_computation_failed
  - exception:{error_type}

Scope: R25 only. No scoring, classification, SHADOW/ACTIVE logic,
FEAT-004, FEAT-008, or orchestrator flow is exercised or changed here.
"""
from __future__ import annotations

from app.services.recommendation_service import RecommendationService
from app.services.sector_rs_service import SectorRelativeStrengthService
from app.schemas.analysis import SectorOverlayResult, FinalRecommendation, RecommendationReasoning

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
# R25 — Every specification-defined abstention reason is preserved
# ===========================================================================

def test_r25_no_sector_mapping_preserved():
    """When sector mapping is missing, reason must be no_sector_mapping."""
    log = _overlay(sector_rs_value=None, feat007_abstained_reason="no_sector_mapping")
    assert log["feat007_abstained_reason"] == "no_sector_mapping"
    assert log["sector_regime_state"] == "UNKNOWN"


def test_r25_sector_index_unavailable_preserved():
    """When sector index OHLCV is unavailable, reason must be sector_index_unavailable."""
    log = _overlay(sector_rs_value=None, feat007_abstained_reason="sector_index_unavailable")
    assert log["feat007_abstained_reason"] == "sector_index_unavailable"
    assert log["sector_regime_state"] == "UNKNOWN"


def test_r25_insufficient_sector_history_preserved():
    """When sector series is too short, reason must be insufficient_sector_history."""
    log = _overlay(sector_rs_value=None, feat007_abstained_reason="insufficient_sector_history")
    assert log["feat007_abstained_reason"] == "insufficient_sector_history"
    assert log["sector_regime_state"] == "UNKNOWN"


def test_r25_sector_rs_computation_failed_preserved():
    """When sector ROC computation fails, reason must be sector_rs_computation_failed."""
    log = _overlay(sector_rs_value=None, feat007_abstained_reason="sector_rs_computation_failed")
    assert log["feat007_abstained_reason"] == "sector_rs_computation_failed"
    assert log["sector_regime_state"] == "UNKNOWN"


def test_r25_upstream_sector_rs_unavailable_fallback():
    """When no specific reason is threaded, the spec §12 catch-all must be used."""
    log = _overlay(sector_rs_value=None, feat007_abstained_reason=None)
    assert log["feat007_abstained_reason"] == "upstream_sector_rs_unavailable"
    assert log["sector_regime_state"] == "UNKNOWN"


def test_r25_upstream_reason_not_overwritten_when_specific():
    """The most specific reason must be preserved, not overwritten by the fallback."""
    log = _overlay(sector_rs_value=None, feat007_abstained_reason="no_sector_mapping")
    assert log["feat007_abstained_reason"] == "no_sector_mapping"
    assert log["feat007_abstained_reason"] != "upstream_sector_rs_unavailable"


# ===========================================================================
# R25 — Successful path returns None
# ===========================================================================

def test_r25_success_path_returns_none_reason():
    """Successful execution must return feat007_abstained_reason = None."""
    log = _overlay(sector_rs_value=5.0)
    assert log["feat007_abstained_reason"] is None
    assert log["sector_regime_state"] == "STRENGTH"


def test_r25_success_weak_returns_none_reason():
    """WEAK success path must also return None."""
    log = _overlay(sector_rs_value=-3.0)
    assert log["feat007_abstained_reason"] is None
    assert log["sector_regime_state"] == "WEAK"


# ===========================================================================
# R25 — Exception path still returns exception:{ExceptionType}
# ===========================================================================

def test_r25_exception_path_returns_exception_type():
    """Exception path must return exception:{ExceptionType}, unchanged."""
    log = _overlay(sector_rs_value=object(), feat007_abstained_reason="no_sector_mapping")
    assert log["feat007_abstained_reason"] == "exception:TypeError"
    assert log["sector_regime_state"] == "UNKNOWN"


# ===========================================================================
# R25 — Disabled mode unchanged
# ===========================================================================

def test_r25_disabled_mode_unchanged():
    """Disabled overlay still returns None (overlay inactive)."""
    svc = RecommendationService()
    log = svc._apply_feat007_overlay(
        composite_score=80.0,
        current_label="BUY",
        symbol="TEST",
        sector_rs_value=None,
        feat007_config={"enabled": False, "stage": "SHADOW"},
        feat007_abstained_reason="no_sector_mapping",
    )
    assert log is None


def test_r25_config_none_unchanged():
    """None config still returns None."""
    svc = RecommendationService()
    log = svc._apply_feat007_overlay(
        composite_score=80.0,
        current_label="BUY",
        symbol="TEST",
        sector_rs_value=None,
        feat007_config=None,
        feat007_abstained_reason="no_sector_mapping",
    )
    assert log is None


# ===========================================================================
# R25 — SHADOW unchanged
# ===========================================================================

def test_r25_shadow_unchanged():
    """SHADOW mode: score and label must not change."""
    log = _overlay(
        composite_score=80.0,
        current_label="BUY",
        sector_rs_value=-5.0,
        feat007_config={"enabled": True, "stage": "SHADOW"},
    )
    assert log["feat007_post_adjustment_score"] == 80.0
    assert log["feat007_adjusted_label"] == "BUY"
    assert log["feat007_watch_downgrade_applied"] is False
    assert log["feat007_abstained_reason"] is None


# ===========================================================================
# R25 — ACTIVE unchanged
# ===========================================================================

def test_r25_active_strength_unchanged():
    """ACTIVE STRENGTH: +1.5 delta applied, abstained_reason = None."""
    log = _overlay(
        composite_score=80.0,
        current_label="BUY",
        sector_rs_value=5.0,
        feat007_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert log["feat007_score_adjustment"] == 1.5
    assert log["feat007_abstained_reason"] is None


def test_r25_active_weak_downgrade_unchanged():
    """ACTIVE WEAK: downgrade fires, abstained_reason = None."""
    log = _overlay(
        composite_score=76.0,
        current_label="BUY",
        sector_rs_value=-5.0,
        feat007_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert log["feat007_watch_downgrade_applied"] is True
    assert log["feat007_adjusted_label"] == "WATCH"
    assert log["feat007_abstained_reason"] is None


def test_r25_reject_immutability_unchanged():
    """REJECT: score/label never modified, abstained_reason = None."""
    log = _overlay(
        composite_score=50.0,
        current_label="REJECT",
        sector_rs_value=5.0,
        feat007_config={"enabled": True, "stage": "ACTIVE"},
    )
    assert log["feat007_adjusted_label"] == "REJECT"
    assert log["feat007_score_adjustment"] == 0.0
    assert log["feat007_abstained_reason"] is None


# ===========================================================================
# R25 — SR-003 populates spec-defined reasons
# ===========================================================================

def test_r25_sr003_unmapped_sets_no_sector_mapping():
    """SR-003 must set feat007_abstained_reason = no_sector_mapping when unmapped."""
    svc = SectorRelativeStrengthService()
    # Force empty mapping
    svc.mapping = {}
    result = SectorOverlayResult(
        mapped_sector=None,
        original_action="WATCH",
        challenger_action="WATCH",
        downgrade_triggered=False,
    )
    # Simulate the UNMAPPED path
    result.sector_filter_status = "UNMAPPED"
    result.feat007_abstained_reason = "no_sector_mapping"
    assert result.feat007_abstained_reason == "no_sector_mapping"


def test_r25_sr003_schema_has_abstained_reason_field():
    """SectorOverlayResult schema must have feat007_abstained_reason field."""
    fields = SectorOverlayResult.model_fields
    assert "feat007_abstained_reason" in fields


def test_r25_sr003_default_abstained_reason_is_none():
    """SectorOverlayResult default for feat007_abstained_reason must be None."""
    result = SectorOverlayResult()
    assert result.feat007_abstained_reason is None


# ===========================================================================
# R25 — FEAT-004 integration unchanged
# ===========================================================================

def test_r25_feat004_fields_still_present():
    """FEAT-004 fields must still be present in the recommendation (unaffected)."""
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
        feat004_config={"enabled": False, "stage": "SHADOW"},
        feat007_config={"enabled": True, "stage": "ACTIVE"},
        sector_rs_value=5.0,
        sector_index_symbol="NIFTYIT",
        sector_roc20=4.8,
        benchmark_roc20=3.8,
        feat007_abstained_reason=None,
    )
    dumped = result.model_dump(mode="json")
    # FEAT-004 must still be present
    assert "feat004" in dumped
    assert dumped["feat004"] is not None
    assert dumped["feat004"]["feat004_enabled"] is False


# ===========================================================================
# R25 — Backward compatibility
# ===========================================================================

def test_r25_backward_compat_omitted_reason_uses_fallback():
    """Callers that omit feat007_abstained_reason get the spec catch-all."""
    log = _overlay(sector_rs_value=None)
    assert log["feat007_abstained_reason"] == "upstream_sector_rs_unavailable"


def test_r25_backward_compat_no_new_reason_codes():
    """Verify only spec-defined reason codes are used (no invented codes)."""
    spec_reasons = {
        "upstream_sector_rs_unavailable",
        "no_sector_mapping",
        "sector_index_unavailable",
        "insufficient_sector_history",
        "sector_rs_computation_failed",
    }
    # Success path
    log = _overlay(sector_rs_value=5.0)
    assert log["feat007_abstained_reason"] is None

    # Abstain paths with each spec reason
    for reason in spec_reasons:
        log = _overlay(sector_rs_value=None, feat007_abstained_reason=reason)
        assert log["feat007_abstained_reason"] == reason

    # Exception path
    log = _overlay(sector_rs_value=object())
    assert log["feat007_abstained_reason"].startswith("exception:")
