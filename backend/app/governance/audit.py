from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from ..core.audit_store import AuditStore

# FEAT-011 Spec 1 / US3 / SC-005: registered shadow audit action catalog.
# Observability consumers should treat these as the stable action routes.
SHADOW_AUDIT_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "shadow.execution.start",
        "shadow.execution.complete",
        "shadow.discrepancy.detected",
    }
)

# Named metric keys introduced by Spec 1 (wired in later telemetry specs).
SHADOW_METRIC_KEYS: Final[frozenset[str]] = frozenset(
    {
        "shadow_mismatch_rate",
        "shadow_score_delta_mean",
    }
)


def is_registered_shadow_action(action: str) -> bool:
    """Return True when *action* is in the Spec 1 shadow audit catalog."""
    return action in SHADOW_AUDIT_ACTIONS


class AuditTrailManager:
    """Records governance actions as immutable audit events.

    Delegates to ``AuditStore`` for append-only file persistence with
    SHA-256 hash chaining to ensure immutability.
    """

    def __init__(self, file_path: str | Path | None = None) -> None:
        if file_path is None:
            file_path = os.getenv("AUDIT_LOG_PATH", "logs/audit.jsonl")
        self.store = AuditStore(file_path)

    @staticmethod
    def registered_shadow_actions() -> frozenset[str]:
        """SC-005: expose the registered ``shadow.*`` audit action routes."""
        return SHADOW_AUDIT_ACTIONS

    async def record(
        self,
        actor: str,
        action: str,
        target_type: str,
        target_id: str | None = None,
        outcome: str = "success",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "uuid": str(uuid.uuid4()),
            "actor": actor,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "outcome": outcome,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.store.append(event)
        return event

    def query(
        self,
        actor: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self.store.query(
            actor=actor,
            action=action,
            target_type=target_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    def export_json(self) -> str:
        return self.store.export_json()

    def export_csv(self) -> str:
        return self.store.export_csv()

    def verify_integrity(self) -> tuple[bool, list[str]]:
        return self.store.verify_integrity()

    def read_all(self) -> list[dict[str, Any]]:
        return self.store.read_all()
