"""Unit tests for FEAT-024A / 004-execution-costs-config.

Spec source: specs/004-execution-costs-config/spec.md

Scope (this phase):
  - Configuration fields only on Settings
  - No execution cost calculation logic (FR-005 / SC-003)
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.config.settings import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COST_ENV_KEYS = (
    "COSTS_ENABLED",
    "SLIPPAGE_BPS",
    "COMMISSION_FIXED",
    "COMMISSION_PERCENT",
)


def _clear_cost_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove cost-related env vars so Settings falls back to field defaults."""
    for key in _COST_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _settings_isolated(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Build Settings ignoring project .env and with controlled cost env vars."""
    _clear_cost_env(monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # Ignore ROOT_DIR/.env so repo-local overrides cannot mask defaults.
    return Settings(_env_file=None)


# ===========================================================================
# Defaults — FR-001..FR-004, Acceptance Scenario 1, quickstart Scenario 1
# ===========================================================================


def test_costs_enabled_default_is_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-001: costs_enabled defaults to True when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.costs_enabled is True
    assert isinstance(settings.costs_enabled, bool)


def test_slippage_bps_default_is_5(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-002: slippage_bps defaults to 5.0 when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.slippage_bps == 5.0
    assert isinstance(settings.slippage_bps, float)


def test_commission_fixed_default_is_0_50(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-003: commission_fixed defaults to 0.50 when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.commission_fixed == 0.50
    assert isinstance(settings.commission_fixed, float)


def test_commission_percent_default_is_0_001(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-004: commission_percent defaults to 0.001 when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.commission_percent == 0.001
    assert isinstance(settings.commission_percent, float)


def test_all_execution_cost_defaults_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """Acceptance Scenario 1: all four defaults applied on init with no overrides."""
    settings = _settings_isolated(monkeypatch)
    assert settings.costs_enabled is True
    assert settings.slippage_bps == 5.0
    assert settings.commission_fixed == 0.50
    assert settings.commission_percent == 0.001


# ===========================================================================
# Environment overrides — quickstart Scenario 2, Independent Test
# ===========================================================================


def test_costs_enabled_env_override_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """COSTS_ENABLED=False is parsed as boolean False."""
    settings = _settings_isolated(monkeypatch, COSTS_ENABLED="False")
    assert settings.costs_enabled is False


def test_costs_enabled_env_override_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """COSTS_ENABLED=True remains True."""
    settings = _settings_isolated(monkeypatch, COSTS_ENABLED="True")
    assert settings.costs_enabled is True


def test_slippage_bps_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """SLIPPAGE_BPS env var overrides the default."""
    settings = _settings_isolated(monkeypatch, SLIPPAGE_BPS="10.0")
    assert settings.slippage_bps == 10.0


def test_commission_fixed_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """COMMISSION_FIXED env var overrides the default."""
    settings = _settings_isolated(monkeypatch, COMMISSION_FIXED="1.25")
    assert settings.commission_fixed == 1.25


def test_commission_percent_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """COMMISSION_PERCENT env var overrides the default."""
    settings = _settings_isolated(monkeypatch, COMMISSION_PERCENT="0.0025")
    assert settings.commission_percent == 0.0025


def test_all_cost_env_overrides_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """Independent Test: all four parameters can be supplied via environment."""
    settings = _settings_isolated(
        monkeypatch,
        COSTS_ENABLED="false",
        SLIPPAGE_BPS="12.5",
        COMMISSION_FIXED="2.0",
        COMMISSION_PERCENT="0.005",
    )
    assert settings.costs_enabled is False
    assert settings.slippage_bps == 12.5
    assert settings.commission_fixed == 2.0
    assert settings.commission_percent == 0.005


# ===========================================================================
# Type coercion (Pydantic built-in) — data-model validation rules
# ===========================================================================


def test_bool_coerces_from_common_string_forms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pydantic coerces common truthy/falsy string forms for costs_enabled."""
    assert _settings_isolated(monkeypatch, COSTS_ENABLED="1").costs_enabled is True
    assert _settings_isolated(monkeypatch, COSTS_ENABLED="0").costs_enabled is False
    assert _settings_isolated(monkeypatch, COSTS_ENABLED="yes").costs_enabled is True
    assert _settings_isolated(monkeypatch, COSTS_ENABLED="no").costs_enabled is False


def test_float_fields_coerce_from_integer_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integer-looking env strings coerce cleanly to float fields."""
    settings = _settings_isolated(
        monkeypatch,
        SLIPPAGE_BPS="5",
        COMMISSION_FIXED="1",
        COMMISSION_PERCENT="0",
    )
    assert settings.slippage_bps == 5.0
    assert settings.commission_fixed == 1.0
    assert settings.commission_percent == 0.0


# ===========================================================================
# Failure paths — invalid types
# ===========================================================================


def test_invalid_slippage_bps_type_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failure path: non-numeric SLIPPAGE_BPS must raise ValidationError."""
    _clear_cost_env(monkeypatch)
    monkeypatch.setenv("SLIPPAGE_BPS", "not-a-number")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "slippage_bps" in str(exc.value).lower() or "float" in str(exc.value).lower()


def test_invalid_commission_fixed_type_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failure path: non-numeric COMMISSION_FIXED must raise ValidationError."""
    _clear_cost_env(monkeypatch)
    monkeypatch.setenv("COMMISSION_FIXED", "abc")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_commission_percent_type_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failure path: non-numeric COMMISSION_PERCENT must raise ValidationError."""
    _clear_cost_env(monkeypatch)
    monkeypatch.setenv("COMMISSION_PERCENT", "xx%")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_costs_enabled_type_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failure path: non-boolean COSTS_ENABLED must raise ValidationError."""
    _clear_cost_env(monkeypatch)
    monkeypatch.setenv("COSTS_ENABLED", "not-a-bool")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# ===========================================================================
# Edge cases — per spec assumption (no custom ge=0 validation required)
# ===========================================================================


def test_negative_slippage_accepted_without_custom_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge (spec assumption): negative slippage is accepted; no new validators."""
    settings = _settings_isolated(monkeypatch, SLIPPAGE_BPS="-1.0")
    assert settings.slippage_bps == -1.0


def test_negative_commission_values_accepted_without_custom_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge (spec assumption): negative commissions rely on existing type checks only."""
    settings = _settings_isolated(
        monkeypatch,
        COMMISSION_FIXED="-0.50",
        COMMISSION_PERCENT="-0.001",
    )
    assert settings.commission_fixed == -0.50
    assert settings.commission_percent == -0.001


def test_zero_values_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Edge: zero is a valid float configuration for cost parameters."""
    settings = _settings_isolated(
        monkeypatch,
        SLIPPAGE_BPS="0",
        COMMISSION_FIXED="0",
        COMMISSION_PERCENT="0",
    )
    assert settings.slippage_bps == 0.0
    assert settings.commission_fixed == 0.0
    assert settings.commission_percent == 0.0


def test_large_boundary_values_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Edge: large numeric inputs are accepted by configuration (no clamp)."""
    settings = _settings_isolated(
        monkeypatch,
        SLIPPAGE_BPS="10000.0",
        COMMISSION_FIXED="999999.99",
        COMMISSION_PERCENT="1.0",
    )
    assert settings.slippage_bps == 10000.0
    assert settings.commission_fixed == 999999.99
    assert settings.commission_percent == 1.0


# ===========================================================================
# Architecture / FR-006 / FR-007 — extend Settings, no duplicate class
# ===========================================================================


def test_fields_live_on_settings_class_not_separate_config() -> None:
    """FR-006: cost fields are attributes of Settings (no parallel config class)."""
    assert "costs_enabled" in Settings.model_fields
    assert "slippage_bps" in Settings.model_fields
    assert "commission_fixed" in Settings.model_fields
    assert "commission_percent" in Settings.model_fields


def test_existing_settings_fields_still_instantiate(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-007 / Acceptance Scenario 2: existing Settings surface remains usable."""
    settings = _settings_isolated(monkeypatch)
    # Spot-check a few long-standing fields that predate this feature.
    assert settings.app_name == "Trading System"
    assert isinstance(settings.app_port, int)
    assert isinstance(settings.feat008_enabled, bool)
    assert settings.feat008_execution_model in {"REALISTIC", "LEGACY"}


def test_module_level_settings_singleton_exposes_cost_fields() -> None:
    """Integration-ish: imported settings singleton has the new cost attributes."""
    from backend.app.config.settings import settings

    assert hasattr(settings, "costs_enabled")
    assert hasattr(settings, "slippage_bps")
    assert hasattr(settings, "commission_fixed")
    assert hasattr(settings, "commission_percent")
    assert isinstance(settings.costs_enabled, bool)
    assert isinstance(settings.slippage_bps, float)
    assert isinstance(settings.commission_fixed, float)
    assert isinstance(settings.commission_percent, float)
