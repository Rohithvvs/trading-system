"""Unit tests for AuditTrailManager — hash chain integrity, queries, exports, streaming, edge cases.

Acceptance criteria covered:
  AC-US1-5 (audit export): JSON and CSV export of audit events
  Edge: tamper detection, empty audit, first entry hash, date range filtering
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from app.governance.audit import AuditTrailManager


async def _record_events(audit: AuditTrailManager, count: int = 5) -> list[str]:
    uuids: list[str] = []
    for i in range(count):
        event = await audit.record(
            actor="test-user",
            action=f"test.action.{i}",
            target_type="test",
            target_id=f"target-{i}",
            outcome="success",
            details={"index": i},
        )
        uuids.append(event["uuid"])
    return uuids


# ---------------------------------------------------------------------------
# Basic append / read
# ---------------------------------------------------------------------------

def test_append_and_read(temp_dir):
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 3))
    events = audit.read_all()
    assert len(events) == 3


def test_event_has_required_fields(temp_dir):
    """Each audit event must contain uuid, actor, action, target_type, timestamp, previous_hash."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 1))
    events = audit.read_all()
    e = events[0]
    for field in ("uuid", "actor", "action", "target_type", "timestamp", "previous_hash"):
        assert field in e, f"Missing required field: {field}"


# ---------------------------------------------------------------------------
# Hash chain integrity
# ---------------------------------------------------------------------------

def test_hash_chain_integrity(temp_dir):
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 5))
    valid, errors = audit.verify_integrity()
    assert valid, f"Hash chain broken: {errors}"
    assert len(errors) == 0


def test_tamper_detection(temp_dir):
    """Edge: tampering with an event breaks the hash chain."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 3))

    events = audit.read_all()
    events[1]["actor"] = "hacker"
    with open(str(temp_dir / "audit.jsonl"), "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, default=str, ensure_ascii=False, sort_keys=True) + "\n")

    valid, errors = audit.verify_integrity()
    assert not valid
    assert len(errors) > 0


def test_first_entry_previous_hash_is_none(temp_dir):
    """Edge: first event in the chain has previous_hash=None."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 1))
    events = audit.read_all()
    assert events[0]["previous_hash"] is None


def test_empty_audit_is_valid(temp_dir):
    """Edge: empty audit file passes integrity check."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit-empty.jsonl"))
    valid, errors = audit.verify_integrity()
    assert valid
    assert len(errors) == 0


# ---------------------------------------------------------------------------
# Query tests — AC-US1-5
# ---------------------------------------------------------------------------

def test_query_by_action(temp_dir):
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 5))
    results = audit.query(action="test.action.0")
    assert len(results) == 1
    assert results[0]["action"] == "test.action.0"


def test_query_by_actor(temp_dir):
    """AC-US1-5: query audit trail filtered by actor."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio

    async def _seed():
        await audit.record(actor="alice", action="a", target_type="t", outcome="success")
        await audit.record(actor="bob", action="b", target_type="t", outcome="success")

    asyncio.run(_seed())
    alice_events = audit.query(actor="alice")
    assert len(alice_events) == 1
    assert alice_events[0]["actor"] == "alice"


def test_query_by_target_type(temp_dir):
    """AC-US1-5: query audit trail filtered by target_type."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio

    async def _seed():
        await audit.record(actor="u", action="a", target_type="experiment", outcome="success")
        await audit.record(actor="u", action="b", target_type="config", outcome="success")

    asyncio.run(_seed())
    cfg = audit.query(target_type="config")
    assert len(cfg) == 1
    assert cfg[0]["target_type"] == "config"


def test_query_by_date_range(temp_dir):
    """AC-US1-5: query audit trail filtered by start_time/end_time."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 3))

    now = datetime.now(timezone.utc)
    future = now + timedelta(hours=1)
    results = audit.query(start_time=future)
    assert len(results) == 0

    past = now - timedelta(hours=1)
    results = audit.query(start_time=past)
    assert len(results) >= 1


def test_query_with_limit_offset(temp_dir):
    """Edge: query results respect limit and offset."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 10))

    page1 = audit.query(limit=3, offset=0)
    page2 = audit.query(limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 3
    assert page1[0]["uuid"] != page2[0]["uuid"]


# ---------------------------------------------------------------------------
# Export tests — AC-US1-5
# ---------------------------------------------------------------------------

def test_export_json(temp_dir):
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 2))
    output = audit.export_json()
    assert '"actor": "test-user"' in output


def test_export_csv(temp_dir):
    """AC-US1-5: CSV export includes headers and data."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 2))
    output = audit.export_csv()
    assert len(output) > 0
    lines = output.strip().split("\n")
    assert len(lines) >= 3  # header + 2 rows


def test_export_json_to_file_streaming(temp_dir):
    """Edge: streaming JSON export writes valid JSON array to file."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 3))

    out_path = temp_dir / "export.json"
    count = audit.store.export_json_to_file(out_path)
    assert count == 3
    assert out_path.exists()

    content = out_path.read_text(encoding="utf-8")
    parsed = json.loads(content)
    assert len(parsed) == 3


def test_export_csv_to_file_streaming(temp_dir):
    """Edge: streaming CSV export writes valid CSV to file."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    import asyncio
    asyncio.run(_record_events(audit, 3))

    out_path = temp_dir / "export.csv"
    count = audit.store.export_csv_to_file(out_path)
    assert count == 3
    assert out_path.exists()

    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 4  # header + 3 rows


def test_export_empty_csv(temp_dir):
    """Edge: CSV export of empty audit returns empty string."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    output = audit.export_csv()
    assert output == ""


def test_export_empty_json(temp_dir):
    """Edge: JSON export of empty audit returns '[]'."""
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    output = audit.export_json()
    parsed = json.loads(output)
    assert parsed == []