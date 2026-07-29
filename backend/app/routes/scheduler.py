from fastapi import APIRouter, Header, Request, HTTPException
from fastapi.responses import JSONResponse
import logging
import os
import secrets
import time
from typing import Optional

from ..schemas import ScreenerRequest
from ..services.scan_execution_service import ScanExecutionService

router = APIRouter(prefix="/scheduler", tags=["scheduler"])
logger = logging.getLogger("app.routes.scheduler")

@router.post("/daily-scan")
async def daily_scan(
    payload: ScreenerRequest,
    request: Request,
    x_scheduler_secret: Optional[str] = Header(default=None, alias="X-Scheduler-Secret")
):
    source_ip = request.client.host if request.client else "unknown"
    timestamp = time.time()
    expected_secret = os.environ.get("SCHEDULER_SECRET")

    if x_scheduler_secret is None:
        logger.warning("SCHEDULER_AUTH_FAILURE | reason=missing_header | source_ip=%s | timestamp=%s", source_ip, timestamp)
        raise HTTPException(status_code=401, detail="Unauthorized")

    if expected_secret is None or not secrets.compare_digest(x_scheduler_secret, expected_secret):
        logger.warning("SCHEDULER_AUTH_FAILURE | reason=invalid_secret_or_unconfigured | source_ip=%s | timestamp=%s", source_ip, timestamp)
        raise HTTPException(status_code=403, detail="Forbidden")

    logger.info("SCHEDULER_AUTH_SUCCESS | source_ip=%s | timestamp=%s", source_ip, timestamp)
    logger.info("SCAN_TRIGGER_ACCEPTED | trigger_source=cron | endpoint=/scheduler/daily-scan")
    
    from ..services.lock_service import LockAcquisitionError
    
    try:
        await ScanExecutionService.execute_scan(
            payload=payload,
            progress_queue=None,
            trigger_source="cron",
            save_history=True,
        )
    except LockAcquisitionError:
        return JSONResponse(
            status_code=202,
            content={
                "status": "ignored",
                "reason": "scan_already_running"
            }
        )
    
    return JSONResponse(
        content={
            "status": "accepted",
            "message": "Daily scan triggered"
        },
        status_code=202
    )

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from ..db.session import get_db
from ..models.market_data import ScanSnapshot

@router.get("/status")
async def scheduler_status(db: AsyncSession = Depends(get_db)):
    stmt = select(ScanSnapshot).order_by(desc(ScanSnapshot.scan_timestamp)).limit(1)
    result = await db.execute(stmt)
    snapshot = result.scalar_one_or_none()

    if snapshot:
        # ScanSnapshot has no updated_at column; use scan_timestamp for completed time.
        completed_ts = None
        if snapshot.status in ("COMPLETED", "FAILED") and snapshot.scan_timestamp is not None:
            completed_ts = snapshot.scan_timestamp.isoformat()
        return {
            "last_scan_started": snapshot.scan_timestamp.isoformat() if snapshot.scan_timestamp else None,
            "last_scan_completed": completed_ts,
            "last_scan_status": snapshot.status,
            "duration_sec": snapshot.scan_duration_ms / 1000 if snapshot.scan_duration_ms else 0,
            "candidates_generated": (snapshot.buy_count or 0) + (snapshot.watch_count or 0),
        }

    # M2: under minimal writes, snapshots may be empty — fall back to canonical latest.
    from sqlalchemy import func
    from ..models.market_data import LatestScanResult

    max_scanned = await db.scalar(select(func.max(LatestScanResult.scanned_at)))
    if max_scanned is None:
        return JSONResponse(
            status_code=200,
            content={
                "last_scan_started": None,
                "last_scan_completed": None,
                "last_scan_status": "NONE",
                "duration_sec": 0,
                "candidates_generated": 0,
            },
        )

    count = await db.scalar(
        select(func.count(LatestScanResult.id)).where(
            LatestScanResult.scanned_at == max_scanned,
            LatestScanResult.signal_type.in_(("BUY", "WATCH")),
        )
    )
    ts = max_scanned.isoformat() if hasattr(max_scanned, "isoformat") else str(max_scanned)
    return {
        "last_scan_started": ts,
        "last_scan_completed": ts,
        "last_scan_status": "COMPLETED",
        "duration_sec": 0,
        "candidates_generated": int(count or 0),
    }
