from app.services.re001.registry import get_re001_registration, is_re001_active


def test_default_inactive(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "re001_enabled", False)
    monkeypatch.setattr(settings, "re001_stage", "OFF")
    assert is_re001_active() is False
    reg = get_re001_registration()
    assert reg.engine_id == "RE-001"
    assert reg.enabled is False


def test_lab_shadow_active(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "re001_enabled", True)
    monkeypatch.setattr(settings, "re001_stage", "LAB_SHADOW")
    assert is_re001_active() is True


def test_invalid_stage_inactive(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "re001_enabled", True)
    monkeypatch.setattr(settings, "re001_stage", "ACTIVE")
    # ACTIVE not a lab evaluation stage in MVP
    assert is_re001_active() is False
