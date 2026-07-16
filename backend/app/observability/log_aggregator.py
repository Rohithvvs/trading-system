from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.jsonl_store import JsonlStore
from .schema import LogEvent, LogEventCreate, LogFilterParams, LogLevel


class LogAggregator:
    """Centralized log aggregation service.

    Ingests log events from multiple sources and persists them to
    daily JSONL files under ``logs/log_aggregator/YYYY-MM-DD.jsonl``.
    Supports querying by level, source, and time range with pagination.
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is None:
            import os as _os
            base_dir = _os.getenv("LOG_AGGREGATOR_DIR", "logs")
        self.store = JsonlStore(base_dir, category="log_aggregator")

    def ingest(self, event: LogEventCreate) -> LogEvent:
        log_event = LogEvent(
            uuid=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            level=event.level,
            source=event.source,
            message=event.message,
            metadata=event.metadata,
        )
        self.store.append(log_event.model_dump(mode="json"))
        return log_event

    def ingest_dict(self, data: dict[str, Any]) -> LogEvent:
        event = LogEventCreate(**data)
        return self.ingest(event)

    def query(
        self,
        level: LogLevel | None = None,
        source: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if level:
            filters["level"] = level.value
        if source:
            filters["source"] = source
        return self.store.query(
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
            filters=filters if filters else None,
        )

    def count(
        self,
        level: LogLevel | None = None,
        source: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        filters: dict[str, Any] = {}
        if level:
            filters["level"] = level.value
        if source:
            filters["source"] = source
        return self.store.count(
            start_time=start_time,
            end_time=end_time,
            filters=filters if filters else None,
        )
