from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db
from app.governance.rule_manager import RuleManager
from app.schemas.shadow_telemetry import (
    AttributionReport,
    InteractionAnalysis,
    PromotionStateRecord,
)
from app.services.attribution_data_loader import (
    load_shadow_histories,
    records_from_histories,
)
from app.services.attribution_validation_service import AttributionValidationService

logger = logging.getLogger("app.routes.governance")

governance_router = APIRouter(prefix="/api/v1/governance", tags=["Governance"])

# Lifecycle rules permitted on promote/kill endpoints (audit H6 / store safety).
_PROMOTABLE_RULES = frozenset({"news_dedup", "sentiment_decay", "market_breadth"})
_SPRINT8_RULES = frozenset({"sentiment_decay", "market_breadth"})


def _require_api_key(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> bool:
    """Phase 0: open when API_KEY unset; otherwise require Bearer token."""
    return verify_api_key(authorization)


def _validate_rule_id(rule_id: str) -> str:
    rid = (rule_id or "").strip()
    if rid not in _PROMOTABLE_RULES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown or unsupported rule_id '{rule_id}'. "
                f"Allowed: {sorted(_PROMOTABLE_RULES)}"
            ),
        )
    return rid


class PromoteRequest(BaseModel):
    actor: str = "admin"
    reason: str = ""
    checklist_approved: bool = False  # safe default — must be explicit True
    attribution_report_approved: bool = False  # SC-001


class KillRequest(BaseModel):
    actor: str = "admin"
    reason: str = "Emergency performance degradation"


class PostPromotionVerifyRequest(BaseModel):
    baseline_false_positive_rate: float = Field(..., ge=0.0, le=1.0)
    live_false_positive_rate: float = Field(..., ge=0.0, le=1.0)
    max_fpr_increase: float = Field(default=0.02, ge=0.0, le=1.0)
    rule_id: str = "market_breadth"
    auto_kill: bool = False
    actor: str = "admin"


@governance_router.get("/attribution-report", response_model=AttributionReport)
async def get_attribution_report(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _auth: bool = Depends(_require_api_key),
) -> AttributionReport:
    """Generates the 4-way A/B ablation attribution report for shadow candidates."""
    try:
        histories = await load_shadow_histories(db, days=days)
        records, _, _ = records_from_histories(histories)
        report = AttributionValidationService.evaluate_ablation(records, days=days)
        logger.info(
            "attribution_report generated | days=%s | samples=%s | status=%s",
            days,
            report.total_samples,
            report.status,
        )
        return report
    except HTTPException:
        raise
    except Exception:
        logger.exception("attribution_report failed | days=%s", days)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate attribution report.",
        )


@governance_router.get("/interaction-check", response_model=InteractionAnalysis)
async def get_interaction_check(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _auth: bool = Depends(_require_api_key),
) -> InteractionAnalysis:
    """Correlation check between sentiment_decay and market_breadth with Go/No-Go."""
    try:
        histories = await load_shadow_histories(db, days=days)
        _, decay_deltas, breadth_contribs = records_from_histories(histories)
        analysis = AttributionValidationService.analyze_interaction(
            decay_deltas, breadth_contribs
        )
        logger.info(
            "interaction_check generated | days=%s | n=%s | class=%s | decay=%s | breadth=%s",
            days,
            len(decay_deltas),
            analysis.redundancy_classification,
            analysis.decay_promotion_recommendation,
            analysis.breadth_promotion_recommendation,
        )
        return analysis
    except HTTPException:
        raise
    except Exception:
        logger.exception("interaction_check failed | days=%s", days)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate interaction check.",
        )


