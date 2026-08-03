"""Production labels must not depend on RE-001 enablement (conceptual unit of RecommendationService)."""

from app.services.recommendation_service import classify_signal_from_score


def test_production_classifier_unchanged_by_re001_settings(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "re001_enabled", True)
    monkeypatch.setattr(settings, "re001_stage", "LAB_SHADOW")
    assert classify_signal_from_score(75.0) == "BUY"
    assert classify_signal_from_score(60.0) == "WATCH"
    assert classify_signal_from_score(40.0) == "REJECT"

    monkeypatch.setattr(settings, "re001_enabled", False)
    assert classify_signal_from_score(75.0) == "BUY"
