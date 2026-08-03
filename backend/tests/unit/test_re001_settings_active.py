"""Unit: settings.is_re001_active stage matrix."""

from app.config import settings


def test_is_re001_active_matrix(monkeypatch):
    monkeypatch.setattr(settings, "re001_enabled", False)
    monkeypatch.setattr(settings, "re001_stage", "LAB_SHADOW")
    assert settings.is_re001_active() is False

    monkeypatch.setattr(settings, "re001_enabled", True)
    monkeypatch.setattr(settings, "re001_stage", "OFF")
    assert settings.is_re001_active() is False

    monkeypatch.setattr(settings, "re001_stage", "LAB_SHADOW")
    assert settings.is_re001_active() is True

    monkeypatch.setattr(settings, "re001_stage", "paper_linked")  # case-insensitive
    assert settings.is_re001_active() is True

    monkeypatch.setattr(settings, "re001_stage", "ACTIVE")
    assert settings.is_re001_active() is False
