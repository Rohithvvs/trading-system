"""Unit tests for FEAT-011 Spec 1 / 006-shadow-infra-foundation configuration.

Spec source: specs/006-shadow-infra-foundation/spec.md

Scope (this phase):
  - Shadow mode configuration fields on Settings
  - Stage validation and env alias loading
  - Startup config snapshot logging
  - No experimental rules / scoring / persistence logic (FR-005)
"""
from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from app.config.settings import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHADOW_ENV_KEYS = (
    "SHADOW_MODE_ENABLED",
    "SHADOW_MODE_STAGE",
    "SHADOW_MODE_RULESET",
    "SHADOW_MODE_PERSISTENCE_ENABLED",
)


def _clear_shadow_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove shadow-related env vars so Settings falls back to field defaults."""
    for key in _SHADOW_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _settings_isolated(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Build Settings ignoring project .env and with controlled shadow env vars."""
    _clear_shadow_env(monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


# ===========================================================================
# Defaults — FR-001..FR-004, US1 Acceptance Scenario 1, SC-001
# ===========================================================================


def test_shadow_mode_enabled_default_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-001 / US1-AS1: shadow_mode_enabled defaults to False when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.shadow_mode_enabled is False
    assert isinstance(settings.shadow_mode_enabled, bool)


def test_shadow_mode_stage_default_is_shadow(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-002 / US1-AS1: shadow_mode_stage defaults to SHADOW when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.shadow_mode_stage == "SHADOW"
    assert isinstance(settings.shadow_mode_stage, str)


def test_shadow_mode_ruleset_default_is_experimental_v1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-003: shadow_mode_ruleset defaults to experimental_v1 when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.shadow_mode_ruleset == "experimental_v1"
    assert isinstance(settings.shadow_mode_ruleset, str)


def test_shadow_mode_persistence_enabled_default_is_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-004: shadow_mode_persistence_enabled defaults to False when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.shadow_mode_persistence_enabled is False
    assert isinstance(settings.shadow_mode_persistence_enabled, bool)


def test_shadow_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """US1 independent test: boot defaults are disabled with safe parameters."""
    settings = _settings_isolated(monkeypatch)
    assert settings.shadow_mode_enabled is False
    assert settings.shadow_mode_stage == "SHADOW"
    assert settings.shadow_mode_ruleset == "experimental_v1"
    assert settings.shadow_mode_persistence_enabled is False


# ===========================================================================
# Valid overrides — US1 Acceptance Scenario 2, SC-001
# ===========================================================================


def test_shadow_config_valid_stage_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-002: OFF / SHADOW / ACTIVE are accepted (case-insensitive, normalized)."""
    for stage in ["off", "shadow", "active", "OFF", "SHADOW", "ACTIVE", " Shadow "]:
        settings = _settings_isolated(monkeypatch, SHADOW_MODE_STAGE=stage)
        assert settings.shadow_mode_stage == stage.strip().upper()


def test_shadow_config_env_bool_and_string_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """US1-AS2: Explicit env values load successfully through aliases."""
    settings = _settings_isolated(
        monkeypatch,
        SHADOW_MODE_ENABLED="true",
        SHADOW_MODE_STAGE="ACTIVE",
        SHADOW_MODE_RULESET="experimental_v2",
        SHADOW_MODE_PERSISTENCE_ENABLED="1",
    )
    assert settings.shadow_mode_enabled is True
    assert settings.shadow_mode_stage == "ACTIVE"
    assert settings.shadow_mode_ruleset == "experimental_v2"
    assert settings.shadow_mode_persistence_enabled is True


def test_shadow_config_disabled_with_active_stage_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge: stage ACTIVE with master toggle False is valid config data."""
    settings = _settings_isolated(
        monkeypatch,
        SHADOW_MODE_ENABLED="false",
        SHADOW_MODE_STAGE="ACTIVE",
    )
    assert settings.shadow_mode_enabled is False
    assert settings.shadow_mode_stage == "ACTIVE"


def test_shadow_mode_stage_none_or_blank_defaults_to_shadow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boundary: None / blank stage normalizes to SHADOW."""
    for raw in (None, "", "   "):
        settings = Settings(
            _env_file=None,
            shadow_mode_stage=raw,  # type: ignore[arg-type]
        )
        assert settings.shadow_mode_stage == "SHADOW"


# ===========================================================================
# Failure paths — invalid configuration
# ===========================================================================


def test_shadow_config_invalid_stage_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-002: Invalid stage values fail Pydantic validation."""
    with pytest.raises(ValidationError) as exc_info:
        _settings_isolated(monkeypatch, SHADOW_MODE_STAGE="INVALID_STAGE")
    assert "Invalid shadow_mode_stage" in str(exc_info.value)


@pytest.mark.parametrize(
    "bad_stage",
    ["PRODUCTION", "enabled", "shadow_mode", "1", "TRUE"],
)
def test_shadow_config_invalid_stage_variants_raise(
    monkeypatch: pytest.MonkeyPatch,
    bad_stage: str,
) -> None:
    """Failure: non-enum stage strings are rejected."""
    with pytest.raises(ValidationError):
        _settings_isolated(monkeypatch, SHADOW_MODE_STAGE=bad_stage)


def test_shadow_config_invalid_bool_enabled_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure: non-boolean enabled value is rejected by Pydantic."""
    with pytest.raises(ValidationError):
        _settings_isolated(monkeypatch, SHADOW_MODE_ENABLED="not-a-bool")


# ===========================================================================
# Observability — config snapshot
# ===========================================================================


def test_log_shadow_config_snapshot_emits_non_secret_fields(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Observability: snapshot logs enabled/stage/ruleset/persistence/hook_active."""
    settings = _settings_isolated(
        monkeypatch,
        SHADOW_MODE_ENABLED="true",
        SHADOW_MODE_STAGE="SHADOW",
        SHADOW_MODE_RULESET="experimental_v1",
        SHADOW_MODE_PERSISTENCE_ENABLED="false",
    )
    with caplog.at_level(logging.INFO, logger="app.config"):
        settings.log_shadow_config_snapshot()

    joined = " ".join(r.message for r in caplog.records)
    assert "Shadow config loaded" in joined
    assert "enabled=True" in joined
    assert "stage=SHADOW" in joined
    assert "ruleset=experimental_v1" in joined
    assert "persistence_enabled=False" in joined
    assert "hook_active=True" in joined


def test_is_shadow_hook_enabled_requires_toggle_and_non_off_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M3: hook is active only when enabled and stage != OFF."""
    disabled = _settings_isolated(
        monkeypatch,
        SHADOW_MODE_ENABLED="false",
        SHADOW_MODE_STAGE="SHADOW",
    )
    assert disabled.is_shadow_hook_enabled() is False

    stage_off = _settings_isolated(
        monkeypatch,
        SHADOW_MODE_ENABLED="true",
        SHADOW_MODE_STAGE="OFF",
    )
    assert stage_off.is_shadow_hook_enabled() is False

    active = _settings_isolated(
        monkeypatch,
        SHADOW_MODE_ENABLED="true",
        SHADOW_MODE_STAGE="ACTIVE",
    )
    assert active.is_shadow_hook_enabled() is True


def test_shadow_persistence_enabled_warns_non_binding(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """M3: persistence flag warns that Spec 1 does not write shadow DB rows."""
    with caplog.at_level(logging.WARNING, logger="app.config"):
        settings = _settings_isolated(
            monkeypatch,
            SHADOW_MODE_PERSISTENCE_ENABLED="true",
        )
        settings.log_shadow_config_snapshot()

    assert settings.shadow_mode_persistence_enabled is True
    joined = " ".join(r.message for r in caplog.records)
    assert "NON-BINDING" in joined
    assert "persistence" in joined.lower()


def test_shadow_stage_active_warns_reserved(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """M3: ACTIVE stage is accepted but logged as reserved for future activation."""
    settings = _settings_isolated(
        monkeypatch,
        SHADOW_MODE_ENABLED="true",
        SHADOW_MODE_STAGE="ACTIVE",
    )
    with caplog.at_level(logging.WARNING, logger="app.config"):
        settings.log_shadow_config_snapshot()

    joined = " ".join(r.message for r in caplog.records)
    assert "ACTIVE is reserved" in joined
