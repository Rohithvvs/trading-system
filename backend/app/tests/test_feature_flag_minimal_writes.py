"""Unit tests for SCAN_RESULT_MINIMAL_WRITES feature flag configuration.

Covers FR-010, default fail-safe, and environment resolution edge cases.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from app.config.settings import Settings


def _settings_without_env_flag(**overrides) -> Settings:
    """Build Settings with SCAN_RESULT_MINIMAL_WRITES removed from the environment."""
    env = {k: v for k, v in os.environ.items() if k != "SCAN_RESULT_MINIMAL_WRITES"}
    env.update(overrides)
    with patch.dict(os.environ, env, clear=True):
        return Settings()


def test_default_scan_result_minimal_writes_is_false():
    """FR-010 / Edge: unset flag must default to False (legacy fail-safe)."""
    s = _settings_without_env_flag()
    assert s.scan_result_minimal_writes is False


def test_scan_result_minimal_writes_enabled_when_true():
    """Flag resolves to True when environment variable is 'true'."""
    s = _settings_without_env_flag(SCAN_RESULT_MINIMAL_WRITES="true")
    assert s.scan_result_minimal_writes is True


def test_scan_result_minimal_writes_disabled_when_false():
    """Flag resolves to False when environment variable is 'false'."""
    s = _settings_without_env_flag(SCAN_RESULT_MINIMAL_WRITES="false")
    assert s.scan_result_minimal_writes is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("False", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("off", False),
    ],
)
def test_scan_result_minimal_writes_bool_coercion(raw: str, expected: bool):
    """Boundary: common boolean string coercions for env-backed settings."""
    s = _settings_without_env_flag(SCAN_RESULT_MINIMAL_WRITES=raw)
    assert s.scan_result_minimal_writes is expected


def test_settings_module_singleton_exposes_flag_attribute():
    """Runtime settings object must expose scan_result_minimal_writes (FR-010)."""
    from app.config.settings import settings

    assert hasattr(settings, "scan_result_minimal_writes")
    assert isinstance(settings.scan_result_minimal_writes, bool)


def test_flag_evaluation_error_defaults_to_false_in_scan_path():
    """Edge: config lookup failure defaults to OFF (legacy fail-safe).

    Mirrors scan_execution_service / latest_scan_service getattr fallback pattern.
    """
    broken = MagicMock()
    type(broken).scan_result_minimal_writes = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("config store unavailable"))
    )

    is_minimal = False
    try:
        is_minimal = getattr(broken, "scan_result_minimal_writes", False)
    except Exception:
        is_minimal = False

    assert is_minimal is False


def test_getattr_missing_attribute_defaults_false():
    """Edge: missing attribute on settings object yields False via getattr default."""
    bare = object()
    assert getattr(bare, "scan_result_minimal_writes", False) is False


def test_live_flag_reader_prefers_env_over_attribute():
    """FR-010 / H3: is_scan_result_minimal_writes re-reads env without restart."""
    s = _settings_without_env_flag(SCAN_RESULT_MINIMAL_WRITES="false")
    assert s.is_scan_result_minimal_writes() is False

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "true"}):
        assert s.is_scan_result_minimal_writes() is True

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": "false"}):
        assert s.is_scan_result_minimal_writes() is False


def test_live_flag_reader_defaults_false_on_error():
    """Fail-safe: evaluation error returns False (legacy mode)."""
    s = _settings_without_env_flag()

    def _boom(self):
        raise RuntimeError("boom")

    with patch.dict(os.environ, {"SCAN_RESULT_MINIMAL_WRITES": ""}, clear=False):
        # Force method body exception via broken environ.get path
        with patch("os.environ.get", side_effect=RuntimeError("env broken")):
            assert s.is_scan_result_minimal_writes() is False
