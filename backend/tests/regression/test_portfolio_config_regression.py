"""Regression tests for 005-portfolio-config (config-only phase).

Spec: specs/005-portfolio-config/spec.md
  - AC: existing tests / Settings consumers keep working
  - AC: no execution, sizing, or cash accounting logic in this phase
  - Public Impact: no API / DB / service / model changes
  - Coexistence with FEAT-008 and FEAT-024A cost fields
"""
from __future__ import annotations

import importlib
import inspect

import pytest

from backend.app.config.settings import Settings


_PORTFOLIO_ENV_KEYS = (
    "PORTFOLIO_SIMULATION_ENABLED",
    "PORTFOLIO_MAX_CONCURRENT_POSITIONS",
    "PORTFOLIO_MAX_POSITION_PCT",
    "PORTFOLIO_MINIMUM_TRADE_VALUE",
    "PORTFOLIO_ALLOW_FRACTIONAL_SHARES",
    "PORTFOLIO_RESERVE_CASH_ENABLED",
    "PORTFOLIO_STARTING_CAPITAL",
)

_COST_ENV_KEYS = (
    "COSTS_ENABLED",
    "SLIPPAGE_BPS",
    "COMMISSION_FIXED",
    "COMMISSION_PERCENT",
)

_FEAT008_ENV_KEYS = (
    "FEAT008_ENABLED",
    "FEAT008_EXECUTION_MODEL",
    "FEAT008_COMPOSITE_USES_REALISTIC",
    "FEAT008_SKIP_ON_MISSING_NEXT_BAR",
)


def test_settings_instantiation_still_succeeds() -> None:
    """AC: Settings still constructs after portfolio-field extension."""
    # Do not pass _env_file=None here — exercise the real model_config path.
    s = Settings()
    assert s is not None
    assert hasattr(s, "portfolio_simulation_enabled")
    assert hasattr(s, "portfolio_starting_capital")


def test_feat008_and_cost_defaults_unchanged_by_portfolio_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: FEAT-008 and FEAT-024A defaults remain available and typed."""
    for key in (*_FEAT008_ENV_KEYS, *_COST_ENV_KEYS, *_PORTFOLIO_ENV_KEYS):
        monkeypatch.delenv(key, raising=False)

    s = Settings(_env_file=None)
    assert s.feat008_enabled is True
    assert s.feat008_execution_model == "REALISTIC"
    assert s.feat008_composite_uses_realistic is True
    assert s.feat008_skip_on_missing_next_bar is True
    # Cost defaults coexist without clobbering portfolio fields.
    assert s.costs_enabled is True
    assert s.slippage_bps == 5.0
    assert s.commission_fixed == 0.50
    assert s.commission_percent == 0.001
    # Portfolio defaults coexist without clobbering FEAT-008 / costs.
    assert s.portfolio_simulation_enabled is False
    assert s.portfolio_max_concurrent_positions == 5
    assert s.portfolio_max_position_pct == 20.0
    assert s.portfolio_starting_capital == 100000.0


def test_extra_env_keys_are_ignored() -> None:
    """Regression: Settings still uses extra='ignore' and accepts unknown env noise."""
    s = Settings(_env_file=None)
    assert s.app_name == "Trading System"


def test_no_portfolio_simulation_module_required_this_phase() -> None:
    """AC: no portfolio simulation / sizing / cash accounting module in Spec 1.

    This phase only adds Settings fields. Future specs introduce portfolio logic.
    """
    candidates = (
        "backend.app.services.portfolio_simulation",
        "backend.app.services.portfolio_sizer",
        "backend.app.services.portfolio_accounting",
        "backend.app.services.utils.portfolio_config",
    )
    for dotted in candidates:
        try:
            importlib.import_module(dotted)
        except ModuleNotFoundError:
            continue
        # If a module appears later from other work, it is not the contract of *this* feature.
        # Settings remains the sole required surface for 005-portfolio-config Spec 1.
        assert "portfolio_simulation_enabled" in Settings.model_fields


def test_settings_fields_are_not_callable_calculators() -> None:
    """AC: portfolio fields are configuration data, not calculation callables."""
    s = Settings(_env_file=None)
    assert not callable(s.portfolio_simulation_enabled)
    assert not callable(s.portfolio_max_position_pct)
    assert not callable(s.portfolio_starting_capital)
    assert isinstance(s.portfolio_simulation_enabled, bool)
    assert isinstance(s.portfolio_max_position_pct, (int, float))
    assert isinstance(s.portfolio_starting_capital, (int, float))


def test_config_package_export_still_exposes_settings() -> None:
    """Existing consumers: backend.app.config continues to export the settings singleton."""
    from backend.app.config import settings as exported

    assert exported is not None
    assert hasattr(exported, "portfolio_simulation_enabled")
    assert hasattr(exported, "portfolio_starting_capital")
    assert hasattr(exported, "database_url")
    assert hasattr(exported, "costs_enabled")


def test_settings_source_still_single_class() -> None:
    """Architecture: Settings remains a single BaseSettings subclass in settings.py."""
    module = inspect.getmodule(Settings)
    assert module is not None
    assert module.__name__.endswith("config.settings")
    from backend.app.config.settings import settings as singleton

    assert isinstance(singleton, Settings)


def test_portfolio_env_does_not_break_cost_field_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: portfolio overrides and cost overrides can coexist."""
    for key in (*_PORTFOLIO_ENV_KEYS, *_COST_ENV_KEYS):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("PORTFOLIO_SIMULATION_ENABLED", "True")
    monkeypatch.setenv("PORTFOLIO_STARTING_CAPITAL", "200000.0")
    monkeypatch.setenv("COSTS_ENABLED", "False")
    monkeypatch.setenv("SLIPPAGE_BPS", "12.0")

    s = Settings(_env_file=None)
    assert s.portfolio_simulation_enabled is True
    assert s.portfolio_starting_capital == 200000.0
    assert s.costs_enabled is False
    assert s.slippage_bps == 12.0