@governance_router.post("/rules/{rule_id}/promote")
async def promote_rule(
    rule_id: str,
    body: PromoteRequest,
    _auth: bool = Depends(_require_api_key),
) -> dict[str, Any]:
    """Promote a shadow feature (checklist + SC-001 + FR-008 enforced in RuleManager)."""
    rule_id = _validate_rule_id(rule_id)
    mgr = RuleManager()
    prev_state = mgr.get_rule_state(rule_id)
    try:
        await mgr.promote_rule(
            rule_id=rule_id,
            checklist_approved=body.checklist_approved,
            reason=body.reason,
            actor=body.actor,
            attribution_report_approved=body.attribution_report_approved,
        )
        payload: dict[str, Any] = {
            "rule_id": rule_id,
            "previous_state": prev_state,
            "new_state": "production",
            "message": f"Rule '{rule_id}' promoted to production.",
        }
        if rule_id in _SPRINT8_RULES:
            record = PromotionStateRecord(
                rule_id=rule_id,
                stage="STAGE_2_BREADTH" if rule_id == "market_breadth" else "STAGE_1_DECAY",
                previous_state=prev_state,
                new_state="production",
                promoted_by=body.actor,
                attribution_report_approved=body.attribution_report_approved,
                kill_switch_active=False,
            )
            payload["promotion_record"] = record.model_dump(mode="json")
        logger.info(
            "rule_promoted | rule_id=%s | actor=%s | prev=%s | attribution_approved=%s",
            rule_id,
            body.actor,
            prev_state,
            body.attribution_report_approved,
        )
        return payload
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logger.exception("rule_promote_failed | rule_id=%s | actor=%s", rule_id, body.actor)
        raise HTTPException(status_code=500, detail="Failed to promote rule.")


@governance_router.post("/rules/{rule_id}/kill")
async def kill_rule(
    rule_id: str,
    body: KillRequest,
    _auth: bool = Depends(_require_api_key),
) -> dict[str, Any]:
    """Triggers immediate kill-switch for a feature, reverting to baseline scoring."""
    rule_id = _validate_rule_id(rule_id)
    mgr = RuleManager()
    prev_state = mgr.get_rule_state(rule_id)
    try:
        await mgr.kill_rule(
            rule_id=rule_id,
            reason=body.reason,
            actor=body.actor,
        )
        logger.info(
            "rule_killed | rule_id=%s | actor=%s | prev=%s | reason=%s",
            rule_id,
            body.actor,
            prev_state,
            body.reason,
        )
        return {
            "rule_id": rule_id,
            "previous_state": prev_state,
            "new_state": "disabled",
            "message": f"Rule '{rule_id}' killed. Reverted to baseline math.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logger.exception("rule_kill_failed | rule_id=%s | actor=%s", rule_id, body.actor)
        raise HTTPException(status_code=500, detail="Failed to kill rule.")


@governance_router.post("/post-promotion-verify")
async def post_promotion_verify(
    body: PostPromotionVerifyRequest,
    _auth: bool = Depends(_require_api_key),
) -> dict[str, Any]:
    """FR-010: verify live FPR vs baseline; optional auto kill-switch on failure."""
    rule_id = _validate_rule_id(body.rule_id)
    passed, rationale = AttributionValidationService.verify_post_promotion_quality(
        baseline_false_positive_rate=body.baseline_false_positive_rate,
        live_false_positive_rate=body.live_false_positive_rate,
        max_fpr_increase=body.max_fpr_increase,
    )
    killed = False
    kill_error: str | None = None
    if not passed and body.auto_kill:
        mgr = RuleManager()
        try:
            await mgr.kill_rule(
                rule_id=rule_id,
                reason=rationale or "Post-promotion quality verification failed",
                actor=body.actor,
            )
            killed = True
            logger.warning(
                "post_promotion_auto_kill | rule_id=%s | actor=%s | rationale=%s",
                rule_id,
                body.actor,
                rationale,
            )
        except Exception as e:
            kill_error = "Auto kill-switch failed; manual intervention required."
            logger.exception(
                "post_promotion_auto_kill_failed | rule_id=%s | error=%s",
                rule_id,
                e,
            )
    return {
        "passed": passed,
        "rationale": rationale,
        "auto_killed": killed,
        "rule_id": rule_id,
        "kill_error": kill_error,
    }
