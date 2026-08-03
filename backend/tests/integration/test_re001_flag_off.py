from app.services.re001.registry import is_re001_active
from app.services.re001.runner import run_re001_isolated


def test_flag_off_no_decision(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "re001_enabled", False)
    monkeypatch.setattr(settings, "re001_stage", "LAB_SHADOW")
    assert is_re001_active() is False
    assert run_re001_isolated(symbol="ABC") is None
