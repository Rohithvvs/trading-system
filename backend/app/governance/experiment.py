from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.experiment import Experiment
from ..observability.schema import ExperimentStatus, MetricObservationCreate
from .experiment_log import ExperimentLog
from .audit import AuditTrailManager


class ExperimentError(Exception):
    pass


class SingleActiveConstraintError(ExperimentError):
    pass


class TerminalStateError(ExperimentError):
    pass


class ExperimentNotFoundError(ExperimentError):
    pass


class ExperimentService:
    """Governs experiment lifecycle with a forward-only state machine.

    State machine::

        [create] -> active -> paused <-> active -> completed
                    ↓                              ↓
                  failed                        (terminal)
                    ↓
                (terminal)

    Only one experiment may be ``active`` at any time.
    ``completed`` and ``failed`` are terminal states.
    """

    def __init__(
        self,
        db: AsyncSession,
        experiment_log: ExperimentLog | None = None,
        audit_mgr: AuditTrailManager | None = None,
    ) -> None:
        self.db = db
        self.log = experiment_log or ExperimentLog()
        self.audit = audit_mgr or AuditTrailManager()

    async def create(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
        actor: str = "admin",
    ) -> Experiment:
        active = await self._get_active()
        if active:
            raise SingleActiveConstraintError(
                f"An experiment is already active (ID: {active.id}, "
                f"name: '{active.name}'). Complete it first."
            )

        experiment = Experiment(
            name=name,
            status=ExperimentStatus.ACTIVE.value,
            started_at=datetime.now(timezone.utc),
            metadata_=metadata or {},
        )
        self.db.add(experiment)
        try:
            await self.db.flush()
            await self.db.commit()
            await self.db.refresh(experiment)
        except IntegrityError as exc:
            await self.db.rollback()
            # Partial unique index uq_experiments_single_active or unique name
            active = await self._get_active()
            if active:
                raise SingleActiveConstraintError(
                    f"An experiment is already active (ID: {active.id}, "
                    f"name: '{active.name}'). Complete it first."
                ) from exc
            raise ExperimentError(
                f"Could not create experiment '{name}': name may already exist"
            ) from exc

        await self.audit.record(
            actor=actor,
            action="experiment.start",
            target_type="experiment",
            target_id=str(experiment.id),
            outcome="success",
            details={"name": name},
        )
        self.log.log_event(
            level="info",
            source="governance.experiment",
            message=f"Experiment '{name}' started (ID: {experiment.id})",
            metadata={"experiment_id": str(experiment.id)},
        )
        return experiment

    async def pause(
        self,
        experiment_id: uuid.UUID | None = None,
        actor: str = "admin",
    ) -> Experiment:
        experiment = await self._resolve(experiment_id)
        self._assert_not_terminal(experiment)
        if experiment.status != ExperimentStatus.ACTIVE.value:
            raise ExperimentError(
                f"Experiment '{experiment.name}' is not active (status: {experiment.status})"
            )
        experiment.status = ExperimentStatus.PAUSED.value
        experiment.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(experiment)

        await self.audit.record(
            actor=actor,
            action="experiment.pause",
            target_type="experiment",
            target_id=str(experiment.id),
            outcome="success",
        )
        self.log.log_event(
            level="info",
            source="governance.experiment",
            message=f"Experiment '{experiment.name}' paused",
            metadata={"experiment_id": str(experiment.id)},
        )
        return experiment

    async def resume(
        self,
        experiment_id: uuid.UUID | None = None,
        actor: str = "admin",
    ) -> Experiment:
        experiment = await self._resolve(experiment_id)
        self._assert_not_terminal(experiment)
        if experiment.status != ExperimentStatus.PAUSED.value:
            raise ExperimentError(
                f"Experiment '{experiment.name}' is not paused (status: {experiment.status})"
            )
        experiment.status = ExperimentStatus.ACTIVE.value
        experiment.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(experiment)

        await self.audit.record(
            actor=actor,
            action="experiment.resume",
            target_type="experiment",
            target_id=str(experiment.id),
            outcome="success",
        )
        self.log.log_event(
            level="info",
            source="governance.experiment",
            message=f"Experiment '{experiment.name}' resumed",
            metadata={"experiment_id": str(experiment.id)},
        )
        return experiment

    async def complete(
        self,
        experiment_id: uuid.UUID | None = None,
        actor: str = "admin",
    ) -> Experiment:
        experiment = await self._resolve(experiment_id)
        self._assert_not_terminal(experiment)
        now = datetime.now(timezone.utc)
        experiment.status = ExperimentStatus.COMPLETED.value
        experiment.ended_at = now
        if experiment.started_at:
            started = experiment.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            experiment.duration_seconds = int((now - started).total_seconds())
        experiment.updated_at = now
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(experiment)

        await self.audit.record(
            actor=actor,
            action="experiment.complete",
            target_type="experiment",
            target_id=str(experiment.id),
            outcome="success",
            details={"duration_seconds": experiment.duration_seconds},
        )
        duration_str = self._format_duration(experiment.duration_seconds)
        self.log.log_event(
            level="info",
            source="governance.experiment",
            message=f"Experiment '{experiment.name}' completed. Duration: {duration_str}.",
            metadata={
                "experiment_id": str(experiment.id),
                "duration_seconds": experiment.duration_seconds,
            },
        )
        return experiment

    async def fail(
        self,
        experiment_id: uuid.UUID | None = None,
        reason: str | None = None,
        actor: str = "admin",
    ) -> Experiment:
        experiment = await self._resolve(experiment_id)
        self._assert_not_terminal(experiment)
        now = datetime.now(timezone.utc)
        experiment.status = ExperimentStatus.FAILED.value
        experiment.ended_at = now
        if experiment.started_at:
            started = experiment.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            experiment.duration_seconds = int((now - started).total_seconds())
        experiment.updated_at = now
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(experiment)

        await self.audit.record(
            actor=actor,
            action="experiment.fail",
            target_type="experiment",
            target_id=str(experiment.id),
            outcome="failure",
            details={"reason": reason, "duration_seconds": experiment.duration_seconds},
        )
        self.log.log_event(
            level="warning",
            source="governance.experiment",
            message=f"Experiment '{experiment.name}' failed{f' ({reason})' if reason else ''}",
            metadata={
                "experiment_id": str(experiment.id),
                "reason": reason,
            },
        )
        return experiment

    async def add_metric(
        self,
        name: str,
        value: float,
        unit: str | None = None,
        tags: dict[str, str] | None = None,
        experiment_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        experiment = await self._resolve(experiment_id)
        validated = MetricObservationCreate(
            name=name,
            value=value,
            unit=unit,
            tags=tags,
            experiment_id=experiment_id or experiment.id,
        )
        metric = {
            "uuid": str(uuid.uuid4()),
            "experiment_id": str(experiment.id),
            "name": name,
            "value": value,
            "unit": unit,
            "tags": tags or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.log.log_metric(metric)

        await self.audit.record(
            actor="system",
            action="experiment.metric",
            target_type="experiment",
            target_id=str(experiment.id),
            outcome="success",
            details={"metric_name": name, "value": value},
        )
        return metric

    async def get(
        self, experiment_id: uuid.UUID
    ) -> Experiment | None:
        result = await self.db.execute(
            select(Experiment).where(Experiment.id == experiment_id)
        )
        return result.scalar_one_or_none()

    async def list_experiments(
        self,
        status: str | None = None,
        since: datetime | None = None,
        name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Experiment]:
        query = select(Experiment)
        if status:
            query = query.where(Experiment.status == status)
        if since:
            query = query.where(Experiment.created_at >= since)
        if name:
            query = query.where(Experiment.name.ilike(f"%{name}%"))
        query = query.order_by(Experiment.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_active(self) -> Experiment | None:
        return await self._get_active()

    async def _get_active(self) -> Experiment | None:
        result = await self.db.execute(
            select(Experiment).where(
                Experiment.status == ExperimentStatus.ACTIVE.value
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def _resolve(
        self, experiment_id: uuid.UUID | None = None
    ) -> Experiment:
        if experiment_id:
            experiment = await self.get(experiment_id)
        else:
            experiment = await self._get_active()
        if not experiment:
            raise ExperimentNotFoundError("No experiment found")
        return experiment

    def _assert_not_terminal(self, experiment: Experiment) -> None:
        if experiment.status in (
            ExperimentStatus.COMPLETED.value,
            ExperimentStatus.FAILED.value,
        ):
            raise TerminalStateError(
                f"Experiment '{experiment.name}' is in terminal state "
                f"({experiment.status}) and cannot be modified"
            )

    def _format_duration(self, seconds: int | None) -> str:
        if seconds is None:
            return "N/A"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"
