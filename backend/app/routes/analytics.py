from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from ..core.security import verify_api_key
from ..db.session import get_db
from ..governance.rule_governance import evaluate_all_promoted_rules
from ..models.analysis import AnalysisHistory
from ..schemas.governance import (
    EngineHealthResponse,
    RuleGovernanceResponse,
    ShadowStatusResponse,
    ShadowStatusRuleItem,
)

logger = logging.getLogger("app.routes.analytics")


def _require_api_key(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> bool:
    """Phase 0 operator auth: open when API_KEY unset; else require Bearer token."""
    return verify_api_key(authorization)


router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["analytics"],
    dependencies=[Depends(_require_api_key)],
)

ACTIVE_SHADOW_RULES = ["news_dedup", "sentiment_decay", "market_breadth", "sector_strength"]


def _compact_shadow_summary(rule: str, payload: Any) -> Dict[str, Any]:
    """Build a small summary of latest shadow output for operators."""
    if not isinstance(payload, dict):
        return {"present": True}
    summary: Dict[str, Any] = {}
    for key in (
        "status",
        "executed_at",
        "benchmark_symbol",
        "benchmark_return_pct",
        "original_news_count",
        "kept_news_count",
        "removed_news_count",
        "breadth_percentage",
        "regime_label",
        "soft_score_contribution",
        "is_valid",
        "aggregate_decayed_score",
        "false_positive",
        "outcome",
    ):
        if key in payload:
            summary[key] = payload[key]
    if rule == "sector_strength" and isinstance(payload.get("sectors"), list):
        summary["sector_count"] = len(payload["sectors"])
        labels: Dict[str, int] = {}
        for item in payload["sectors"]:
            if isinstance(item, dict):
                label = str(item.get("label") or "unknown")
                labels[label] = labels.get(label, 0) + 1
        if labels:
            summary["label_counts"] = labels
    if not summary:
        summary["keys"] = list(payload.keys())[:12]
    return summary


async def _db_dialect_name(db: AsyncSession) -> str:
    """Resolve SQL dialect for portable JSON key predicates."""
    try:
        bind = db.get_bind()
        if bind is not None:
            return getattr(getattr(bind, "dialect", None), "name", "") or "unknown"
    except Exception:
        pass
    try:
        conn = await db.connection()
        return conn.dialect.name
    except Exception:
        return "unknown"


def _json_key_present(key: str, dialect: str) -> ColumnElement[bool]:
    """True when shadow_outputs contains top-level JSON key (PG JSONB or SQLite JSON)."""
    col = AnalysisHistory.shadow_outputs
    if dialect == "postgresql":
        # JSONB has_key — index-friendly when GIN exists; still set-based aggregation.
        return col.has_key(key)  # type: ignore[attr-defined]
    # SQLite / generic: json_extract returns NULL when path missing.
    return func.json_extract(col, f"$.{key}").is_not(None)


def _rule_match_predicate(rule: str, dialect: str) -> ColumnElement[bool]:
    """SQL predicate matching how shadow-status counts executions for a rule."""
    if rule == "news_dedup":
        return or_(
            _json_key_present("news_dedup", dialect),
            _json_key_present("original_news_count", dialect),
            _json_key_present("kept_news_count", dialect),
        )
    return _json_key_present(rule, dialect)


@router.get("/engine-health", response_model=EngineHealthResponse)
async def get_engine_health(db: AsyncSession = Depends(get_db)) -> EngineHealthResponse:
    """GET /api/v1/analytics/engine-health

    Returns rolling 7-day operational performance metrics for the Recommendation Engine.
    Uses SQL aggregation (no full-row hydrate) for scale.
    """
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=7)
    window = AnalysisHistory.created_at >= start_date
    t0 = time.perf_counter()

    try:
        total_recommendations = int(
            await db.scalar(select(func.count()).select_from(AnalysisHistory).where(window))
            or 0
        )
        # Distinct stocks analyzed in window — proxy for scan coverage (not row count).
        total_scans = int(
            await db.scalar(
                select(func.count(func.distinct(AnalysisHistory.stock_id))).where(window)
            )
            or 0
        )

        signal_dist = {"BUY": 0, "SELL": 0, "HOLD": 0}
        dist_rows = (
            await db.execute(
                select(AnalysisHistory.recommendation, func.count())
                .where(window)
                .group_by(AnalysisHistory.recommendation)
            )
        ).all()
        for rec, cnt in dist_rows:
            key = (rec or "").upper()
            if key in signal_dist:
                signal_dist[key] = int(cnt)

        avg_confidence = await db.scalar(
            select(func.avg(AnalysisHistory.confidence)).where(window)
        )
        average_confidence_score = (
            round(float(avg_confidence), 2) if avg_confidence is not None else 0.0
        )

        # Positive outcome rate among BUY rows with a backtest score.
        buy_with_outcome = int(
            await db.scalar(
                select(func.count())
                .select_from(AnalysisHistory)
                .where(
                    window,
                    AnalysisHistory.recommendation == "BUY",
                    AnalysisHistory.backtest_score.is_not(None),
                )
            )
            or 0
        )
        positive_outcome_rate: Optional[float] = None
        if buy_with_outcome > 0:
            positive_buys = int(
                await db.scalar(
                    select(func.count())
                    .select_from(AnalysisHistory)
                    .where(
                        window,
                        AnalysisHistory.recommendation == "BUY",
                        AnalysisHistory.backtest_score.is_not(None),
                        AnalysisHistory.backtest_score > 0,
                    )
                )
                or 0
            )
            positive_outcome_rate = round(positive_buys / buy_with_outcome, 4)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if elapsed_ms >= 2000.0:
            logger.warning(
                "engine_health_slow | elapsed_ms=%.1f | recs=%s | scans=%s",
                elapsed_ms,
                total_recommendations,
                total_scans,
            )
        else:
            logger.info(
                "engine_health_ok | elapsed_ms=%.1f | recs=%s | scans=%s",
                elapsed_ms,
                total_recommendations,
                total_scans,
            )

        return EngineHealthResponse(
            window_days=7,
            total_scans=total_scans,
            total_recommendations=total_recommendations,
            signal_distribution=signal_dist,
            positive_outcome_rate=positive_outcome_rate,
            average_confidence_score=average_confidence_score,
            generated_at=now.isoformat(),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "engine_health_failed | elapsed_ms=%.1f",
            (time.perf_counter() - t0) * 1000.0,
        )
        # Safe fallback: never 500 on aggregation failure — operators still get a schema.
        return EngineHealthResponse(
            window_days=7,
            total_scans=0,
            total_recommendations=0,
            signal_distribution={"BUY": 0, "SELL": 0, "HOLD": 0},
            positive_outcome_rate=None,
            average_confidence_score=0.0,
            generated_at=now.isoformat(),
        )


