"""Isolated RE-001 runner — fail-open relative to production (async-safe)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from ...config.settings import settings
from ...schemas.re001 import Re001DecisionObject
from .context import LabExecutionContext, build_lab_context
from .decision_builder import build_decision_object
from .engine import evaluate_re001
from .metrics import incr, snapshot as metrics_snapshot
from .persistence import persist_decision
from .registry import get_re001_registration, is_re001_active
from .scan_context import get_scan_run_id

logger = logging.getLogger("app.re001")


def _evaluate_sync(ctx: LabExecutionContext) -> Re001DecisionObject:
    result = evaluate_re001(ctx)
    return build_decision_object(ctx, result)


def _diagnostic_decision(
    ctx: LabExecutionContext,
    *,
    status: str,
    reason: str,
    message: str,
) -> Re001DecisionObject:
    reg = get_re001_registration()
    return Re001DecisionObject(
        recommendation_id=str(uuid.uuid4()),
        engine_id="RE-001",
        engine_version=reg.engine_version,
        market_regime="UNKNOWN",
        recommendation_state="REJECT",
        confidence_score=0.0,
        risk_profile={"mode": "diagnostic"},
        portfolio_decision={"status": "skipped"},
        evidence={"diagnostic": status, "reason": reason},
        explanation=message,
        reason_codes=[reason],
        symbol=ctx.symbol,
        scan_run_id=ctx.scan_run_id,
        analysis_history_id=ctx.analysis_history_id,
        evaluation_status=status,  # type: ignore[arg-type]
        timestamp=datetime.now(timezone.utc),
    )


def _persist_safe(
    decision: Re001DecisionObject,
    *,
    mode: str,
    db_session_factory: Any | None,
) -> None:
    if not settings.re001_persist_decisions or db_session_factory is None:
        return
    try:
        db = db_session_factory()
        try:
            row = persist_decision(db, decision, mode=mode)
            if row is not None:
                incr("persist_ok")
            else:
                incr("persist_fail")
        finally:
            db.close()
    except Exception as exc:
        incr("persist_fail")
        logger.warning("RE-001 persist session failed | %s", exc, exc_info=True)


def _build_context(**kwargs: Any) -> LabExecutionContext:
    scan_run_id = kwargs.pop("scan_run_id", None) or get_scan_run_id()
    return build_lab_context(scan_run_id=scan_run_id, **kwargs)


async def run_re001_isolated_async(
    *,
    symbol: str,
    mode: str = "swing",
    scan_run_id: str | None = None,
    candles: list[Any] | None = None,
    technical_results: list[Any] | None = None,
    sentiment_score: float = 0.0,
    fundamental_result: Any | None = None,
    backtests: list[Any] | None = None,
    production_recommendation: Any | None = None,
    market_regime: Any | None = None,
    sector_overlay: Any | None = None,
    market_breadth_soft_score: float | None = None,
    user_portfolio: dict[str, Any] | None = None,
    risk_settings: dict[str, Any] | None = None,
    analysis_history_id: int | None = None,
    db_session_factory: Any | None = None,
) -> Re001DecisionObject | None:
    """Async RE-001 entry: never raises into production path; does not block event loop."""
    if not is_re001_active():
        return None

    reg = get_re001_registration()
    timeout_ms = float(getattr(settings, "re001_timeout_ms", 3000) or 3000)
    timeout_s = max(0.2, timeout_ms / 1000.0)

    ctx = _build_context(
        symbol=symbol,
        mode=mode,
        scan_run_id=scan_run_id,
        candles=candles,
        technical_results=technical_results,
        sentiment_score=sentiment_score,
        fundamental_result=fundamental_result,
        backtests=backtests,
        production_recommendation=production_recommendation,
        market_regime=market_regime,
        sector_overlay=sector_overlay,
        market_breadth_soft_score=market_breadth_soft_score,
        user_portfolio=user_portfolio,
        risk_settings=risk_settings,
        analysis_history_id=analysis_history_id,
    )

    logger.info(
        "RE-001 start | symbol=%s | stage=%s | version=%s | scan_run_id=%s | analysis_history_id=%s",
        symbol,
        reg.stage,
        reg.engine_version,
        ctx.scan_run_id,
        ctx.analysis_history_id,
    )
    incr("runs")
    t0 = time.perf_counter()
    decision: Re001DecisionObject | None = None
    try:
        decision = await asyncio.wait_for(
            asyncio.to_thread(_evaluate_sync, ctx),
            timeout=timeout_s,
        )
        incr("success")
        state = (decision.recommendation_state or "").lower()
        if state in {"buy", "watch", "reject"}:
            incr(state)
    except TimeoutError:
        incr("timeout")
        logger.warning(
            "RE-001 timeout | symbol=%s | scan_run_id=%s | timeout_s=%.2f",
            symbol,
            ctx.scan_run_id,
            timeout_s,
        )
        decision = _diagnostic_decision(
            ctx,
            status="timeout",
            reason="re001_timeout",
            message=f"RE-001 evaluation timed out after {timeout_s:.2f}s",
        )
        _persist_safe(decision, mode=mode, db_session_factory=db_session_factory)
        return decision
    except Exception as exc:
        incr("error")
        logger.warning(
            "RE-001 error | symbol=%s | scan_run_id=%s | err=%s",
            symbol,
            ctx.scan_run_id,
            exc,
            exc_info=True,
        )
        decision = _diagnostic_decision(
            ctx,
            status="error",
            reason="re001_error",
            message=f"RE-001 evaluation error: {exc}",
        )
        _persist_safe(decision, mode=mode, db_session_factory=db_session_factory)
        return decision
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "RE-001 complete | symbol=%s | scan_run_id=%s | state=%s | status=%s | elapsed_ms=%.1f | metrics=%s",
            symbol,
            ctx.scan_run_id,
            getattr(decision, "recommendation_state", None),
            getattr(decision, "evaluation_status", None),
            elapsed_ms,
            metrics_snapshot(),
        )

    if decision is None:
        return None

    _persist_safe(decision, mode=mode, db_session_factory=db_session_factory)
    return decision


def run_re001_isolated(**kwargs: Any) -> Re001DecisionObject | None:
    """Sync wrapper for tests/scripts. Prefer run_re001_isolated_async in async code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        # Called from async context incorrectly — still fail-open via thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(lambda: asyncio.run(run_re001_isolated_async(**kwargs)))
            try:
                return fut.result(timeout=max(1.0, float(getattr(settings, "re001_timeout_ms", 3000) or 3000) / 1000.0 + 1.0))
            except Exception as exc:
                logger.warning("RE-001 sync-wrapper failed | %s", exc, exc_info=True)
                return None
    return asyncio.run(run_re001_isolated_async(**kwargs))
