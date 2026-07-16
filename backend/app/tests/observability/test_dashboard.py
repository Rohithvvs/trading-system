"""Unit tests for DashboardProvider — metrics, logs, alerts aggregation, edge cases.

Acceptance criteria covered:
  AC-US2-1: dashboard displays system metrics (CPU, memory, request rate, error rate)
  AC-US2-2: filtered log entries returned with consistent structure
  AC-US2-3: alerts returned with severity, timestamp, metric_value
  AC-US2-4: experiment resource usage displayed
  Edge: no experiment, empty logs, empty alerts, invalid severity
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from uuid import UUID

import pytest
import yaml

from app.observability.dashboard import DashboardProvider
from app.observability.log_aggregator import LogAggregator
from app.observability.alert_engine import AlertEngine
from app.observability.schema import LogEventCreate, LogLevel, AlertSeverity


# ---------------------------------------------------------------------------
# Metrics — AC-US2-1
# ---------------------------------------------------------------------------

def test_get_metrics_no_experiment():
    """AC-US2-1: dashboard returns CPU, memory, request rate, error rate."""
    dashboard = DashboardProvider()
    result = dashboard.get_metrics()
    assert "system" in result
    sys_metrics = result["system"]
    assert "cpu_percent" in sys_metrics
    assert "memory_percent" in sys_metrics
    assert "request_rate_per_sec" in sys_metrics
    assert "error_rate_per_sec" in sys_metrics
    # system metrics are numeric
    assert isinstance(sys_metrics["cpu_percent"], float)
    assert isinstance(sys_metrics["memory_percent"], float)
    assert "experiment" not in result


def test_get_metrics_with_experiment():
    """AC-US2-4: dashboard includes experiment resource usage when experiment is active."""
    dashboard = DashboardProvider()
    result = dashboard.get_metrics(experiment_data={"id": "abc-123", "name": "test-exp"})
    assert "experiment" in result
    assert result["experiment"]["id"] == "abc-123"
    assert result["experiment"]["name"] == "test-exp"
    assert "cpu_percent" in result["experiment"]
    assert "io_read_bytes_per_sec" in result["experiment"]
    assert "io_write_bytes_per_sec" in result["experiment"]


def test_get_metrics_values_in_range():
    """Edge: system percentages are in [0, 100]."""
    dashboard = DashboardProvider()
    result = dashboard.get_metrics()
    assert 0 <= result["system"]["cpu_percent"] <= 100
    assert 0 <= result["system"]["memory_percent"] <= 100


# ---------------------------------------------------------------------------
# Logs — AC-US2-2
# ---------------------------------------------------------------------------

def test_get_logs(temp_dir):
    agg = LogAggregator(base_dir=str(temp_dir))
    agg.ingest(LogEventCreate(level=LogLevel.INFO, source="test", message="hello"))
    dashboard = DashboardProvider(log_aggregator=agg)
    result = dashboard.get_logs()
    assert "entries" in result
    assert "total" in result
    assert "limit" in result
    assert "offset" in result
    assert result["total"] >= 1


def test_get_logs_with_filters(temp_dir):
    """AC-US2-2: level filter returns only matching entries."""
    agg = LogAggregator(base_dir=str(temp_dir))
    agg.ingest(LogEventCreate(level=LogLevel.ERROR, source="err-src", message="error"))
    agg.ingest(LogEventCreate(level=LogLevel.INFO, source="info-src", message="info"))
    dashboard = DashboardProvider(log_aggregator=agg)
    result = dashboard.get_logs(level="error")
    assert result["total"] == 1
    assert result["entries"][0]["level"] == "error"


def test_get_logs_empty(temp_dir):
    """Edge: no logs → empty entries list, total=0."""
    agg = LogAggregator(base_dir=str(temp_dir))
    dashboard = DashboardProvider(log_aggregator=agg)
    result = dashboard.get_logs()
    assert result["entries"] == []
    assert result["total"] == 0


def test_get_logs_with_pagination(temp_dir):
    """Edge: pagination params are reflected in response."""
    agg = LogAggregator(base_dir=str(temp_dir))
    for i in range(20):
        agg.ingest(LogEventCreate(level=LogLevel.INFO, source="page", message=f"m-{i}"))
    dashboard = DashboardProvider(log_aggregator=agg)
    result = dashboard.get_logs(limit=5, offset=0)
    assert result["limit"] == 5
    assert result["offset"] == 0
    assert len(result["entries"]) == 5


# ---------------------------------------------------------------------------
# Alerts — AC-US2-3
# ---------------------------------------------------------------------------

def test_get_alerts(temp_dir):
    """AC-US2-3: alerts include severity, metric_value, timestamp."""
    rules_path = temp_dir / "alerts.yml"
    with open(rules_path, "w", encoding="utf-8") as f:
        yaml.dump([{
            "name": "test-rule", "metric_name": "cpu_percent",
            "condition": "gt", "threshold": 50.0,
            "severity": "warning", "enabled": True,
        }], f)
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    engine.evaluate("cpu_percent", 75.0)
    dashboard = DashboardProvider(alert_engine=engine)
    result = dashboard.get_alerts()
    assert "alerts" in result
    assert len(result["alerts"]) >= 1
    alert = result["alerts"][0]
    assert "severity" in alert
    assert "metric_value" in alert
    assert "timestamp" in alert


def test_get_alerts_empty():
    """Edge: no alerts → empty list."""
    dashboard = DashboardProvider()
    result = dashboard.get_alerts()
    assert "alerts" in result
    assert result["alerts"] == []


def test_get_alerts_filtered_by_severity(temp_dir):
    """Edge: severity filter returns only matching alerts."""
    rules_path = temp_dir / "alerts.yml"
    with open(rules_path, "w", encoding="utf-8") as f:
        yaml.dump([
            {"name": "warn-rule", "metric_name": "metric_a", "condition": "gt",
             "threshold": 1.0, "severity": "warning", "enabled": True},
            {"name": "crit-rule", "metric_name": "metric_b", "condition": "gt",
             "threshold": 1.0, "severity": "critical", "enabled": True},
        ], f)
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    engine._dedup_window_seconds = 0
    engine.evaluate("metric_a", 10.0)
    engine.evaluate("metric_b", 10.0)
    dashboard = DashboardProvider(alert_engine=engine)

    critical = dashboard.get_alerts(severity="critical")
    assert len(critical["alerts"]) >= 1
    assert all(a["severity"] == "critical" for a in critical["alerts"])


# ---------------------------------------------------------------------------
# Dependency injection — verify custom components are used
# ---------------------------------------------------------------------------

def test_custom_log_aggregator_used(temp_dir):
    """DI: a custom LogAggregator passed to DashboardProvider is used."""
    agg = LogAggregator(base_dir=str(temp_dir))
    agg.ingest(LogEventCreate(level=LogLevel.INFO, source="custom", message="injected"))
    dashboard = DashboardProvider(log_aggregator=agg)
    result = dashboard.get_logs(source="custom")
    assert result["total"] >= 1


def test_custom_alert_engine_used(temp_dir):
    """DI: a custom AlertEngine passed to DashboardProvider is used."""
    rules_path = temp_dir / "alerts.yml"
    with open(rules_path, "w", encoding="utf-8") as f:
        yaml.dump([{"name": "x", "metric_name": "metric_m", "condition": "gt",
                     "threshold": 1.0, "severity": "info", "enabled": True}], f)
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    engine.evaluate("metric_m", 10.0)
    dashboard = DashboardProvider(alert_engine=engine)
    result = dashboard.get_alerts()
    assert len(result["alerts"]) >= 1