@router.get("/shadow-status", response_model=ShadowStatusResponse)
async def get_shadow_status(db: AsyncSession = Depends(get_db)) -> ShadowStatusResponse:
    """GET /api/v1/analytics/shadow-status

    Returns operational telemetry for all active watch-only shadow rules.

    Spec edge (large volumes): uses SQL-side key presence counts + one latest-row
    fetch per rule (no full-window JSON hydrate into Python).
    """
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=7)
    window = and_(
        AnalysisHistory.created_at >= start_date,
        AnalysisHistory.shadow_outputs.is_not(None),
    )
    t0 = time.perf_counter()

    rules_telemetry: Dict[str, ShadowStatusRuleItem] = {
        r: ShadowStatusRuleItem(status="active", total_executions_7d=0, last_executed_at=None)
        for r in ACTIVE_SHADOW_RULES
    }

    try:
        dialect = await _db_dialect_name(db)

        for rule in ACTIVE_SHADOW_RULES:
            match_pred = _rule_match_predicate(rule, dialect)
            total = int(
                await db.scalar(
                    select(func.count())
                    .select_from(AnalysisHistory)
                    .where(window, match_pred)
                )
                or 0
            )
            item = rules_telemetry[rule]
            item.total_executions_7d = total

            if total <= 0:
                continue

            # Latest matching row only — for last_executed_at + output summary.
            latest = (
                await db.execute(
                    select(AnalysisHistory.created_at, AnalysisHistory.shadow_outputs)
                    .where(window, match_pred)
                    .order_by(AnalysisHistory.created_at.desc())
                    .limit(1)
                )
            ).first()
            if not latest:
                continue

            created_at, so = latest
            if created_at is not None:
                created = created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                item.last_executed_at = created.isoformat()

            payload: Any = None
            if isinstance(so, dict):
                if rule in so:
                    payload = so.get(rule)
                elif rule == "news_dedup":
                    payload = {
                        "original_news_count": so.get("original_news_count"),
                        "kept_news_count": so.get("kept_news_count"),
                        "status": "success",
                    }

            if isinstance(payload, dict):
                item.last_status = str(payload.get("status") or "success")
                item.last_output_summary = _compact_shadow_summary(rule, payload)
            else:
                item.last_status = "success"
                item.last_output_summary = {"present": True}

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if elapsed_ms >= 2000.0:
            logger.warning(
                "shadow_status_slow | elapsed_ms=%.1f | dialect=%s | mode=sql_agg",
                elapsed_ms,
                dialect,
            )
        else:
            logger.info(
                "shadow_status_ok | elapsed_ms=%.1f | dialect=%s | mode=sql_agg",
                elapsed_ms,
                dialect,
            )

        return ShadowStatusResponse(
            active_shadow_rules=list(ACTIVE_SHADOW_RULES),
            rules_telemetry=rules_telemetry,
            generated_at=now.isoformat(),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "shadow_status_failed | elapsed_ms=%.1f",
            (time.perf_counter() - t0) * 1000.0,
        )
        return ShadowStatusResponse(
            active_shadow_rules=list(ACTIVE_SHADOW_RULES),
            rules_telemetry=rules_telemetry,
            generated_at=now.isoformat(),
        )


@router.get("/rule-governance", response_model=RuleGovernanceResponse)
async def get_rule_governance(db: AsyncSession = Depends(get_db)) -> RuleGovernanceResponse:
    """GET /api/v1/analytics/rule-governance

    Returns 30-day health status evaluations for all promoted production rules.
    """
    t0 = time.perf_counter()
    try:
        response = await evaluate_all_promoted_rules(db)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if elapsed_ms >= 2000.0:
            logger.warning(
                "rule_governance_endpoint_slow | elapsed_ms=%.1f | rules=%s",
                elapsed_ms,
                response.promoted_rules_count,
            )
        else:
            logger.info(
                "rule_governance_endpoint_ok | elapsed_ms=%.1f | rules=%s",
                elapsed_ms,
                response.promoted_rules_count,
            )
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "rule_governance_endpoint_failed | elapsed_ms=%.1f",
            (time.perf_counter() - t0) * 1000.0,
        )
        now = datetime.now(timezone.utc).isoformat()
        # evaluate_all already fail-softs; this is a last-resort shape-preserving response.
        return RuleGovernanceResponse(
            evaluated_at=now,
            promoted_rules_count=0,
            rules=[],
        )
