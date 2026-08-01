import os
from unittest.mock import patch
import pytest
from app.config.settings import Settings


def test_single_final_write_flag_default_off():
    env = {k: v for k, v in os.environ.items() if k != "SCANNER_SINGLE_FINAL_WRITE_ENABLED"}
    with patch.dict(os.environ, env, clear=True):
        s = Settings()
        assert s.is_scanner_single_final_write_enabled() is False


def test_single_final_write_flag_enabled_true():
    with patch.dict(os.environ, {"SCANNER_SINGLE_FINAL_WRITE_ENABLED": "true"}):
        s = Settings()
        assert s.is_scanner_single_final_write_enabled() is True


def test_single_final_write_flag_enabled_1():
    with patch.dict(os.environ, {"SCANNER_SINGLE_FINAL_WRITE_ENABLED": "1"}):
        s = Settings()
        assert s.is_scanner_single_final_write_enabled() is True


def test_single_final_write_flag_disabled_false():
    with patch.dict(os.environ, {"SCANNER_SINGLE_FINAL_WRITE_ENABLED": "false"}):
        s = Settings()
        assert s.is_scanner_single_final_write_enabled() is False


def test_single_final_write_flag_dynamic_rollback():
    # Simulate active runtime toggle from ON to OFF
    with patch.dict(os.environ, {"SCANNER_SINGLE_FINAL_WRITE_ENABLED": "true"}):
        s1 = Settings()
        assert s1.is_scanner_single_final_write_enabled() is True

    with patch.dict(os.environ, {"SCANNER_SINGLE_FINAL_WRITE_ENABLED": "false"}):
        s2 = Settings()
        assert s2.is_scanner_single_final_write_enabled() is False
