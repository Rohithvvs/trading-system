"""RE-001 health metrics from decisions table."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ...models.recommendation_engine import RecommendationEngineDecision
from ...schemas.re001 import Re001HealthSegment


def re001_health_segment(db: Session, *, days: int = 7) -> Re001HealthSegment:
    """Aggregate RE-001 decision health without loading all rows into memory."""
    start = datetime.now(timezone.utc) - timedelta(days=max(1, int(days or 7)))
    state = func.upper(RecommendationEngineDecision.recommendation_state)
    eval_status = func.lower(RecommendationEngineDecision.evaluation_status)

    row = (
        db.query(
            func.count(RecommendationEngineDecision.id).label("total"),
            func.coalesce(
                func.sum(case((state == "BUY", 1), else_=0)),
                0,
            ).label("buy_count"),
            func.coalesce(
                func.sum(case((state == "WATCH", 1), else_=0)),
                0,
            ).label("watch_count"),
            func.coalesce(
                func.sum(case((state == "REJECT", 1), else_=0)),
                0,
            ).label("reject_count"),
            func.coalesce(
                func.sum(case((eval_status == "error", 1), else_=0)),
                0,
            ).label("error_count"),
            func.coalesce(
                func.sum(case((eval_status == "timeout", 1), else_=0)),
                0,
            ).label("timeout_count"),
            func.coalesce(
                func.sum(
                    case(
                        (RecommendationEngineDecision.is_mismatch.is_(True), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("mismatch_count"),
        )
        .filter(
            RecommendationEngineDecision.engine_id == "RE-001",
            RecommendationEngineDecision.created_at >= start,
        )
        .one()
    )

    seg = Re001HealthSegment(
        total=int(row.total or 0),
        buy_count=int(row.buy_count or 0),
        watch_count=int(row.watch_count or 0),
        reject_count=int(row.reject_count or 0),
        error_count=int(row.error_count or 0),
        timeout_count=int(row.timeout_count or 0),
        mismatch_count=int(row.mismatch_count or 0),
    )
    try:
        from .metrics import snapshot as re001_metrics_snapshot

        seg.runtime_counters = re001_metrics_snapshot()
    except Exception:
        seg.runtime_counters = None
    return seg
