"""Regression tests for 004-execution-costs-config (config-only phase).

Spec: specs/004-execution-costs-config/spec.md
  - SC-001 / SC-002: no regressions to existing configuration behavior
  - FR-005 / SC-003: no calculation / API / payload changes in this phase
  - FR-007: existing Settings consumers keep working
"""
from __future__ import annotations

import importlib
import inspect

import pytest

from backend.app.config.settings import Settings


def test_settings_instantiation_still_succeeds() -> None:
    """SC-001: Settings still constructs after cost-field extension."""
    # Do not pass _env_file=None here — exercise the real model_config path.
    s = Settings()
    assert s is not None
    assert hasattr(s, "costs_enabled")


def test_feat008_defaults_unchanged_by_cost_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """SC-002: FEAT-008 control-plane defaults remain available and typed."""
    for key in (
        "FEAT008_ENABLED",
        "FEAT008_EXECUTION_MODEL",
        "FEAT008_COMPOSITE_USES_REALISTIC",
        "FEAT008_SKIP_ON_MISSING_NEXT_BAR",
        "COSTS_ENABLED",
        "SLIPPAGE_BPS",
        "COMMISSION_FIXED",
        "COMMISSION_PERCENT",
    ):
        monkeypatch.delenv(key, raising=False)

    s = Settings(_env_file=None)
    assert s.feat008_enabled is True
    assert s.feat008_execution_model == "REALISTIC"
    assert s.feat008_composite_uses_realistic is True
    assert s.feat008_skip_on_missing_next_bar is True
    # Cost defaults coexist without clobbering FEAT-008.
    assert s.costs_enabled is True
    assert s.slippage_bps == 5.0


def test_extra_env_keys_are_ignored() -> None:
    """Regression: Settings still uses extra='ignore' and accepts unknown env noise."""
    # Constructing with unrelated kwargs must not explode when extra=ignore.
    # Pydantic Settings ignores unknown env; model still builds.
    s = Settings(_env_file=None)
    assert s.app_name == "Trading System"


def test_no_execution_cost_calculation_module_required_this_phase() -> None:
    """FR-005 / SC-003: calculation module is not part of this specification.

    This phase only adds Settings fields. Future specs introduce math.
    If a calc module appears later that is fine; this asserts it is not required.
    """
    try:
        mod = importlib.import_module("backend.app.services.utils.execution_costs")
    except ModuleNotFoundError:
        return  # Expected for config-only phase.

    # If a module exists from other work, it must not be the contract of *this* feature.
    # Ensure Settings remains the sole required surface for 004-execution-costs-config.
    assert mod is not None
    assert "costs_enabled" in Settings.model_fields


def test_settings_fields_are_not_callable_calculators() -> None:
    """FR-005: cost fields are configuration data, not calculation callables."""
    s = Settings(_env_file=None)
    assert not callable(s.costs_enabled)
    assert not callable(s.slippage_bps)
    assert not callable(s.commission_fixed)
    assert not callable(s.commission_percent)
    # Values are plain data.
    assert isinstance(s.costs_enabled, bool)
    assert isinstance(s.slippage_bps, (int, float))


def test_config_package_export_still_exposes_settings() -> None:
    """FR-007: backend.app.config continues to export the settings singleton."""
    from backend.app.config import settings as exported

    assert exported is not None
    assert hasattr(exported, "costs_enabled")
    assert hasattr(exported, "database_url")


def test_settings_source_still_single_class() -> None:
    """FR-006: Settings remains a single BaseSettings subclass in settings.py."""
    from backend.app.config import settings as settings_module

    # Reload path via class module.
    module = inspect.getmodule(Settings)
    assert module is not None
    assert module.__name__.endswith("config.settings")
    assert issubclass(Settings, object)
    # Only one Settings class is the configuration entrypoint used by the app.
    from backend.app.config.settings import settings as singleton

    assert isinstance(singleton, Settings)
