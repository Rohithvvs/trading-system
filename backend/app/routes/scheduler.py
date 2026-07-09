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
            trigger_source="cron"
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
    
    if not snapshot:
        return JSONResponse(status_code=200, content={
            "last_scan_started": None,
            "last_scan_completed": None,
            "last_scan_status": "NONE",
            "duration_sec": 0,
            "candidates_generated": 0
        })
        
    return {
        "last_scan_started": snapshot.scan_timestamp.isoformat() if snapshot.scan_timestamp else None,
        "last_scan_completed": snapshot.updated_at.isoformat() if snapshot.status in ("COMPLETED", "FAILED") else None,
        "last_scan_status": snapshot.status,
        "duration_sec": snapshot.scan_duration_ms / 1000 if snapshot.scan_duration_ms else 0,
        "candidates_generated": (snapshot.buy_count or 0) + (snapshot.watch_count or 0)
    }
