"""Unit tests for ResourceTracker — psutil metrics, snapshot structure, edge cases.

Acceptance criteria covered:
  AC-US2-4: resource usage per experiment (CPU, memory, I/O) displayed
  SC-007: resource tracking accuracy
  Edge: process not found, empty values, all fields present
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import psutil
import pytest

from app.observability.resource_tracker import ResourceTracker


# ---------------------------------------------------------------------------
# System-level metrics
# ---------------------------------------------------------------------------

def test_get_system_cpu_percent():
    tracker = ResourceTracker()
    pct = tracker.get_system_cpu_percent(interval=0)
    assert isinstance(pct, float)
    assert 0 <= pct <= 100


def test_get_system_memory_percent():
    tracker = ResourceTracker()
    pct = tracker.get_system_memory_percent()
    assert isinstance(pct, float)
    assert 0 <= pct <= 100


def test_get_system_memory_used_mb():
    tracker = ResourceTracker()
    mb = tracker.get_system_memory_used_mb()
    assert isinstance(mb, float)
    assert mb > 0


# ---------------------------------------------------------------------------
# Process-level metrics
# ---------------------------------------------------------------------------

def test_get_process_cpu_percent():
    tracker = ResourceTracker()
    pct = tracker.get_process_cpu_percent(interval=0)
    assert isinstance(pct, float)
    assert pct >= 0


def test_get_process_memory_percent():
    tracker = ResourceTracker()
    pct = tracker.get_process_memory_percent()
    assert isinstance(pct, float)
    assert pct >= 0


def test_get_process_memory_used_mb():
    tracker = ResourceTracker()
    mb = tracker.get_process_memory_used_mb()
    assert isinstance(mb, float)
    assert mb > 0


def test_get_io_counters():
    tracker = ResourceTracker()
    io = tracker.get_io_counters()
    assert "read_bytes_per_sec" in io
    assert "write_bytes_per_sec" in io
    assert isinstance(io["read_bytes_per_sec"], float)
    assert isinstance(io["write_bytes_per_sec"], float)


# ---------------------------------------------------------------------------
# Snapshot completeness — AC-US2-4
# ---------------------------------------------------------------------------

def test_get_snapshot_has_all_fields():
    """AC-US2-4: snapshot contains all required resource metrics + timestamp."""
    tracker = ResourceTracker()
    snap = tracker.get_snapshot()
    required = [
        "cpu_percent", "memory_percent", "memory_used_mb",
        "process_cpu_percent", "process_memory_percent", "process_memory_used_mb",
        "io_read_bytes_per_sec", "io_write_bytes_per_sec", "timestamp",
    ]
    for key in required:
        assert key in snap, f"Missing field in snapshot: {key}"


def test_get_process_snapshot_has_all_fields():
    tracker = ResourceTracker()
    snap = tracker.get_process_snapshot()
    required = ["cpu_percent", "memory_percent", "memory_used_mb",
                "io_read_bytes_per_sec", "io_write_bytes_per_sec"]
    for key in required:
        assert key in snap, f"Missing field in process snapshot: {key}"


def test_snapshot_values_in_range():
    """Edge: all percentage values are in [0, 100]."""
    tracker = ResourceTracker()
    snap = tracker.get_snapshot()
    assert 0 <= snap["cpu_percent"] <= 100
    assert 0 <= snap["memory_percent"] <= 100
    assert snap["memory_used_mb"] > 0
    assert snap["process_memory_used_mb"] > 0


def test_snapshot_timestamp_is_iso():
    """Edge: timestamp is a valid ISO format string."""
    from datetime import datetime
    tracker = ResourceTracker()
    snap = tracker.get_snapshot()
    parsed = datetime.fromisoformat(snap["timestamp"])
    assert parsed is not None


# ---------------------------------------------------------------------------
# Error handling — process not found (T031)
# ---------------------------------------------------------------------------

def test_process_not_found_returns_zero():
    """Edge: when the process no longer exists (container stopped), return 0 gracefully."""
    with patch("psutil.Process") as mock_proc_cls:
        mock_proc = MagicMock()
        mock_proc.cpu_percent.side_effect = psutil.NoSuchProcess(999)
        mock_proc.memory_percent.side_effect = psutil.NoSuchProcess(999)
        mock_proc.memory_info.side_effect = psutil.NoSuchProcess(999)
        mock_proc_cls.return_value = mock_proc

        tracker = ResourceTracker()
        assert tracker.get_process_cpu_percent(interval=0) == 0.0
        assert tracker.get_process_memory_percent() == 0.0
        assert tracker.get_process_memory_used_mb() == 0.0


def test_io_counters_no_io_available():
    """Edge: when io_counters is not available, returns zeros."""
    with patch("psutil.Process") as mock_proc_cls:
        mock_proc = MagicMock()
        mock_proc.io_counters.side_effect = AttributeError("not available")
        mock_proc_cls.return_value = mock_proc

        tracker = ResourceTracker()
        io = tracker.get_io_counters()
        assert io["read_bytes_per_sec"] == 0.0
        assert io["write_bytes_per_sec"] == 0.0


def test_get_snapshot_does_not_raise_on_failure():
    """Edge: get_snapshot always returns a dict despite psutil errors."""
    with patch("psutil.Process") as mock_proc_cls:
        mock_proc = MagicMock()
        mock_proc.cpu_percent.side_effect = psutil.AccessDenied()
        mock_proc.memory_percent.side_effect = psutil.AccessDenied()
        mock_proc.memory_info.side_effect = psutil.AccessDenied()
        mock_proc.io_counters.side_effect = AttributeError()
        mock_proc_cls.return_value = mock_proc

        tracker = ResourceTracker()
        snap = tracker.get_snapshot()
        assert isinstance(snap, dict)
        assert "cpu_percent" in snap


# ---------------------------------------------------------------------------
# Two consecutive snapshots compute I/O rate (SC-007)
# ---------------------------------------------------------------------------

def test_io_rate_after_two_reads():
    """SC-007: two calls to get_io_counters compute a non-negative rate."""
    tracker = ResourceTracker()
    _ = tracker.get_io_counters()  # prime
    import time
    time.sleep(0.01)
    io = tracker.get_io_counters()
    assert isinstance(io["read_bytes_per_sec"], float)
    assert io["read_bytes_per_sec"] >= 0
    assert io["write_bytes_per_sec"] >= 0