"""Lab query helpers for RE-001 decisions."""

from __future__ import annotations

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ...models.recommendation_engine import RecommendationEngineDecision
from .persistence import (
    get_decision_by_id,
    get_latest_for_symbol,
    list_decisions_for_scan,
    row_to_decision_dict,
)


def query_scan_comparison(db: Session, scan_run_id: str) -> list[dict]:
    rows = list_decisions_for_scan(db, scan_run_id)
    return [row_to_decision_dict(r) for r in rows]


def query_decision(db: Session, recommendation_id: str) -> dict | None:
    row = get_decision_by_id(db, recommendation_id)
    return row_to_decision_dict(row) if row else None


def query_latest_symbol(db: Session, symbol: str) -> dict | None:
    row = get_latest_for_symbol(db, symbol)
    return row_to_decision_dict(row) if row else None


def list_recent_scan_runs(db: Session, *, limit: int = 20, engine_id: str = "RE-001") -> list[dict]:
    q = (
        db.query(
            RecommendationEngineDecision.scan_run_id,
            func.count(RecommendationEngineDecision.id).label("decision_count"),
            func.max(RecommendationEngineDecision.created_at).label("latest_created_at"),
        )
        .filter(
            RecommendationEngineDecision.engine_id == engine_id,
            RecommendationEngineDecision.scan_run_id.isnot(None),
        )
        .group_by(RecommendationEngineDecision.scan_run_id)
        .order_by(desc("latest_created_at"))
        .limit(limit)
    )
    out: list[dict] = []
    for scan_run_id, count, latest in q.all():
        if not scan_run_id:
            continue
        out.append(
            {
                "scan_run_id": str(scan_run_id),
                "decision_count": int(count or 0),
                "latest_created_at": latest.isoformat() if latest else None,
            }
        )
    return out
