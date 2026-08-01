"""Unit tests for shadow telemetry / audit event hooks.

Spec source: specs/006-shadow-infra-foundation/spec.md
  - US3: shadow.* audit actions resolve correctly
  - SC-005: registered shadow audit events map to valid routes
  - Telemetry hooks: shadow.execution.start|complete, shadow.discrepancy.detected
"""
from __future__ import annotations

import pytest

from app.governance.audit import (
    SHADOW_AUDIT_ACTIONS,
    SHADOW_METRIC_KEYS,
    AuditTrailManager,
    is_registered_shadow_action,
)


@pytest.mark.asyncio
async def test_shadow_telemetry_audit_logging(tmp_path) -> None:
    """US3 independent test: shadow audit actions can be recorded and read back."""
    audit_file = tmp_path / "audit.jsonl"
    manager = AuditTrailManager(file_path=str(audit_file))

    event1 = await manager.record(
        actor="system",
        action="shadow.execution.start",
        target_type="shadow_run",
        target_id="test_run_1",
        outcome="success",
        details={"symbol": "RELIANCE-EQ"},
    )
    assert event1["action"] == "shadow.execution.start"

    event2 = await manager.record(
        actor="system",
        action="shadow.execution.complete",
        target_type="shadow_run",
        target_id="test_run_1",
        outcome="success",
        details={"symbol": "RELIANCE-EQ"},
    )
    assert event2["action"] == "shadow.execution.complete"

    event3 = await manager.record(
        actor="system",
        action="shadow.discrepancy.detected",
        target_type="shadow_run",
        target_id="test_run_1",
        outcome="success",
        details={"symbol": "RELIANCE-EQ", "diff": 10.0},
    )
    assert event3["action"] == "shadow.discrepancy.detected"

    events = manager.read_all()
    assert len(events) == 3
    actions = [e["action"] for e in events]
    assert "shadow.execution.start" in actions
    assert "shadow.execution.complete" in actions
    assert "shadow.discrepancy.detected" in actions


@pytest.mark.asyncio
async def test_all_shadow_audit_actions_are_recordable(tmp_path) -> None:
    """SC-005 / US3-AS1: each shadow.* action records without rejection."""
    manager = AuditTrailManager(file_path=str(tmp_path / "audit.jsonl"))

    for action in SHADOW_AUDIT_ACTIONS:
        event = await manager.record(
            actor="system",
            action=action,
            target_type="shadow_run",
            target_id="run-sc005",
            outcome="success",
            details={"ruleset": "experimental_v1"},
        )
        assert event["action"] == action
        assert event["uuid"]
        assert event["timestamp"]

    recorded = {e["action"] for e in manager.read_all()}
    assert set(SHADOW_AUDIT_ACTIONS) <= recorded


@pytest.mark.asyncio
async def test_shadow_audit_query_by_action(tmp_path) -> None:
    """US3: query filter resolves shadow discrepancy events only."""
    manager = AuditTrailManager(file_path=str(tmp_path / "audit.jsonl"))

    await manager.record(
        actor="system",
        action="shadow.execution.start",
        target_type="shadow_run",
        target_id="q1",
    )
    await manager.record(
        actor="system",
        action="shadow.discrepancy.detected",
        target_type="shadow_run",
        target_id="q1",
        details={"score_delta": 4.0},
    )
    await manager.record(
        actor="system",
        action="shadow.execution.complete",
        target_type="shadow_run",
        target_id="q1",
    )

    only_disc = manager.query(action="shadow.discrepancy.detected")
    assert len(only_disc) == 1
    assert only_disc[0]["action"] == "shadow.discrepancy.detected"
    assert only_disc[0]["details"]["score_delta"] == 4.0


@pytest.mark.asyncio
async def test_shadow_audit_failure_outcome_is_preserved(tmp_path) -> None:
    """Failure path: failed shadow runs record outcome=failure with details."""
    manager = AuditTrailManager(file_path=str(tmp_path / "audit.jsonl"))

    event = await manager.record(
        actor="system",
        action="shadow.execution.complete",
        target_type="shadow_run",
        target_id="fail-1",
        outcome="failure",
        details={"error": "ruleset executor crashed"},
    )
    assert event["outcome"] == "failure"
    assert "crashed" in event["details"]["error"]

    events = manager.read_all()
    assert events[0]["outcome"] == "failure"


@pytest.mark.asyncio
async def test_shadow_audit_empty_details_default(tmp_path) -> None:
    """Edge: missing details defaults to empty dict."""
    manager = AuditTrailManager(file_path=str(tmp_path / "audit.jsonl"))
    event = await manager.record(
        actor="ops",
        action="shadow.execution.start",
        target_type="shadow_run",
        target_id=None,
    )
    assert event["details"] == {}
    assert event["target_id"] is None


def test_shadow_audit_actions_are_registered_in_catalog() -> None:
    """SC-005 / T013: shadow.* actions are registered in the audit catalog."""
    registered = AuditTrailManager.registered_shadow_actions()
    expected = {
        "shadow.execution.start",
        "shadow.execution.complete",
        "shadow.discrepancy.detected",
    }
    assert registered == expected
    assert registered is SHADOW_AUDIT_ACTIONS
    for action in expected:
        assert is_registered_shadow_action(action) is True
    assert is_registered_shadow_action("shadow.unknown") is False
    assert is_registered_shadow_action("experiment.start") is False


def test_shadow_metric_keys_catalog() -> None:
    """Spec §5: named metric keys are introduced for later telemetry wiring."""
    assert "shadow_mismatch_rate" in SHADOW_METRIC_KEYS
    assert "shadow_score_delta_mean" in SHADOW_METRIC_KEYS
