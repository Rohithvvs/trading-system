"""Persist and query RE-001 Decision Objects."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...models.recommendation_engine import RecommendationEngineDecision
from ...schemas.re001 import Re001DecisionObject

logger = logging.getLogger("app.re001")


def persist_decision(
    db: Session,
    decision: Re001DecisionObject,
    *,
    mode: str = "swing",
) -> RecommendationEngineDecision | None:
    from ...config.settings import settings

    if not settings.re001_persist_decisions:
        return None
    try:
        explanation = decision.explanation
        if isinstance(explanation, dict):
            explanation = str(explanation)

        symbol = str(decision.symbol or "").strip().upper()
        row = RecommendationEngineDecision(
            recommendation_id=decision.recommendation_id,
            engine_id=decision.engine_id,
            engine_version=decision.engine_version,
            symbol=symbol,
            mode=mode,
            scan_run_id=decision.scan_run_id,
            analysis_history_id=decision.analysis_history_id,
            market_regime=decision.market_regime,
            trading_objective=decision.trading_objective,
            trading_style=decision.trading_style,
            strategy_family=decision.strategy_family,
            strategy_name=decision.strategy_name,
            recommendation_state=decision.recommendation_state,
            confidence_score=float(decision.confidence_score),
            risk_profile=decision.risk_profile if isinstance(decision.risk_profile, dict) else {"value": decision.risk_profile},
            portfolio_decision=(
                decision.portfolio_decision
                if isinstance(decision.portfolio_decision, dict)
                else {"value": decision.portfolio_decision}
            ),
            evidence=decision.evidence,
            explanation=str(explanation or ""),
            reason_codes=list(decision.reason_codes or []),
            trade_guidance=(
                decision.trade_guidance.model_dump() if decision.trade_guidance else None
            ),
            production_action=decision.production_action,
            production_score=decision.production_score,
            is_mismatch=decision.is_mismatch,
            evaluation_status=decision.evaluation_status,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        # Idempotent retries / concurrent double-write: return existing row.
        try:
            db.rollback()
        except Exception:
            pass
        existing = get_decision_by_id(db, decision.recommendation_id)
        if existing is not None:
            try:
                from .metrics import incr

                incr("persist_idempotent")
            except Exception:
                pass
            logger.info(
                "RE-001 persist idempotent | recommendation_id=%s | symbol=%s | scan_run_id=%s",
                decision.recommendation_id,
                decision.symbol,
                decision.scan_run_id,
            )
            return existing
        logger.warning(
            "RE-001 persist IntegrityError without existing row | recommendation_id=%s",
            decision.recommendation_id,
            exc_info=True,
        )
        return None
    except Exception as exc:
        logger.warning(
            "RE-001 persist failed | recommendation_id=%s | symbol=%s | scan_run_id=%s | err=%s",
            decision.recommendation_id,
            decision.symbol,
            decision.scan_run_id,
            exc,
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return None


def list_decisions_for_scan(db: Session, scan_run_id: str, *, engine_id: str = "RE-001") -> list[RecommendationEngineDecision]:
    return (
        db.query(RecommendationEngineDecision)
        .filter(
            RecommendationEngineDecision.scan_run_id == scan_run_id,
            RecommendationEngineDecision.engine_id == engine_id,
        )
        .order_by(RecommendationEngineDecision.symbol.asc())
        .all()
    )


def get_decision_by_id(db: Session, recommendation_id: str) -> RecommendationEngineDecision | None:
    return (
        db.query(RecommendationEngineDecision)
        .filter(RecommendationEngineDecision.recommendation_id == recommendation_id)
        .first()
    )


def get_latest_for_symbol(db: Session, symbol: str, *, engine_id: str = "RE-001") -> RecommendationEngineDecision | None:
    sym = str(symbol or "").strip().upper()
    return (
        db.query(RecommendationEngineDecision)
        .filter(
            RecommendationEngineDecision.symbol == sym,
            RecommendationEngineDecision.engine_id == engine_id,
        )
        .order_by(RecommendationEngineDecision.created_at.desc())
        .first()
    )


def row_to_decision_dict(row: RecommendationEngineDecision) -> dict[str, Any]:
    """Serialize Decision Object fields required for lab UI / FR-004 completeness."""
    return {
        "recommendation_id": row.recommendation_id,
        "engine_id": row.engine_id,
        "engine_version": row.engine_version,
        "symbol": row.symbol,
        "mode": row.mode,
        "scan_run_id": row.scan_run_id,
        "analysis_history_id": row.analysis_history_id,
        "market_regime": row.market_regime,
        "trading_objective": row.trading_objective,
        "trading_style": row.trading_style,
        "strategy_family": row.strategy_family,
        "strategy_name": row.strategy_name,
        "recommendation_state": row.recommendation_state,
        "confidence_score": row.confidence_score,
        "risk_profile": row.risk_profile,
        "portfolio_decision": row.portfolio_decision,
        "evidence": row.evidence,
        "explanation": row.explanation,
        "reason_codes": row.reason_codes,
        "trade_guidance": row.trade_guidance,
        "production_action": row.production_action,
        "production_score": row.production_score,
        "is_mismatch": row.is_mismatch,
        "evaluation_status": row.evaluation_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
