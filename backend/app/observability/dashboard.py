from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .resource_tracker import ResourceTracker
from .alert_engine import AlertEngine
from .log_aggregator import LogAggregator
from .rate_monitor import get_request_rate_per_sec, get_error_rate_per_sec
from .schema import AlertSeverity


class DashboardProvider:
    def __init__(
        self,
        tracker: ResourceTracker | None = None,
        alert_engine: AlertEngine | None = None,
        log_aggregator: LogAggregator | None = None,
    ) -> None:
        self.tracker = tracker or ResourceTracker()
        self.alert_engine = alert_engine or AlertEngine()
        self.log_aggregator = log_aggregator or LogAggregator()

    def get_metrics(
        self, experiment_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        snapshot = self.tracker.get_snapshot()
        result: dict[str, Any] = {
            "system": {
                "cpu_percent": snapshot["cpu_percent"],
                "memory_percent": snapshot["memory_percent"],
                "memory_used_mb": snapshot["memory_used_mb"],
                "request_rate_per_sec": get_request_rate_per_sec(),
                "error_rate_per_sec": get_error_rate_per_sec(),
            },
        }
        if experiment_data:
            result["experiment"] = {
                "id": str(experiment_data.get("id", "")),
                "name": experiment_data.get("name", ""),
                "cpu_percent": snapshot.get("process_cpu_percent", 0.0),
                "memory_percent": snapshot.get("process_memory_percent", 0.0),
                "io_read_bytes_per_sec": snapshot.get("io_read_bytes_per_sec", 0.0),
                "io_write_bytes_per_sec": snapshot.get("io_write_bytes_per_sec", 0.0),
            }
        return result

    def get_logs(
        self,
        level: str | None = None,
        source: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        level_enum = None
        if level:
            from .schema import LogLevel
            try:
                level_enum = LogLevel(level)
            except ValueError:
                pass
        entries = self.log_aggregator.query(
            level=level_enum,
            source=source,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
        total = self.log_aggregator.count(
            level=level_enum,
            source=source,
            start_time=start_time,
            end_time=end_time,
        )
        return {
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_alerts(
        self,
        severity: str | None = None,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        severity_enum = None
        if severity:
            try:
                severity_enum = AlertSeverity(severity)
            except ValueError:
                pass
        alerts = self.alert_engine.query_alerts(
            severity=severity_enum,
            since=since,
        )
        return {"alerts": alerts}
