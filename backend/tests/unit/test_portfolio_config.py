"""Unit tests for FEAT-024B / 005-portfolio-config.

Spec source: specs/005-portfolio-config/spec.md

Scope (this phase):
  - Configuration fields only on Settings
  - Strict Pydantic boundaries at initialization
  - No portfolio simulation, sizing, or cash accounting logic
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.config.settings import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PORTFOLIO_ENV_KEYS = (
    "PORTFOLIO_SIMULATION_ENABLED",
    "PORTFOLIO_MAX_CONCURRENT_POSITIONS",
    "PORTFOLIO_MAX_POSITION_PCT",
    "PORTFOLIO_MINIMUM_TRADE_VALUE",
    "PORTFOLIO_ALLOW_FRACTIONAL_SHARES",
    "PORTFOLIO_RESERVE_CASH_ENABLED",
    "PORTFOLIO_STARTING_CAPITAL",
)


def _clear_portfolio_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove portfolio-related env vars so Settings falls back to field defaults."""
    for key in _PORTFOLIO_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _settings_isolated(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Build Settings ignoring project .env and with controlled portfolio env vars."""
    _clear_portfolio_env(monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # Ignore ROOT_DIR/.env so repo-local overrides cannot mask defaults.
    return Settings(_env_file=None)


# ===========================================================================
# Defaults — Acceptance Scenario / quickstart Scenario 1
# ===========================================================================


def test_portfolio_simulation_enabled_default_is_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """portfolio_simulation_enabled defaults to False when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.portfolio_simulation_enabled is False
    assert isinstance(settings.portfolio_simulation_enabled, bool)


def test_portfolio_max_concurrent_positions_default_is_5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """portfolio_max_concurrent_positions defaults to 5 when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.portfolio_max_concurrent_positions == 5
    assert isinstance(settings.portfolio_max_concurrent_positions, int)


def test_portfolio_max_position_pct_default_is_20(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """portfolio_max_position_pct defaults to 20.0 when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.portfolio_max_position_pct == 20.0
    assert isinstance(settings.portfolio_max_position_pct, float)


def test_portfolio_minimum_trade_value_default_is_1000(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """portfolio_minimum_trade_value defaults to 1000.0 when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.portfolio_minimum_trade_value == 1000.0
    assert isinstance(settings.portfolio_minimum_trade_value, float)


def test_portfolio_allow_fractional_shares_default_is_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC: portfolio_allow_fractional_shares defaults to False (NSE/BSE)."""
    settings = _settings_isolated(monkeypatch)
    assert settings.portfolio_allow_fractional_shares is False
    assert isinstance(settings.portfolio_allow_fractional_shares, bool)


def test_portfolio_reserve_cash_enabled_default_is_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """portfolio_reserve_cash_enabled defaults to False when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.portfolio_reserve_cash_enabled is False
    assert isinstance(settings.portfolio_reserve_cash_enabled, bool)


def test_portfolio_starting_capital_default_is_100000(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """portfolio_starting_capital defaults to 100000.0 when unset."""
    settings = _settings_isolated(monkeypatch)
    assert settings.portfolio_starting_capital == 100000.0
    assert isinstance(settings.portfolio_starting_capital, float)


def test_all_portfolio_defaults_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """Acceptance / quickstart Scenario 1: all seven defaults applied with no overrides."""
    settings = _settings_isolated(monkeypatch)
    assert settings.portfolio_simulation_enabled is False
    assert settings.portfolio_max_concurrent_positions == 5
    assert settings.portfolio_max_position_pct == 20.0
    assert settings.portfolio_minimum_trade_value == 1000.0
    assert settings.portfolio_allow_fractional_shares is False
    assert settings.portfolio_reserve_cash_enabled is False
    assert settings.portfolio_starting_capital == 100000.0


# ===========================================================================
# Environment overrides — quickstart Scenario 2
# ===========================================================================


def test_portfolio_simulation_enabled_env_override_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PORTFOLIO_SIMULATION_ENABLED=True is parsed as boolean True."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_SIMULATION_ENABLED="True")
    assert settings.portfolio_simulation_enabled is True


def test_portfolio_simulation_enabled_env_override_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PORTFOLIO_SIMULATION_ENABLED=False remains False."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_SIMULATION_ENABLED="False")
    assert settings.portfolio_simulation_enabled is False


def test_portfolio_max_concurrent_positions_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PORTFOLIO_MAX_CONCURRENT_POSITIONS env var overrides the default."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_MAX_CONCURRENT_POSITIONS="10")
    assert settings.portfolio_max_concurrent_positions == 10


def test_portfolio_max_position_pct_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PORTFOLIO_MAX_POSITION_PCT env var overrides the default."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_MAX_POSITION_PCT="15.5")
    assert settings.portfolio_max_position_pct == 15.5


def test_portfolio_minimum_trade_value_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PORTFOLIO_MINIMUM_TRADE_VALUE env var overrides the default."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_MINIMUM_TRADE_VALUE="500.0")
    assert settings.portfolio_minimum_trade_value == 500.0


def test_portfolio_reserve_cash_enabled_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PORTFOLIO_RESERVE_CASH_ENABLED=True is parsed as boolean True."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_RESERVE_CASH_ENABLED="True")
    assert settings.portfolio_reserve_cash_enabled is True


def test_portfolio_starting_capital_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PORTFOLIO_STARTING_CAPITAL env var overrides the default."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_STARTING_CAPITAL="250000.0")
    assert settings.portfolio_starting_capital == 250000.0


def test_portfolio_allow_fractional_shares_env_false_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit PORTFOLIO_ALLOW_FRACTIONAL_SHARES=False is accepted."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_ALLOW_FRACTIONAL_SHARES="False")
    assert settings.portfolio_allow_fractional_shares is False


def test_all_portfolio_env_overrides_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """Independent Test / quickstart Scenario 2: valid overrides applied together."""
    settings = _settings_isolated(
        monkeypatch,
        PORTFOLIO_SIMULATION_ENABLED="True",
        PORTFOLIO_MAX_CONCURRENT_POSITIONS="10",
        PORTFOLIO_MAX_POSITION_PCT="15.5",
        PORTFOLIO_MINIMUM_TRADE_VALUE="500.0",
        PORTFOLIO_ALLOW_FRACTIONAL_SHARES="False",
        PORTFOLIO_RESERVE_CASH_ENABLED="True",
        PORTFOLIO_STARTING_CAPITAL="250000.0",
    )
    assert settings.portfolio_simulation_enabled is True
    assert settings.portfolio_max_concurrent_positions == 10
    assert settings.portfolio_max_position_pct == 15.5
    assert settings.portfolio_minimum_trade_value == 500.0
    assert settings.portfolio_allow_fractional_shares is False
    assert settings.portfolio_reserve_cash_enabled is True
    assert settings.portfolio_starting_capital == 250000.0


# ===========================================================================
# Type coercion (Pydantic built-in)
# ===========================================================================


def test_bool_coerces_from_common_string_forms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pydantic coerces common truthy/falsy string forms for portfolio bools."""
    assert (
        _settings_isolated(monkeypatch, PORTFOLIO_SIMULATION_ENABLED="1").portfolio_simulation_enabled
        is True
    )
    assert (
        _settings_isolated(monkeypatch, PORTFOLIO_SIMULATION_ENABLED="0").portfolio_simulation_enabled
        is False
    )
    assert (
        _settings_isolated(monkeypatch, PORTFOLIO_RESERVE_CASH_ENABLED="yes").portfolio_reserve_cash_enabled
        is True
    )
    assert (
        _settings_isolated(monkeypatch, PORTFOLIO_RESERVE_CASH_ENABLED="no").portfolio_reserve_cash_enabled
        is False
    )


def test_numeric_fields_coerce_from_integer_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integer-looking env strings coerce cleanly to int/float portfolio fields."""
    settings = _settings_isolated(
        monkeypatch,
        PORTFOLIO_MAX_CONCURRENT_POSITIONS="7",
        PORTFOLIO_MAX_POSITION_PCT="25",
        PORTFOLIO_MINIMUM_TRADE_VALUE="0",
        PORTFOLIO_STARTING_CAPITAL="5000",
    )
    assert settings.portfolio_max_concurrent_positions == 7
    assert settings.portfolio_max_position_pct == 25.0
    assert settings.portfolio_minimum_trade_value == 0.0
    assert settings.portfolio_starting_capital == 5000.0


# ===========================================================================
# Valid boundary values (edge cases — accepted)
# ===========================================================================


def test_max_concurrent_positions_boundary_ge_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge: portfolio_max_concurrent_positions == 1 is accepted (ge=1)."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_MAX_CONCURRENT_POSITIONS="1")
    assert settings.portfolio_max_concurrent_positions == 1


def test_max_position_pct_boundary_just_above_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge: portfolio_max_position_pct just above 0.0 is accepted (gt=0.0)."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_MAX_POSITION_PCT="0.01")
    assert settings.portfolio_max_position_pct == 0.01


def test_max_position_pct_boundary_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge: portfolio_max_position_pct == 100.0 is accepted (le=100.0)."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_MAX_POSITION_PCT="100.0")
    assert settings.portfolio_max_position_pct == 100.0


def test_minimum_trade_value_boundary_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge: portfolio_minimum_trade_value == 0.0 is accepted (ge=0.0)."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_MINIMUM_TRADE_VALUE="0.0")
    assert settings.portfolio_minimum_trade_value == 0.0


def test_starting_capital_boundary_1000(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge: portfolio_starting_capital == 1000.0 is accepted (ge=1000.0)."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_STARTING_CAPITAL="1000.0")
    assert settings.portfolio_starting_capital == 1000.0


def test_large_concurrent_positions_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge: large concurrent position counts are accepted (no upper clamp)."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_MAX_CONCURRENT_POSITIONS="1000")
    assert settings.portfolio_max_concurrent_positions == 1000


def test_large_starting_capital_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Edge: large starting capital is accepted by configuration (no clamp)."""
    settings = _settings_isolated(monkeypatch, PORTFOLIO_STARTING_CAPITAL="10000000.0")
    assert settings.portfolio_starting_capital == 10000000.0


# ===========================================================================
# Failure paths — boundary violations
# ===========================================================================


def test_portfolio_max_concurrent_positions_invalid_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC: max concurrent positions must be >= 1; 0 raises ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_MAX_CONCURRENT_POSITIONS", "0")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "portfolio_max_concurrent_positions" in str(exc.value).lower()


def test_portfolio_max_concurrent_positions_invalid_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure: negative concurrent positions raise ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_MAX_CONCURRENT_POSITIONS", "-1")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "portfolio_max_concurrent_positions" in str(exc.value).lower()


def test_portfolio_max_position_pct_invalid_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC: max position pct must be > 0.0; 0.0 raises ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_MAX_POSITION_PCT", "0.0")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "portfolio_max_position_pct" in str(exc.value).lower()


def test_portfolio_max_position_pct_invalid_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure: negative max position pct raises ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_MAX_POSITION_PCT", "-1.0")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "portfolio_max_position_pct" in str(exc.value).lower()


def test_portfolio_max_position_pct_invalid_above_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC: max position pct must be <= 100.0; 100.1 raises ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_MAX_POSITION_PCT", "100.1")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "portfolio_max_position_pct" in str(exc.value).lower()


def test_portfolio_max_position_pct_invalid_150(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """quickstart Scenario 2: PORTFOLIO_MAX_POSITION_PCT=150.0 fails at startup."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_MAX_POSITION_PCT", "150.0")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "portfolio_max_position_pct" in str(exc.value).lower()


def test_portfolio_minimum_trade_value_invalid_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC: minimum trade value must be >= 0.0; negative raises ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_MINIMUM_TRADE_VALUE", "-0.01")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "portfolio_minimum_trade_value" in str(exc.value).lower()


def test_portfolio_starting_capital_invalid_below_1000(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC: starting capital must be >= 1000.0; 999.9 raises ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_STARTING_CAPITAL", "999.9")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "portfolio_starting_capital" in str(exc.value).lower()


def test_portfolio_starting_capital_invalid_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure: zero starting capital raises ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_STARTING_CAPITAL", "0")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "portfolio_starting_capital" in str(exc.value).lower()


def test_portfolio_allow_fractional_shares_true_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC / plan: portfolio_allow_fractional_shares=True is strictly rejected."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_ALLOW_FRACTIONAL_SHARES", "True")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    message = str(exc.value).lower()
    assert "portfolio_allow_fractional_shares" in message
    assert "fractional shares are not allowed" in message


# ===========================================================================
# Failure paths — invalid types
# ===========================================================================


def test_invalid_max_concurrent_positions_type_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure path: non-numeric concurrent positions must raise ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_MAX_CONCURRENT_POSITIONS", "not-an-int")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_max_position_pct_type_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure path: non-numeric max position pct must raise ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_MAX_POSITION_PCT", "not-a-number")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_minimum_trade_value_type_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure path: non-numeric minimum trade value must raise ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_MINIMUM_TRADE_VALUE", "abc")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_starting_capital_type_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure path: non-numeric starting capital must raise ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_STARTING_CAPITAL", "xx")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_simulation_enabled_type_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure path: non-boolean simulation enabled must raise ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_SIMULATION_ENABLED", "not-a-bool")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_reserve_cash_enabled_type_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure path: non-boolean reserve cash enabled must raise ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_RESERVE_CASH_ENABLED", "not-a-bool")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_allow_fractional_shares_type_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure path: non-boolean fractional shares flag must raise ValidationError."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_ALLOW_FRACTIONAL_SHARES", "maybe")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_empty_string_numeric_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failure path: empty-string env for numeric portfolio fields fails validation."""
    for key in (
        "PORTFOLIO_MAX_CONCURRENT_POSITIONS",
        "PORTFOLIO_MAX_POSITION_PCT",
        "PORTFOLIO_MINIMUM_TRADE_VALUE",
        "PORTFOLIO_STARTING_CAPITAL",
    ):
        _clear_portfolio_env(monkeypatch)
        monkeypatch.setenv(key, "")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)


def test_float_string_for_concurrent_positions_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure path: non-integer concurrent positions string is rejected."""
    _clear_portfolio_env(monkeypatch)
    monkeypatch.setenv("PORTFOLIO_MAX_CONCURRENT_POSITIONS", "5.7")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# ===========================================================================
# Architecture — fields on Settings, config-only phase
# ===========================================================================


def test_all_seven_fields_live_on_settings_class() -> None:
    """AC: all seven portfolio configuration fields are on Settings."""
    expected = (
        "portfolio_simulation_enabled",
        "portfolio_max_concurrent_positions",
        "portfolio_max_position_pct",
        "portfolio_minimum_trade_value",
        "portfolio_allow_fractional_shares",
        "portfolio_reserve_cash_enabled",
        "portfolio_starting_capital",
    )
    for name in expected:
        assert name in Settings.model_fields, f"missing Settings field: {name}"


def test_existing_settings_fields_still_instantiate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC: existing Settings surface remains usable after portfolio extension."""
    settings = _settings_isolated(monkeypatch)
    assert settings.app_name == "Trading System"
    assert isinstance(settings.app_port, int)
    assert isinstance(settings.feat008_enabled, bool)
    assert settings.feat008_execution_model in {"REALISTIC", "LEGACY"}
    # FEAT-024A cost fields continue to coexist.
    assert isinstance(settings.costs_enabled, bool)
    assert isinstance(settings.slippage_bps, float)


def test_module_level_settings_singleton_exposes_portfolio_fields() -> None:
    """Integration-ish: imported settings singleton has the new portfolio attributes."""
    from backend.app.config.settings import settings

    assert hasattr(settings, "portfolio_simulation_enabled")
    assert hasattr(settings, "portfolio_max_concurrent_positions")
    assert hasattr(settings, "portfolio_max_position_pct")
    assert hasattr(settings, "portfolio_minimum_trade_value")
    assert hasattr(settings, "portfolio_allow_fractional_shares")
    assert hasattr(settings, "portfolio_reserve_cash_enabled")
    assert hasattr(settings, "portfolio_starting_capital")
    assert isinstance(settings.portfolio_simulation_enabled, bool)
    assert isinstance(settings.portfolio_max_concurrent_positions, int)
    assert isinstance(settings.portfolio_max_position_pct, float)
    assert isinstance(settings.portfolio_minimum_trade_value, float)
    assert isinstance(settings.portfolio_allow_fractional_shares, bool)
    assert isinstance(settings.portfolio_reserve_cash_enabled, bool)
    assert isinstance(settings.portfolio_starting_capital, float)


def test_portfolio_fields_are_not_callable_calculators() -> None:
    """AC: portfolio fields are configuration data, not calculation callables."""
    s = Settings(_env_file=None)
    assert not callable(s.portfolio_simulation_enabled)
    assert not callable(s.portfolio_max_concurrent_positions)
    assert not callable(s.portfolio_max_position_pct)
    assert not callable(s.portfolio_minimum_trade_value)
    assert not callable(s.portfolio_allow_fractional_shares)
    assert not callable(s.portfolio_reserve_cash_enabled)
    assert not callable(s.portfolio_starting_capital)


def test_settings_accepts_portfolio_kwargs_by_field_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """populate_by_name: constructing Settings with Python field names still works."""
    _clear_portfolio_env(monkeypatch)
    s = Settings(
        _env_file=None,
        portfolio_simulation_enabled=True,
        portfolio_max_concurrent_positions=3,
        portfolio_max_position_pct=10.0,
        portfolio_minimum_trade_value=2000.0,
        portfolio_allow_fractional_shares=False,
        portfolio_reserve_cash_enabled=True,
        portfolio_starting_capital=50000.0,
    )
    assert s.portfolio_simulation_enabled is True
    assert s.portfolio_max_concurrent_positions == 3
    assert s.portfolio_max_position_pct == 10.0
    assert s.portfolio_minimum_trade_value == 2000.0
    assert s.portfolio_allow_fractional_shares is False
    assert s.portfolio_reserve_cash_enabled is True
    assert s.portfolio_starting_capital == 50000.0


def test_settings_kwargs_reject_fractional_shares_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boundary: kwargs path also rejects portfolio_allow_fractional_shares=True."""
    _clear_portfolio_env(monkeypatch)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, portfolio_allow_fractional_shares=True)
    assert "fractional shares are not allowed" in str(exc.value).lower()