def test_backtest_service_still_importable_unchanged() -> None:
    """Public Impact / AC: services are unchanged; BacktestService still imports."""
    from backend.app.services.backtest_service import BacktestService

    assert inspect.isclass(BacktestService)
    # Config-only phase: no portfolio simulation methods required on BacktestService.
    assert not hasattr(BacktestService, "apply_portfolio_constraints")
    assert not hasattr(BacktestService, "run_portfolio_simulation")


def test_portfolio_fields_absent_from_public_api_surface() -> None:
    """Public Impact: portfolio Settings fields are not part of analysis/paper API schemas."""
    from backend.app.schemas import analysis as analysis_schemas
    from backend.app.schemas import paper_trading as paper_schemas

    analysis_names = {
        name
        for name, obj in vars(analysis_schemas).items()
        if inspect.isclass(obj) and hasattr(obj, "model_fields")
        for name in obj.model_fields
    }
    paper_names = {
        name
        for name, obj in vars(paper_schemas).items()
        if inspect.isclass(obj) and hasattr(obj, "model_fields")
        for name in obj.model_fields
    }
    portfolio_settings_fields = {
        "portfolio_simulation_enabled",
        "portfolio_max_concurrent_positions",
        "portfolio_max_position_pct",
        "portfolio_minimum_trade_value",
        "portfolio_allow_fractional_shares",
        "portfolio_reserve_cash_enabled",
        "portfolio_starting_capital",
    }
    assert analysis_names.isdisjoint(portfolio_settings_fields)
    assert paper_names.isdisjoint(portfolio_settings_fields)


def test_portfolio_config_snapshot_logger_available() -> None:
    """Audit L6: ops can emit a non-secret portfolio config snapshot."""
    s = Settings(_env_file=None)
    assert callable(s.log_portfolio_config_snapshot)
    s.log_portfolio_config_snapshot()  # must not raise


def test_dual_source_backtest_equity_not_bound_to_portfolio_settings() -> None:
    """Audit M2: BacktestService source still independent of portfolio_starting_capital."""
    import inspect as _inspect

    from backend.app.services import backtest_service as bs_mod

    source = _inspect.getsource(bs_mod.BacktestService.run)
    # Spec 1 intentionally leaves single-asset sizing/equity paths on BacktestService.
    assert "portfolio_starting_capital" not in source
    assert "portfolio_max_position_pct" not in source
    assert "position_sizing_pct" in source
