from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.research import (
    ResearchSession,
    ResearchIdea,
    ResearchCritique,
    ResearchSynthesis,
    ResearchDecision,
    ResearchRolloutState,
)


class ResearchPersistenceService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_session(self, label: str, symbol: str | None = None, metadata: dict | None = None) -> ResearchSession:
        obj = ResearchSession(
            session_label=label,
            symbol=symbol,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def get_session(self, session_id: int) -> ResearchSession | None:
        return await self.db.get(ResearchSession, session_id)

    async def update_session_status(self, session_id: int, status: str, ended_at: datetime | None = None) -> None:
        obj = await self.db.get(ResearchSession, session_id)
        if obj:
            obj.status = status
            if ended_at is not None:
                obj.ended_at = ended_at

    async def create_idea(
        self,
        session_id: int,
        component_tag: str,
        title: str,
        situation_tags: list[str] | str,
        evidence_level: str,
        lifecycle_stage: str,
        bucket: str,
        required_data: dict | str,
        safe_fallback: str,
        rollback_criteria: dict | str,
        *,
        symbol: str | None = None,
        parent_idea_id: int | None = None,
        description: str | None = None,
        confidence_score: float | None = None,
    ) -> ResearchIdea:
        obj = ResearchIdea(
            session_id=session_id,
            parent_idea_id=parent_idea_id,
            symbol=symbol,
            component_tag=component_tag,
            title=title,
            description=description,
            situation_tags=json.dumps(situation_tags) if isinstance(situation_tags, (list, dict)) else situation_tags,
            evidence_level=evidence_level,
            lifecycle_stage=lifecycle_stage,
            bucket=bucket,
            required_data=json.dumps(required_data) if isinstance(required_data, dict) else required_data,
            safe_fallback=safe_fallback,
            rollback_criteria=json.dumps(rollback_criteria) if isinstance(rollback_criteria, dict) else rollback_criteria,
            confidence_score=confidence_score,
        )
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def get_idea(self, idea_id: int) -> ResearchIdea | None:
        return await self.db.get(ResearchIdea, idea_id)

    async def deactivate_idea(self, idea_id: int) -> None:
        obj = await self.db.get(ResearchIdea, idea_id)
        if obj:
            obj.is_active = False

    async def create_critique(
        self,
        idea_id: int,
        critique_type: str,
        content: str,
        *,
        severity: str = "MEDIUM",
    ) -> ResearchCritique:
        obj = ResearchCritique(
            idea_id=idea_id,
            critique_type=critique_type,
            content=content,
            severity=severity,
        )
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def resolve_critique(self, critique_id: int) -> None:
        obj = await self.db.get(ResearchCritique, critique_id)
        if obj:
            obj.resolved = True

    async def create_synthesis(
        self,
        session_id: int,
        title: str,
        synthesis_text: str,
        source_idea_ids: list[int],
        *,
        confidence_score: float | None = None,
    ) -> ResearchSynthesis:
        obj = ResearchSynthesis(
            session_id=session_id,
            title=title,
            synthesis_text=synthesis_text,
            source_idea_ids=json.dumps(source_idea_ids),
            confidence_score=confidence_score,
        )
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def get_synthesis(self, synthesis_id: int) -> ResearchSynthesis | None:
        return await self.db.get(ResearchSynthesis, synthesis_id)

    async def update_synthesis(
        self,
        synthesis_id: int,
        *,
        title: str | None = None,
        synthesis_text: str | None = None,
        source_idea_ids: list[int] | None = None,
        confidence_score: float | None = None,
        status: str | None = None,
    ) -> None:
        obj = await self.db.get(ResearchSynthesis, synthesis_id)
        if obj:
            if title is not None:
                obj.title = title
            if synthesis_text is not None:
                obj.synthesis_text = synthesis_text
            if source_idea_ids is not None:
                obj.source_idea_ids = json.dumps(source_idea_ids)
            if confidence_score is not None:
                obj.confidence_score = confidence_score
            if status is not None:
                obj.status = status

    async def create_decision(
        self,
        session_id: int,
        decision_type: str,
        rationale: str,
        *,
        synthesis_id: int | None = None,
        idea_id: int | None = None,
        status: str = "PENDING",
    ) -> ResearchDecision:
        obj = ResearchDecision(
            session_id=session_id,
            synthesis_id=synthesis_id,
            idea_id=idea_id,
            decision_type=decision_type,
            rationale=rationale,
            status=status,
        )
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def execute_decision(self, decision_id: int) -> None:
        obj = await self.db.get(ResearchDecision, decision_id)
        if obj:
            obj.status = "EXECUTED"
            obj.executed_at = datetime.now(timezone.utc)

    async def create_rollout_state(
        self,
        decision_id: int,
        rollout_phase: str,
        *,
        status: str = "PENDING",
        gating_checks_passed: bool | None = None,
    ) -> ResearchRolloutState:
        obj = ResearchRolloutState(
            decision_id=decision_id,
            rollout_phase=rollout_phase,
            status=status,
            gating_checks_passed=gating_checks_passed,
        )
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def advance_rollout_phase(
        self,
        rollout_id: int,
        status: str,
        *,
        observations: str | None = None,
        gating_checks_passed: bool | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        obj = await self.db.get(ResearchRolloutState, rollout_id)
        if obj:
            obj.status = status
            if observations is not None:
                obj.observations = observations
            if gating_checks_passed is not None:
                obj.gating_checks_passed = gating_checks_passed
            if completed_at is not None:
                obj.completed_at = completed_at
