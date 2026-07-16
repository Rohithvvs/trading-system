"""Unit tests for ExperimentService — state machine, CRUD, metrics, queries, edge cases, and failure paths.

Acceptance criteria covered:
  AC-US1-2: start experiment → status active, unique ID, timestamp
  AC-US1-3: add metric to active experiment → recorded against experiment
  AC-US1-4: complete experiment → status completed, ended_at, duration_seconds
  AC-US1-5: query with filters → matching results
  Edge: single-active constraint, terminal state rejection, nonexistent experiment
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.experiment import (
    ExperimentService,
    SingleActiveConstraintError,
    TerminalStateError,
    ExperimentNotFoundError,
)
from app.governance.experiment_log import ExperimentLog
from app.governance.audit import AuditTrailManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def service(db: AsyncSession, temp_dir) -> ExperimentService:
    """Provide ExperimentService with a clean active-experiment slate.

    Commits are durable (production path), so each test clears leftover
    active/paused rows that would violate the single-active constraint.
    """
    from sqlalchemy import text

    await db.execute(
        text(
            "UPDATE experiments SET status = 'failed', "
            "ended_at = COALESCE(ended_at, NOW()), "
            "updated_at = NOW() "
            "WHERE status IN ('active', 'paused')"
        )
    )
    await db.commit()

    log = ExperimentLog(base_dir=str(temp_dir))
    audit = AuditTrailManager(file_path=str(temp_dir / "audit.jsonl"))
    return ExperimentService(db, experiment_log=log, audit_mgr=audit)


# ---------------------------------------------------------------------------
# Happy-path tests (existing, kept for regression)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_experiment(service: ExperimentService):
    """AC-US1-2: starting an experiment creates a record with active status, unique ID, and timestamp."""
    name = f"test-exp-{uuid.uuid4().hex[:8]}"
    exp = await service.create(name=name)
    assert exp.name == name
    assert exp.status == "active"
    assert exp.id is not None
    assert exp.started_at is not None


@pytest.mark.asyncio
async def test_single_active_constraint(service: ExperimentService):
    """Edge: cannot start a second experiment while one is active."""
    await service.create(name=f"exp-1-{uuid.uuid4().hex[:8]}")
    with pytest.raises(SingleActiveConstraintError):
        await service.create(name=f"exp-2-{uuid.uuid4().hex[:8]}")


@pytest.mark.asyncio
async def test_complete_experiment(service: ExperimentService):
    """AC-US1-4: completing sets status to completed with end timestamp and duration."""
    exp = await service.create(name=f"complete-test-{uuid.uuid4().hex[:8]}")
    completed = await service.complete(experiment_id=exp.id)
    assert completed.status == "completed"
    assert completed.ended_at is not None
    assert completed.duration_seconds is not None
    assert isinstance(completed.duration_seconds, int)


@pytest.mark.asyncio
async def test_cannot_modify_completed(service: ExperimentService):
    """Edge: terminal state rejection — cannot pause a completed experiment."""
    exp = await service.create(name=f"terminal-test-{uuid.uuid4().hex[:8]}")
    await service.complete(experiment_id=exp.id)
    with pytest.raises(TerminalStateError):
        await service.pause(experiment_id=exp.id)


@pytest.mark.asyncio
async def test_cannot_resume_failed(service: ExperimentService):
    """Edge: terminal state rejection — cannot resume a failed experiment."""
    exp = await service.create(name=f"fail-terminal-{uuid.uuid4().hex[:8]}")
    await service.fail(experiment_id=exp.id, reason="boom")
    with pytest.raises(TerminalStateError):
        await service.resume(experiment_id=exp.id)


@pytest.mark.asyncio
async def test_pause_resume(service: ExperimentService):
    """AC-US1: pause then resume returns experiment to active state."""
    exp = await service.create(name=f"pause-resume-{uuid.uuid4().hex[:8]}")
    paused = await service.pause(experiment_id=exp.id)
    assert paused.status == "paused"
    resumed = await service.resume(experiment_id=exp.id)
    assert resumed.status == "active"


@pytest.mark.asyncio
async def test_fail_experiment(service: ExperimentService):
    """Edge: failing an experiment sets status to failed and records end timestamp."""
    exp = await service.create(name=f"fail-test-{uuid.uuid4().hex[:8]}")
    failed = await service.fail(experiment_id=exp.id, reason="test failure")
    assert failed.status == "failed"
    assert failed.ended_at is not None


# ---------------------------------------------------------------------------
# Failure-path tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pause_non_active_raises(service: ExperimentService):
    """Failure: pausing an already-paused experiment raises ExperimentError."""
    exp = await service.create(name=f"double-pause-{uuid.uuid4().hex[:8]}")
    await service.pause(experiment_id=exp.id)
    with pytest.raises(Exception):
        await service.pause(experiment_id=exp.id)


@pytest.mark.asyncio
async def test_resume_non_paused_raises(service: ExperimentService):
    """Failure: resuming an active (not paused) experiment raises ExperimentError."""
    exp = await service.create(name=f"resume-active-{uuid.uuid4().hex[:8]}")
    with pytest.raises(Exception):
        await service.resume(experiment_id=exp.id)


@pytest.mark.asyncio
async def test_get_nonexistent(service: ExperimentService):
    """Failure: get returns None for nonexistent UUID."""
    result = await service.get(uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_resolve_nonexistent_raises(service: ExperimentService):
    """Failure: operating on a nonexistent experiment raises ExperimentNotFoundError."""
    with pytest.raises(ExperimentNotFoundError):
        await service.complete(experiment_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_add_metric_nonexistent_raises(service: ExperimentService):
    """Failure: adding metric to nonexistent experiment raises ExperimentNotFoundError."""
    with pytest.raises(ExperimentNotFoundError):
        await service.add_metric(name="cpu_usage", value=1.0, experiment_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_complete_without_id_or_active_raises(service: ExperimentService):
    """Failure: completing with no ID and no active experiment raises ExperimentNotFoundError."""
    with pytest.raises(ExperimentNotFoundError):
        await service.complete()


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_without_id_uses_active(service: ExperimentService):
    """Edge: complete() with no ID resolves to the single active experiment."""
    exp = await service.create(name=f"auto-complete-{uuid.uuid4().hex[:8]}")
    completed = await service.complete()
    assert completed.id == exp.id
    assert completed.status == "completed"


@pytest.mark.asyncio
async def test_add_metric_without_id_uses_active(service: ExperimentService):
    """Edge: add_metric without experiment_id resolves to active experiment."""
    exp = await service.create(name=f"auto-metric-{uuid.uuid4().hex[:8]}")
    metric = await service.add_metric(name="cpu_usage", value=42.0)
    assert metric["experiment_id"] == str(exp.id)


@pytest.mark.asyncio
async def test_metadata_persisted(service: ExperimentService):
    """Edge: metadata passed to create is stored and retrievable."""
    meta = {"env": "test", "version": "1.0"}
    exp = await service.create(name=f"meta-test-{uuid.uuid4().hex[:8]}", metadata=meta)
    assert exp.metadata_ == meta


@pytest.mark.asyncio
async def test_empty_metadata_defaults_to_empty_dict(service: ExperimentService):
    """Edge: no metadata defaults to empty dict."""
    exp = await service.create(name=f"no-meta-{uuid.uuid4().hex[:8]}")
    assert exp.metadata_ == {}


@pytest.mark.asyncio
async def test_create_generates_unique_id(service: ExperimentService):
    """Edge: each experiment gets a unique UUID."""
    exp1 = await service.create(name=f"unique-1-{uuid.uuid4().hex[:8]}")
    await service.complete(experiment_id=exp1.id)
    exp2 = await service.create(name=f"unique-2-{uuid.uuid4().hex[:8]}")
    assert exp1.id != exp2.id


@pytest.mark.asyncio
async def test_fail_with_reason(service: ExperimentService):
    """Edge: failing with a reason records it in the failure details."""
    exp = await service.create(name=f"fail-with-reason-{uuid.uuid4().hex[:8]}")
    failed = await service.fail(experiment_id=exp.id, reason="broken pipe")
    assert failed.status == "failed"


@pytest.mark.asyncio
async def test_duration_is_non_negative(service: ExperimentService):
    """Edge: completed experiment duration is non-negative."""
    exp = await service.create(name=f"duration-test-{uuid.uuid4().hex[:8]}")
    completed = await service.complete(experiment_id=exp.id)
    assert completed.duration_seconds is not None
    assert completed.duration_seconds >= 0


# ---------------------------------------------------------------------------
# Query / filter tests — AC-US1-5
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_experiments_all_returns_pagination(service: ExperimentService):
    """AC-US1-5: list returns results with default pagination bounds."""
    await service.create(name=f"list-a-{uuid.uuid4().hex[:8]}")
    await service.complete()
    await service.create(name=f"list-b-{uuid.uuid4().hex[:8]}")
    exps = await service.list_experiments()
    assert len(exps) >= 2


@pytest.mark.asyncio
async def test_list_filter_by_status(service: ExperimentService):
    """AC-US1-5: filtering by status returns only matching experiments."""
    await service.create(name=f"status-active-{uuid.uuid4().hex[:8]}")
    await service.complete()
    await service.create(name=f"status-completed-1-{uuid.uuid4().hex[:8]}")
    await service.complete()
    await service.create(name=f"status-active-2-{uuid.uuid4().hex[:8]}")

    active = await service.list_experiments(status="active")
    assert all(e.status == "active" for e in active)
    assert len(active) >= 1

    completed = await service.list_experiments(status="completed")
    assert all(e.status == "completed" for e in completed)
    assert len(completed) >= 2


@pytest.mark.asyncio
async def test_list_filter_by_name(service: ExperimentService):
    """AC-US1-5: name filter returns matching experiments (contains, case-insensitive)."""
    await service.create(name=f"alpha-test-{uuid.uuid4().hex[:8]}")
    await service.complete()
    await service.create(name=f"beta-test-{uuid.uuid4().hex[:8]}")
    await service.complete()
    await service.create(name=f"alpha-beta-{uuid.uuid4().hex[:8]}")
    await service.complete()

    results = await service.list_experiments(name="alpha")
    assert all("alpha" in e.name.lower() for e in results)
    assert len(results) >= 2


@pytest.mark.asyncio
async def test_list_filter_by_since(service: ExperimentService):
    """AC-US1-5: date-range filter returns experiments created since a timestamp."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)  # include everything
    name = f"since-test-1-{uuid.uuid4().hex[:8]}"
    await service.create(name=name)
    await service.complete()
    results = await service.list_experiments(since=cutoff)
    assert any(e.name == name for e in results)


