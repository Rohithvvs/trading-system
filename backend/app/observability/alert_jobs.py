"""Scheduled jobs for alert evaluation and log retention (Phase 0)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("app.observability.alert_jobs")

# Singleton engines reused by the scheduler
_alert_engine = None
_resource_tracker = None


def _get_alert_engine():
    global _alert_engine
    if _alert_engine is None:
        from .alert_engine import AlertEngine

        _alert_engine = AlertEngine()
    return _alert_engine


def _get_tracker():
    global _resource_tracker
    if _resource_tracker is None:
        from .resource_tracker import ResourceTracker

        _resource_tracker = ResourceTracker()
    return _resource_tracker


def evaluate_system_alerts_job() -> int:
    """Sample system metrics and evaluate configured alert rules.

    Returns the number of newly triggered alerts.
    """
    try:
        from .rate_monitor import get_error_rate_per_sec, get_request_rate_per_sec

        tracker = _get_tracker()
        snapshot = tracker.get_snapshot()
        metrics = {
            "cpu_percent": float(snapshot.get("cpu_percent") or 0.0),
            "memory_percent": float(snapshot.get("memory_percent") or 0.0),
            "error_rate_per_sec": float(get_error_rate_per_sec()),
            "request_rate_per_sec": float(get_request_rate_per_sec()),
        }
        engine = _get_alert_engine()
        alerts = engine.evaluate_batch(metrics)
        if alerts:
            logger.warning(
                "ALERTS_TRIGGERED | count=%s | rules=%s",
                len(alerts),
                [a.rule_name for a in alerts],
            )
        return len(alerts)
    except Exception:
        logger.exception("ALERT_EVALUATION_FAILED")
        return 0


def rotate_observability_logs_job(retention_days: int = 90) -> dict[str, int]:
    """Archive JSONL files older than retention_days for Phase 0 stores."""
    from ..core.jsonl_store import JsonlStore

    base_dir = os.getenv("LOG_AGGREGATOR_DIR") or os.getenv("EXPERIMENT_LOG_DIR") or "logs"
    categories = [
        "log_aggregator",
        "alerts",
        "experiment_metrics",
        "experiment_events",
    ]
    results: dict[str, int] = {}
    for category in categories:
        try:
            store = JsonlStore(base_dir, category=category)
            results[category] = store.rotate_old_files(retention_days)
        except Exception:
            logger.exception("LOG_ROTATION_FAILED | category=%s", category)
            results[category] = 0
    if any(results.values()):
        logger.info("LOG_ROTATION_COMPLETE | results=%s", results)
    return results
