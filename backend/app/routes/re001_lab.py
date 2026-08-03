"""RE-001 Recommendation Lab read APIs."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..config.settings import settings
from ..core.deps import require_feature_sync
from ..db.session import get_sync_db
from ..schemas.re001 import (
    Re001ComparisonRow,
    Re001HealthSegment,
    Re001RecentScansResponse,
    Re001Registration,
    Re001ScanComparisonResponse,
    Re001ScanRunSummary,
)
from ..services.re001.analytics import re001_health_segment
from ..services.re001.lab_query import (
    list_recent_scan_runs,
    query_decision,
    query_latest_symbol,
    query_scan_comparison,
)
from ..services.re001.metrics import snapshot as re001_metrics_snapshot
from ..services.re001.registry import get_re001_registration

router = APIRouter(prefix="/api/v1/recommendation-lab", tags=["recommendation-lab"])

# Bound path identifiers so lab read APIs reject oversized / hostile tokens early.
_SCAN_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")
_RECOMMENDATION_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-]{1,32}$")


def _lab_access():
    """Feature permission + RE001_UI_ENABLED kill-switch (default True)."""

    def _dep(_principal=Depends(require_feature_sync("recommendation_lab"))):
        if not bool(getattr(settings, "re001_ui_enabled", True)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="RE-001 lab UI is disabled (RE001_UI_ENABLED=false)",
            )
        return _principal

    return _dep


def _require_scan_run_id(scan_run_id: str) -> str:
    s = (scan_run_id or "").strip()
    if not s or not _SCAN_RUN_ID_RE.match(s):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid scan_run_id",
        )
    return s


def _require_recommendation_id(recommendation_id: str) -> str:
    s = (recommendation_id or "").strip()
    if not s or not _RECOMMENDATION_ID_RE.match(s):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid recommendation_id",
        )
    return s


def _require_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s or not _SYMBOL_RE.match(s):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid symbol",
        )
    return s


@router.get("/registration", response_model=Re001Registration)
def get_registration(
    _=Depends(_lab_access()),
) -> Re001Registration:
    return get_re001_registration()


@router.get("/scans/recent", response_model=Re001RecentScansResponse)
def get_recent_scans(
    limit: int = Query(default=20, ge=1, le=100),
    _=Depends(_lab_access()),
    db: Session = Depends(get_sync_db),
) -> Re001RecentScansResponse:
    items = [Re001ScanRunSummary(**row) for row in list_recent_scan_runs(db, limit=limit)]
    return Re001RecentScansResponse(items=items)


@router.get("/scans/{scan_run_id}/comparison", response_model=Re001ScanComparisonResponse)
def get_scan_comparison(
    scan_run_id: str,
    _=Depends(_lab_access()),
    db: Session = Depends(get_sync_db),
) -> Re001ScanComparisonResponse:
    scan_run_id = _require_scan_run_id(scan_run_id)
    rows = query_scan_comparison(db, scan_run_id)
    items = [
        Re001ComparisonRow(
            symbol=str(r.get("symbol") or ""),
            recommendation_id=str(r.get("recommendation_id") or ""),
            production_action=r.get("production_action"),
            production_score=r.get("production_score"),
            re001_state=r.get("recommendation_state") or "REJECT",  # type: ignore[arg-type]
            confidence_score=float(r.get("confidence_score") or 0.0),
            strategy_name=r.get("strategy_name"),
            strategy_family=r.get("strategy_family"),
            is_mismatch=r.get("is_mismatch"),
        )
        for r in rows
    ]
    return Re001ScanComparisonResponse(scan_run_id=scan_run_id, items=items)


@router.get("/decisions/{recommendation_id}")
def get_decision_detail(
    recommendation_id: str,
    _=Depends(_lab_access()),
    db: Session = Depends(get_sync_db),
) -> dict:
    recommendation_id = _require_recommendation_id(recommendation_id)
    row = query_decision(db, recommendation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")
    return row


@router.get("/symbols/{symbol}/latest")
def get_symbol_latest(
    symbol: str,
    _=Depends(_lab_access()),
    db: Session = Depends(get_sync_db),
) -> dict:
    symbol = _require_symbol(symbol)
    row = query_latest_symbol(db, symbol)
    if not row:
        raise HTTPException(status_code=404, detail="No RE-001 decision for symbol")
    return row


@router.get("/health", response_model=Re001HealthSegment)
def get_re001_health(
    days: int = Query(default=7, ge=1, le=90),
    _=Depends(_lab_access()),
    db: Session = Depends(get_sync_db),
) -> Re001HealthSegment:
    seg = re001_health_segment(db, days=days)
    seg.runtime_counters = re001_metrics_snapshot()
    return seg