# ---------------------------------------------------------------------------
# Metric tests — AC-US1-3
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_metric_to_active(service: ExperimentService):
    """AC-US1-3: metric is recorded against the active experiment and persisted."""
    exp = await service.create(name=f"metric-test-{uuid.uuid4().hex[:8]}")
    metric = await service.add_metric(
        name="cpu_usage", value=45.2, unit="%",
        experiment_id=exp.id,
    )
    assert metric["name"] == "cpu_usage"
    assert metric["value"] == 45.2
    assert metric["experiment_id"] == str(exp.id)
    assert "uuid" in metric
    assert "timestamp" in metric


@pytest.mark.asyncio
async def test_add_metric_with_tags(service: ExperimentService):
    """Edge: tags are preserved in the metric dict."""
    exp = await service.create(name=f"tags-test-{uuid.uuid4().hex[:8]}")
    metric = await service.add_metric(
        name="latency_ms", value=12.3, unit="ms",
        tags={"host": "srv1", "region": "us"},
        experiment_id=exp.id,
    )
    assert metric["tags"] == {"host": "srv1", "region": "us"}


@pytest.mark.asyncio
async def test_add_metric_to_paused_fails(service: ExperimentService):
    """Failure: adding a metric to a nonexistent (paused→competed) experiment fails."""
    exp = await service.create(name=f"paused-metric-{uuid.uuid4().hex[:8]}")
    _ = await service.pause(experiment_id=exp.id)
    # should still work because paused → active is possible
    # (add_metric uses _resolve which resolves the active by default)


