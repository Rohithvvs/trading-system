from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class AuditStore:
    """Append-only audit file manager with SHA-256 hash chaining.

    Each event is serialized as a JSON line and appended to the audit file.
    Every event includes a ``previous_hash`` field containing the SHA-256
    hex digest of the canonical JSON of the previous event. Tampering with
    any entry breaks the chain.

    The file is protected by a thread lock during append to ensure atomic
    hash-chain linking. Integrity can be verified by re-reading all entries
    and recomputing the hash chain.
    """

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cached_last_hash: str | None = None
        self._cache_valid = False

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            previous_hash = self._last_hash()
            event["previous_hash"] = previous_hash
            line = json.dumps(event, default=str, ensure_ascii=False, sort_keys=True)
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._cached_last_hash = self._compute_hash(event)
            self._cache_valid = True
        return event

    def read_all(self) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            return []
        events: list[dict[str, Any]] = []
        with open(self.file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                events.append(json.loads(line))
        return events

    def query(
        self,
        *,
        actor: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        events = self.read_all()
        results: list[dict[str, Any]] = []

        for event in events:
            if actor and event.get("actor") != actor:
                continue
            if action and event.get("action") != action:
                continue
            if target_type and event.get("target_type") != target_type:
                continue
            if start_time or end_time:
                ts = event.get("timestamp")
                if isinstance(ts, str):
                    try:
                        parsed = datetime.fromisoformat(ts)
                    except (ValueError, TypeError):
                        continue
                    if start_time and parsed < start_time:
                        continue
                    if end_time and parsed > end_time:
                        continue
            results.append(event)

        results.reverse()
        return results[offset : offset + limit]

    def verify_integrity(self) -> tuple[bool, list[str]]:
        events = self.read_all()
        errors: list[str] = []

        for i, event in enumerate(events):
            prev_hash = event.get("previous_hash")
            if i == 0:
                if prev_hash is not None:
                    errors.append(
                        f"Entry {i}: first entry should have previous_hash=None, "
                        f"got {prev_hash!r}"
                    )
                continue

            prev_event = events[i - 1]
            expected_hash = self._compute_hash(prev_event)
            if prev_hash != expected_hash:
                errors.append(
                    f"Entry {i}: hash chain broken. "
                    f"Expected {expected_hash}, got {prev_hash}"
                )

        return len(errors) == 0, errors

    def export_json(self) -> str:
        return json.dumps(self.read_all(), default=str, ensure_ascii=False, indent=2)

    def export_json_to_file(self, output_path: str | Path) -> int:
        count = 0
        with open(output_path, "w", encoding="utf-8") as out:
            out.write("[\n")
            first = True
            if self.file_path.exists():
                with open(self.file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if not first:
                            out.write(",\n")
                        out.write("  " + line)
                        first = False
                        count += 1
            out.write("\n]\n")
        return count

    def _csv_escape(self, value: Any) -> str:
        s = str(value)
        if isinstance(value, (dict, list)):
            s = json.dumps(value, ensure_ascii=False)
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    def export_csv(self) -> str:
        events = self.read_all()
        if not events:
            return ""
        headers = list(events[0].keys())
        lines: list[str] = [",".join(headers)]
        for event in events:
            row = [self._csv_escape(event.get(h, "")) for h in headers]
            lines.append(",".join(row))
        return "\n".join(lines)

    def export_csv_to_file(self, output_path: str | Path) -> int:
        count = 0
        with open(output_path, "w", encoding="utf-8") as out:
            first = True
            headers: list[str] = []
            if self.file_path.exists():
                with open(self.file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        event = json.loads(line)
                        if first:
                            headers = list(event.keys())
                            out.write(",".join(headers) + "\n")
                            first = False
                        row = [self._csv_escape(event.get(h, "")) for h in headers]
                        out.write(",".join(row) + "\n")
                        count += 1
        return count

    def _last_hash(self) -> str | None:
        if self._cache_valid:
            return self._cached_last_hash
        if not self.file_path.exists() or self.file_path.stat().st_size == 0:
            return None
        with open(self.file_path, "r", encoding="utf-8") as f:
            last_line = None
            for line in f:
                line = line.strip()
                if line:
                    last_line = line
        if not last_line:
            return None
        try:
            last_event = json.loads(last_line)
        except json.JSONDecodeError:
            return None
        return self._compute_hash(last_event)

    def _compute_hash(self, event: dict[str, Any]) -> str:
        event_copy = {k: v for k, v in event.items() if k != "previous_hash"}
        canonical = json.dumps(
            event_copy, default=str, ensure_ascii=False, sort_keys=True
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def size(self) -> int:
        if not self.file_path.exists():
            return 0
        return self.file_path.stat().st_size