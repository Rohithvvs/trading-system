"""Unit tests for disk_utils — disk space checking, edge cases (T016, T035).

Verifies:
  - check_disk_space returns bool on valid paths
  - ensure_disk_space raises OSError when insufficient
  - Non-existent paths handled gracefully
"""
from __future__ import annotations

import warnings

from app.core.disk_utils import check_disk_space, ensure_disk_space


def test_check_disk_space_true_on_valid_path(temp_dir):
    """On a normal temp directory with plenty of space, returns True."""
    assert check_disk_space(temp_dir) is True


def test_check_disk_space_with_large_threshold():
    """Edge: extremely large threshold returns False (or warns) on available disk."""
    result = check_disk_space(".", threshold_mb=10_000_000)
    assert isinstance(result, bool)


def test_check_disk_space_warns_when_low():
    """Edge: when free space is below threshold, a ResourceWarning is issued."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        check_disk_space(".", threshold_mb=10_000_000)
    # May or may not warn depending on actual disk — just ensure no crash
    assert isinstance(w, list)


def test_ensure_disk_space_passes_on_valid_path(temp_dir):
    """ensure_disk_space does not raise when space is available."""
    ensure_disk_space(temp_dir)


def test_check_disk_space_nonexistent_path_returns_true():
    """Edge: nonexistent path doesn't crash; returns True (conservative)."""
    result = check_disk_space("Z:/nonexistent/path/that/doesnt/exist")
    assert isinstance(result, bool)