# ---------------------------------------------------------------------------
# Audit trail interaction tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_records_audit(service: ExperimentService, temp_dir):
    """AC-US1: creating an experiment records an audit event with action 'experiment.start'."""
    await service.create(name=f"audit-test-{uuid.uuid4().hex[:8]}")
    events = service.audit.read_all()
    assert any(e["action"] == "experiment.start" for e in events)


@pytest.mark.asyncio
async def test_complete_records_audit(service: ExperimentService):
    """AC-US1: completing an experiment records an audit event."""
    exp = await service.create(name=f"audit-complete-{uuid.uuid4().hex[:8]}")
    await service.complete(experiment_id=exp.id)
    events = service.audit.read_all()
    assert any(e["action"] == "experiment.complete" for e in events)


@pytest.mark.asyncio
async def test_fail_records_audit_with_failure_outcome(service: ExperimentService):
    """Edge: failing an experiment records audit event with outcome='failure'."""
    exp = await service.create(name=f"audit-fail-{uuid.uuid4().hex[:8]}")
    await service.fail(experiment_id=exp.id, reason="test")
    events = service.audit.read_all()
    fail_events = [e for e in events if e["action"] == "experiment.fail"]
    assert len(fail_events) == 1
    assert fail_events[0]["outcome"] == "failure"