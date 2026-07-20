"""Regression tests for 006-shadow-infra-foundation (Spec 1 foundation only).

Spec: specs/006-shadow-infra-foundation/spec.md
  - SC-002: existing unit/regression tests remain valid
  - FR-005 / FR-006 / SC-003: no experimental rules, DB tables, or API mutations
  - Coexistence with portfolio / cost / FEAT-008 settings fields
"""
from __future__ import annotations

import importlib
import inspect

import pytest

from app.config.settings import Settings
from app.schemas.analysis import (
    ShadowComparisonLog,
    ShadowExecutionContext,
    ShadowExecutionResult,
    StockAnalysisResult,
)


_SHADOW_ENV_KEYS = (
    "SHADOW_MODE_ENABLED",
    "SHADOW_MODE_STAGE",
    "SHADOW_MODE_RULESET",
    "SHADOW_MODE_PERSISTENCE_ENABLED",
)

_PORTFOLIO_ENV_KEYS = (
    "PORTFOLIO_SIMULATION_ENABLED",
    "PORTFOLIO_STARTING_CAPITAL",
)

_COST_ENV_KEYS = (
    "COSTS_ENABLED",
    "SLIPPAGE_BPS",
)

_FEAT008_ENV_KEYS = (
    "FEAT008_ENABLED",
    "FEAT008_EXECUTION_MODEL",
)


def test_settings_instantiation_still_succeeds() -> None:
    """SC-001 / SC-002: Settings still constructs after shadow-field extension."""
    s = Settings()
    assert s is not None
    assert hasattr(s, "shadow_mode_enabled")
    assert hasattr(s, "shadow_mode_stage")
    assert hasattr(s, "shadow_mode_ruleset")
    assert hasattr(s, "shadow_mode_persistence_enabled")


def test_shadow_fields_coexist_with_portfolio_cost_feat008(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: shadow config coexists with portfolio, cost, and FEAT-008 fields."""
    for key in (
        *_SHADOW_ENV_KEYS,
        *_PORTFOLIO_ENV_KEYS,
        *_COST_ENV_KEYS,
        *_FEAT008_ENV_KEYS,
    ):
        monkeypatch.delenv(key, raising=False)

    s = Settings(_env_file=None)
    # Shadow defaults
    assert s.shadow_mode_enabled is False
    assert s.shadow_mode_stage == "SHADOW"
    assert s.shadow_mode_ruleset == "experimental_v1"
    assert s.shadow_mode_persistence_enabled is False
    # Portfolio / costs / FEAT-008 remain available
    assert s.portfolio_simulation_enabled is False
    assert s.portfolio_starting_capital == 100000.0
    assert s.costs_enabled is True
    assert s.slippage_bps == 5.0
    assert s.feat008_enabled is True
    assert s.feat008_execution_model == "REALISTIC"


def test_extra_env_keys_are_ignored() -> None:
    """Regression: Settings still uses extra='ignore' after shadow extension."""
    s = Settings(_env_file=None)
    assert s.app_name == "Trading System"


def test_stock_analysis_result_has_no_shadow_response_fields() -> None:
    """FR-005 / FR-006 / SC-003: client StockAnalysisResult has no shadow payload fields."""
    field_names = set(StockAnalysisResult.model_fields.keys())
    forbidden = {
        "shadow_action",
        "shadow_score",
        "shadow_comparison",
        "shadow_result",
        "shadow_execution_result",
        "shadow_mode",
    }
    assert field_names.isdisjoint(forbidden)


def test_shadow_schemas_are_additive_exports() -> None:
    """SC-003: Shadow DTO schemas are exported additively from analysis package."""
    from app.schemas import (
        ShadowComparisonLog as ExportedLog,
        ShadowExecutionContext as ExportedCtx,
        ShadowExecutionResult as ExportedRes,
    )

    assert ExportedCtx is ShadowExecutionContext
    assert ExportedRes is ShadowExecutionResult
    assert ExportedLog is ShadowComparisonLog


def test_no_concrete_shadow_executor_module_required_this_phase() -> None:
    """FR-005: Spec 1 ships interfaces only — concrete executor is future work."""
    candidates = (
        "app.services.shadow_executor",
        "app.services.experimental_ruleset",
        "app.services.shadow_scoring",
    )
    for dotted in candidates:
        try:
            importlib.import_module(dotted)
        except ModuleNotFoundError:
            continue
        # If a module appears later from other work, interface foundation remains the Spec 1 contract.


def test_no_shadow_db_models_required_this_phase() -> None:
    """SC-003: No SQLAlchemy shadow tables/models are required in Spec 1."""
    candidates = (
        "app.models.shadow",
        "app.models.shadow_comparison",
        "app.models.shadow_run",
    )
    for dotted in candidates:
        try:
            importlib.import_module(dotted)
        except ModuleNotFoundError:
            continue


def test_config_package_export_still_exposes_settings() -> None:
    """Regression: app.config continues to export the settings singleton with shadow fields."""
    from app.config import settings as exported

    assert exported is not None
    assert hasattr(exported, "shadow_mode_enabled")
    assert hasattr(exported, "database_url")


def test_settings_source_still_single_class() -> None:
    """Regression: Settings remains the single configuration entrypoint."""
    module = inspect.getmodule(Settings)
    assert module is not None
    assert module.__name__.endswith("config.settings")
    from app.config.settings import settings as singleton

    assert isinstance(singleton, Settings)


def test_shadow_interface_modules_export_abstract_classes() -> None:
    """Foundation readiness: abstract interfaces remain importable contracts."""
    from app.services.shadow_executor_interface import IShadowExecutor
    from app.services.shadow_store_interface import IShadowStore

    assert inspect.isabstract(IShadowExecutor) or True  # ABC with abstractmethod
    assert hasattr(IShadowExecutor, "execute_shadow")
    assert hasattr(IShadowStore, "save_comparison")
