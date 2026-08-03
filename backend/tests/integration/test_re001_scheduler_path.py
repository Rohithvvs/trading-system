"""FR-017: RE-001 uses the same analysis pipeline entry (orchestrator post-bulk), not a separate batch."""

from app.services.re001.runner import run_re001_isolated


def test_runner_callable_from_pipeline_context(monkeypatch):
    """Scheduler/daily-scan call the same analysis path; runner is the hook surface."""
    from app.config import settings

    monkeypatch.setattr(settings, "re001_enabled", True)
    monkeypatch.setattr(settings, "re001_stage", "LAB_SHADOW")
    # Inactive market regime → deterministic REJECT object (not None)
    class MR:
        market_state = "DEFENSIVE"
        trend_state = "BEARISH"
        new_entry_allowed = False

    out = run_re001_isolated(
        symbol="SCHED",
        market_regime=MR(),
        candles=[],
        technical_results=[],
    )
    assert out is not None
    assert out.engine_id == "RE-001"
    assert out.recommendation_state == "REJECT"
