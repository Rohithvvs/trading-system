from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from ..core.security import verify_api_key
from ..observability.dashboard import DashboardProvider
from ..observability.schema import LogEventCreate, LogFilterParams, AlertFilterParams

logger = logging.getLogger(__name__)


def _require_api_key(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> bool:
    """Inject Authorization header into verify_api_key."""
    return verify_api_key(authorization)


router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["diagnostics"],
    dependencies=[Depends(_require_api_key)],
)

_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_MAX = 60
_RATE_LIMIT_WINDOW = 60.0
_RATE_LIMIT_PRUNE_INTERVAL = 300.0
_last_prune = 0.0


def _prune_rate_limit_store() -> None:
    global _last_prune
    now = time.monotonic()
    if now - _last_prune < _RATE_LIMIT_PRUNE_INTERVAL:
        return
    _last_prune = now
    window_start = now - _RATE_LIMIT_WINDOW
    empty_keys = [
        ip for ip, ts in _rate_limit_store.items()
        if not ts or all(t <= window_start for t in ts)
    ]
    for key in empty_keys:
        del _rate_limit_store[key]


def _check_rate_limit(request: Request) -> None:
    _prune_rate_limit_store()
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - _RATE_LIMIT_WINDOW
    timestamps = _rate_limit_store[client_ip]
    timestamps[:] = [t for t in timestamps if t > window_start]
    if len(timestamps) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
        )
    timestamps.append(now)


_dashboard_singleton: DashboardProvider | None = None


def get_dashboard() -> DashboardProvider:
    global _dashboard_singleton
    if _dashboard_singleton is None:
        _dashboard_singleton = DashboardProvider()
    return _dashboard_singleton


@router.get("/metrics")
async def get_metrics(
    dashboard: DashboardProvider = Depends(get_dashboard),
) -> dict[str, Any]:
    experiment_data: dict[str, Any] | None = None
    try:
        from ..db.session import AsyncSessionLocal
        from ..governance.experiment import ExperimentService
        from ..governance.experiment_log import ExperimentLog
        from ..governance.audit import AuditTrailManager

        async with AsyncSessionLocal() as db:
            svc = ExperimentService(db, experiment_log=ExperimentLog(), audit_mgr=AuditTrailManager())
            active = await svc.get_active()
            if active:
                experiment_data = {
                    "id": str(active.id),
                    "name": active.name,
                }
    except Exception as e:
        logger.warning("Failed to query active experiment for dashboard: %s", e)
    return dashboard.get_metrics(experiment_data=experiment_data)


@router.get("/logs")
async def get_logs(
    level: str | None = Query(None),
    source: str | None = Query(None),
    start_time: str | None = Query(None),
    end_time: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    dashboard: DashboardProvider = Depends(get_dashboard),
) -> dict[str, Any]:
    params = LogFilterParams(
        level=level,
        source=source,
        start_time=(
            datetime.fromisoformat(start_time) if start_time else None
        ),
        end_time=(
            datetime.fromisoformat(end_time) if end_time else None
        ),
        limit=limit,
        offset=offset,
    )
    return dashboard.get_logs(
        level=params.level.value if params.level else None,
        source=params.source,
        start_time=params.start_time,
        end_time=params.end_time,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/alerts")
async def get_alerts(
    severity: str | None = Query(None),
    since: str | None = Query(None),
    dashboard: DashboardProvider = Depends(get_dashboard),
) -> dict[str, Any]:
    params = AlertFilterParams(
        severity=severity,
        since=(
            datetime.fromisoformat(since) if since else None
        ),
    )
    return dashboard.get_alerts(
        severity=params.severity.value if params.severity else None,
        since=params.since,
    )


@router.post("/logs/ingest", status_code=201)
async def ingest_log(
    request: Request,
    event: LogEventCreate,
    dashboard: DashboardProvider = Depends(get_dashboard),
    _rate_limited: None = Depends(_check_rate_limit),
) -> dict[str, str]:
    log_event = dashboard.log_aggregator.ingest(event)
    return {"status": "accepted", "uuid": str(log_event.uuid)}


@router.get("/metrics/prometheus")
async def prometheus_metrics(
    dashboard: DashboardProvider = Depends(get_dashboard),
) -> dict[str, Any]:
    snapshot = dashboard.tracker.get_snapshot()
    return {
        "trading_cpu_percent": snapshot["cpu_percent"],
        "trading_memory_percent": snapshot["memory_percent"],
        "trading_memory_used_mb": snapshot["memory_used_mb"],
    }