from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator
from .disk_utils import check_disk_space


class JsonlStore:
    """File-based append-only JSONL storage with query support.

    Each line is a JSON object. Files are organized by day:
    ``logs/<category>/YYYY-MM-DD.jsonl``.

    Supports time-range, field-level filtering, and pagination.
    """

    def __init__(self, base_dir: str | Path, category: str = "default") -> None:
        self.base_dir = Path(base_dir)
        self.category = category
        self.category_dir = self.base_dir / category
        self.category_dir.mkdir(parents=True, exist_ok=True)

    def _current_path(self) -> Path:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        return self.category_dir / f"{date_str}.jsonl"

    def _path_for_date(self, date_str: str) -> Path:
        return self.category_dir / f"{date_str}.jsonl"

    def append(self, record: dict[str, Any]) -> None:
        from .disk_utils import ensure_disk_space

        path = self._current_path()
        ensure_disk_space(self.category_dir)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")

    def append_batch(self, records: list[dict[str, Any]]) -> None:
        from .disk_utils import ensure_disk_space

        path = self._current_path()
        ensure_disk_space(self.category_dir)
        with open(path, "a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")

    @staticmethod
    def _as_naive_utc(dt: datetime | None) -> datetime | None:
        """Normalize datetimes for comparison (JSONL file dates are naive UTC)."""
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def query(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        files = sorted(self.category_dir.glob("*.jsonl"), reverse=True)
        start_naive = self._as_naive_utc(start_time)
        end_naive = self._as_naive_utc(end_time)

        for file_path in files:
            if start_naive or end_naive:
                date_part = file_path.stem
                try:
                    file_date = datetime.strptime(date_part, "%Y-%m-%d")
                except ValueError:
                    continue
                if start_naive and file_date < start_naive.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ):
                    continue
                if end_naive and file_date > end_naive.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                ):
                    continue

            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if self._matches_filters(record, filters):
                        results.append(record)

        if start_naive:
            results = [
                r
                for r in results
                if self._get_ts(r) is None or self._as_naive_utc(self._get_ts(r)) >= start_naive
            ]
        if end_naive:
            results = [
                r
                for r in results
                if self._get_ts(r) is None or self._as_naive_utc(self._get_ts(r)) <= end_naive
            ]

        results.sort(
            key=lambda r: self._as_naive_utc(self._get_ts(r)) or datetime.min,
            reverse=True,
        )
        return results[offset : offset + limit]

    def count(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        filters: dict[str, Any] | None = None,
    ) -> int:
        return len(
            self.query(
                start_time=start_time,
                end_time=end_time,
                filters=filters,
                limit=10**9,
            )
        )

    def _get_ts(self, record: dict[str, Any]) -> datetime | None:
        ts = record.get("timestamp")
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                pass
        elif isinstance(ts, datetime):
            return ts
        return None

    def _matches_filters(
        self, record: dict[str, Any], filters: dict[str, Any] | None
    ) -> bool:
        if not filters:
            return True
        for key, value in filters.items():
            if key not in record:
                return False
            if isinstance(value, (list, tuple)):
                if record[key] not in value:
                    return False
            elif record[key] != value:
                return False
        return True

    def get_active_files(self) -> list[Path]:
        return sorted(self.category_dir.glob("*.jsonl"), reverse=True)

    def archive_older_than(self, days: int) -> int:
        cutoff = datetime.utcnow().timestamp() - days * 86400
        archived = 0
        archive_dir = self.category_dir / "archive"
        archive_dir.mkdir(exist_ok=True)

        for file_path in self.category_dir.glob("*.jsonl"):
            if file_path.stat().st_mtime < cutoff:
                dest = archive_dir / file_path.name
                file_path.rename(dest)
                archived += 1

        return archived

    def rotate_old_files(self, retention_days: int) -> int:
        import time
        cutoff = time.time() - retention_days * 86400
        rotated = 0
        archive_dir = self.category_dir / "archive"
        archive_dir.mkdir(exist_ok=True)

        for file_path in self.category_dir.glob("*.jsonl"):
            if file_path.stat().st_mtime < cutoff:
                dest = archive_dir / file_path.name
                file_path.rename(dest)
                rotated += 1

        return rotated
