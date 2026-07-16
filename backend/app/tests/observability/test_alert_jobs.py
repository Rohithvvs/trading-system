"""Tests for scheduled alert evaluation job."""

from __future__ import annotations

import yaml

from app.observability.alert_jobs import evaluate_system_alerts_job
from app.observability.alert_engine import AlertEngine
import app.observability.alert_jobs as alert_jobs


def test_evaluate_system_alerts_job_triggers(temp_dir, monkeypatch):
    rules_path = temp_dir / "alerts.yml"
    with open(rules_path, "w", encoding="utf-8") as f:
        yaml.dump(
            [
                {
                    "name": "always-cpu",
                    "metric_name": "cpu_percent",
                    "condition": "gte",
                    "threshold": 0.0,
                    "severity": "warning",
                    "enabled": True,
                }
            ],
            f,
        )
    engine = AlertEngine(rules_path=str(rules_path), base_dir=str(temp_dir))
    alert_jobs._alert_engine = engine
    alert_jobs._resource_tracker = None

    count = evaluate_system_alerts_job()
    assert count >= 1
    alerts = engine.query_alerts()
    assert len(alerts) >= 1

    # cleanup singleton for other tests
    alert_jobs._alert_engine = None
