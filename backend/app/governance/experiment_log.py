from __future__ import annotations

import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.jsonl_store import JsonlStore
from ..core.disk_utils import check_disk_space


class ExperimentLog:
    """Persists experiment metric observations and lifecycle events to JSONL files.

    Metrics are stored in ``logs/experiment_metrics/YYYY-MM-DD.jsonl``.
    Lifecycle events are stored in ``logs/experiment_events/YYYY-MM-DD.jsonl``.
    """

    def __init__(
        self,
        base_dir: str | Path | None = None,
    ) -> None:
        if base_dir is None:
            base_dir = os.getenv("EXPERIMENT_LOG_DIR", "logs")
        base_path = Path(base_dir)
        self.metric_store = JsonlStore(base_path, category="experiment_metrics")
        self.event_store = JsonlStore(base_path, category="experiment_events")

    def log_metric(self, metric: dict[str, Any]) -> None:
        check_disk_space(self.metric_store.category_dir)
        self.metric_store.append(metric)

    def log_event(
        self,
        level: str,
        source: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        check_disk_space(self.event_store.category_dir)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "source": source,
            "message": message,
            "metadata": metadata or {},
        }
        self.event_store.append(event)

    def query_metrics(
        self,
        experiment_id: str | None = None,
        name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if experiment_id:
            filters["experiment_id"] = experiment_id
        if name:
            filters["name"] = name
        return self.metric_store.query(
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
            filters=filters if filters else None,
        )

    def query_events(
        self,
        level: str | None = None,
        source: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if level:
            filters["level"] = level
        if source:
            filters["source"] = source
        return self.event_store.query(
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
            filters=filters if filters else None,
        )

    def get_metrics_for_experiment(
        self, experiment_id: str
    ) -> list[dict[str, Any]]:
        return self.query_metrics(experiment_id=experiment_id)
