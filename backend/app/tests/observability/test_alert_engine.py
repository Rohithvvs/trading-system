"""Unit tests for AlertEngine — rule loading, evaluation, all conditions, dedup, edge cases.

Acceptance criteria covered:
  AC-US2-3: metric exceeds threshold → alert with severity, timestamp, metric_value
  Edge: dedup, disabled rules, empty rules, all conditions
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.observability.alert_engine import AlertEngine, AlertRule
from app.observability.schema import AlertSeverity, AlertCondition


def _write_rules(path: Path, rules: list[dict]) -> None:
    import yaml
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(rules, f)


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------

def test_load_rules(temp_dir):
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{
        "name": "high-cpu", "metric_name": "cpu_percent",
        "condition": "gt", "threshold": 80.0,
        "severity": "warning", "enabled": True,
    }])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    rules = engine.load_rules()
    assert len(rules) == 1
    assert rules[0].name == "high-cpu"
    assert rules[0].metric_name == "cpu_percent"


def test_load_rules_cached(temp_dir):
    """Edge: load_rules caches rules on first call."""
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{
        "name": "cached", "metric_name": "m",
        "condition": "gt", "threshold": 1.0, "severity": "info", "enabled": True,
    }])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    first = engine.load_rules()
    second = engine.load_rules()
    assert first is second  # same object reference (cached)


def test_load_empty_rules_file(temp_dir):
    """Edge: empty rules file returns no rules."""
    rules_path = temp_dir / "alerts.yml"
    rules_path.write_text("", encoding="utf-8")
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    assert engine.load_rules() == []


def test_load_rules_nonexistent_file(temp_dir):
    """Failure: nonexistent rules file returns empty list (no crash)."""
    engine = AlertEngine(rules_path=str(temp_dir / "nope.yml"), base_dir=str(temp_dir))
    assert engine.load_rules() == []


def test_reload_rules(temp_dir):
    """Edge: reload_rules clears cache and re-reads from disk."""
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{"name": "r1", "metric_name": "m", "condition": "gt",
                                "threshold": 80.0, "severity": "warning", "enabled": True}])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    assert len(engine.load_rules()) == 1

    _write_rules(rules_path, [
        {"name": "r1", "metric_name": "m", "condition": "gt",
         "threshold": 80.0, "severity": "warning", "enabled": True},
        {"name": "r2", "metric_name": "p", "condition": "gt",
         "threshold": 90.0, "severity": "critical", "enabled": True},
    ])
    assert len(engine.reload_rules()) == 2


# ---------------------------------------------------------------------------
# Evaluation — AC-US2-3
# ---------------------------------------------------------------------------

def test_evaluate_triggers_alert(temp_dir):
    """AC-US2-3: threshold breach creates alert with severity, metric_value, rule_name."""
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{
        "name": "high-cpu", "metric_name": "cpu_percent",
        "condition": "gt", "threshold": 80.0,
        "severity": "warning", "message_template": "CPU at {metric_value}%",
        "enabled": True,
    }])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    alerts = engine.evaluate("cpu_percent", 90.0)
    assert len(alerts) == 1
    assert alerts[0].rule_name == "high-cpu"
    assert alerts[0].severity.value == "warning"
    assert alerts[0].metric_value == 90.0
    assert alerts[0].threshold == 80.0


def test_evaluate_no_match(temp_dir):
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{
        "name": "high-cpu", "metric_name": "cpu_percent",
        "condition": "gt", "threshold": 80.0, "severity": "warning", "enabled": True,
    }])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    assert engine.evaluate("cpu_percent", 50.0) == []


def test_evaluate_disabled_rule(temp_dir):
    """Edge: disabled rules never trigger."""
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{
        "name": "disabled", "metric_name": "cpu_percent",
        "condition": "gt", "threshold": 0.0, "severity": "info", "enabled": False,
    }])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    assert engine.evaluate("cpu_percent", 100.0) == []


def test_evaluate_no_matching_metric(temp_dir):
    """Edge: metric name not in rules → no alert."""
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{
        "name": "cpu-rule", "metric_name": "cpu_percent",
        "condition": "gt", "threshold": 80.0, "severity": "warning", "enabled": True,
    }])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    assert engine.evaluate("memory_percent", 90.0) == []


# ---------------------------------------------------------------------------
# All conditions
# ---------------------------------------------------------------------------

def test_condition_gt(temp_dir):
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{"name": "gt-rule", "metric_name": "metric_m",
                                "condition": "gt", "threshold": 50.0, "severity": "warning", "enabled": True}])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    assert len(engine.evaluate("metric_m", 60.0)) == 1
    assert len(engine.evaluate("metric_m", 50.0)) == 0
    assert len(engine.evaluate("metric_m", 40.0)) == 0


def test_condition_lt(temp_dir):
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{"name": "lt-rule", "metric_name": "metric_m",
                                "condition": "lt", "threshold": 50.0, "severity": "warning", "enabled": True}])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    assert len(engine.evaluate("metric_m", 40.0)) == 1
    assert len(engine.evaluate("metric_m", 50.0)) == 0


def test_condition_gte(temp_dir):
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{"name": "gte-rule", "metric_name": "metric_m",
                                "condition": "gte", "threshold": 50.0, "severity": "warning", "enabled": True}])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    assert len(engine.evaluate("metric_m", 50.0)) == 1
    assert len(engine.evaluate("metric_m", 49.9)) == 0


def test_condition_lte(temp_dir):
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{"name": "lte-rule", "metric_name": "metric_m",
                                "condition": "lte", "threshold": 50.0, "severity": "warning", "enabled": True}])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    assert len(engine.evaluate("metric_m", 50.0)) == 1
    assert len(engine.evaluate("metric_m", 50.1)) == 0


def test_condition_eq(temp_dir):
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{"name": "eq-rule", "metric_name": "metric_m",
                                "condition": "eq", "threshold": 50.0, "severity": "info", "enabled": True}])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    assert len(engine.evaluate("metric_m", 50.0)) == 1
    assert len(engine.evaluate("metric_m", 50.0001)) == 0


# ---------------------------------------------------------------------------
# Deduplication — Edge case from spec
# ---------------------------------------------------------------------------

def test_dedup_within_window(temp_dir):
    """Edge: repeated threshold breach within 60s deduplicates (only first alert logged)."""
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{"name": "cpu", "metric_name": "cpu_percent",
                                "condition": "gt", "threshold": 80.0, "severity": "warning", "enabled": True}])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    engine._dedup_window_seconds = 60

    first = engine.evaluate("cpu_percent", 90.0)
    assert len(first) == 1

    second = engine.evaluate("cpu_percent", 95.0)
    assert len(second) == 0  # dedup suppresses


def test_dedup_after_window_expires(temp_dir):
    """Edge: after dedup window, alert triggers again."""
    from datetime import datetime, timezone, timedelta
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{"name": "cpu", "metric_name": "cpu_percent",
                                "condition": "gt", "threshold": 80.0, "severity": "warning", "enabled": True}])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    engine._dedup_window_seconds = 60

    first = engine.evaluate("cpu_percent", 90.0)
    assert len(first) == 1

    # Simulate window expiry
    engine._last_triggered["cpu"] = datetime.now(timezone.utc) - timedelta(seconds=65)

    second = engine.evaluate("cpu_percent", 95.0)
    assert len(second) == 1


# ---------------------------------------------------------------------------
# Message template
# ---------------------------------------------------------------------------

def test_message_template_formatted(temp_dir):
    """Edge: message_template substitutes metric_value and threshold."""
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{
        "name": "tpl", "metric_name": "cpu_percent",
        "condition": "gt", "threshold": 80.0,
        "severity": "warning", "message_template": "CPU {metric_value}% > {threshold}%",
        "enabled": True,
    }])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    alerts = engine.evaluate("cpu_percent", 92.0)
    assert len(alerts) == 1
    assert "92.0%" in alerts[0].message
    assert "80.0%" in alerts[0].message


def test_message_none_when_no_template(temp_dir):
    """Edge: alert message is None when no template configured."""
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{
        "name": "no-tpl", "metric_name": "cpu_percent",
        "condition": "gt", "threshold": 80.0, "severity": "warning", "enabled": True,
    }])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    alerts = engine.evaluate("cpu_percent", 90.0)
    assert alerts[0].message is None


# ---------------------------------------------------------------------------
# Batch evaluation
# ---------------------------------------------------------------------------

def test_evaluate_batch_multiple_triggers(temp_dir):
    """Edge: batch evaluation triggers multiple rules simultaneously."""
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [
        {"name": "high-cpu", "metric_name": "cpu_percent", "condition": "gt",
         "threshold": 80.0, "severity": "warning", "enabled": True},
        {"name": "high-mem", "metric_name": "memory_percent", "condition": "gt",
         "threshold": 90.0, "severity": "critical", "enabled": True},
    ])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    alerts = engine.evaluate_batch({"cpu_percent": 85.0, "memory_percent": 95.0})
    assert len(alerts) == 2


def test_evaluate_batch_no_triggers(temp_dir):
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [
        {"name": "high-cpu", "metric_name": "cpu_percent", "condition": "gt",
         "threshold": 80.0, "severity": "warning", "enabled": True},
    ])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    alerts = engine.evaluate_batch({"cpu_percent": 50.0})
    assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Query alerts
# ---------------------------------------------------------------------------

def test_query_alerts(temp_dir):
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{"name": "cpu", "metric_name": "cpu_percent",
                                "condition": "gt", "threshold": 80.0, "severity": "warning", "enabled": True}])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    engine.evaluate("cpu_percent", 90.0)
    results = engine.query_alerts()
    assert len(results) >= 1


def test_query_alerts_by_severity(temp_dir):
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [
        {"name": "warn", "metric_name": "cpu", "condition": "gt",
         "threshold": 50.0, "severity": "warning", "enabled": True},
        {"name": "crit", "metric_name": "mem", "condition": "gt",
         "threshold": 50.0, "severity": "critical", "enabled": True},
    ])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    engine.evaluate("cpu", 90.0)
    engine.evaluate("mem", 95.0)

    critical = engine.query_alerts(severity=AlertSeverity.CRITICAL)
    assert len(critical) >= 1
    assert all(a["severity"] == "critical" for a in critical)


def test_query_alerts_empty(temp_dir):
    """Edge: querying alerts on empty engine returns []."""
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [{"name": "r", "metric_name": "m",
                                "condition": "gt", "threshold": 1.0, "severity": "info", "enabled": True}])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    assert engine.query_alerts() == []


# ---------------------------------------------------------------------------
# Multiple rules for same metric
# ---------------------------------------------------------------------------

def test_multiple_rules_same_metric(temp_dir):
    """Edge: two rules targeting the same metric both trigger if threshold breached."""
    rules_path = temp_dir / "alerts.yml"
    _write_rules(rules_path, [
        {"name": "warn-cpu", "metric_name": "cpu", "condition": "gt",
         "threshold": 50.0, "severity": "warning", "enabled": True},
        {"name": "crit-cpu", "metric_name": "cpu", "condition": "gt",
         "threshold": 90.0, "severity": "critical", "enabled": True},
    ])
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    engine._dedup_window_seconds = 0  # disable dedup for multi-rule test
    alerts = engine.evaluate("cpu", 95.0)
    assert len(alerts) == 2