from fastapi import APIRouter, Header, Request, HTTPException, Query
from fastapi.responses import JSONResponse
import asyncio
import logging
import os
import secrets
import time
from typing import Optional

from ..schemas import AnalysisMode, ScreenerRequest, TimeframeConfig
from ..services.scan_execution_service import ScanExecutionService

router = APIRouter(prefix="/scheduler", tags=["scheduler"])
logger = logging.getLogger("backend.app.routes.scheduler")


def _build_default_scanner_request() -> ScreenerRequest:
    return ScreenerRequest(
        mode=AnalysisMode.swing,
        timeframe=TimeframeConfig(
            intraday="5m",
            swing="1d",
            lookback_window=260,
        ),
        symbols=[],
        top_n=20,
    )


def _cron_scanner_response(scan_id: str, result: dict) -> dict:
    shortlisted = result.get("shortlisted_symbols") or []
    buy_candidates = result.get("buy_candidate_symbols") or []
    watch_candidates = result.get("watch_candidate_symbols") or []
    matched = result.get("matched_symbols") or []
    eligible = result.get("eligible_symbols") or []

    return {
        "success": True,
        "message": "Scanner executed successfully",
        "scan_id": scan_id,
        "scanned_symbols": result.get("scanned_symbols", 0),
        "shortlisted_count": len(shortlisted),
        "metadata": {
            "data_source": result.get("data_source"),
            "data_warning": result.get("data_warning"),
            "screener_name": result.get("screener_name"),
            "scanned_at": result.get("scanned_at"),
            "last_scan_completed_at": result.get("last_scan_completed_at"),
            "eligible_count": len(eligible),
            "matched_count": len(matched),
            "buy_count": len(buy_candidates),
            "watch_count": len(watch_candidates),
            "stopped_at_stage": result.get("stopped_at_stage"),
            "duplicate_symbols_skipped": result.get("duplicate_symbols_skipped", 0),
            "market_context": result.get("market_context", {}),
            "scan_stages": result.get("scan_stages", []),
        },
    }


@router.get("/run-scanner")
async def run_scanner(
    request: Request,
    key: Optional[str] = Query(default=None),
):
    source_ip = request.client.host if request.client else "unknown"
    triggered_at = time.time()
    started_perf = time.perf_counter()
    expected_secret = os.environ.get("CRON_SECRET")

    logger.info(
        "CRON_SCANNER_TRIGGERED | endpoint=/scheduler/run-scanner | source_ip=%s | timestamp=%s",
        source_ip,
        triggered_at,
    )

    if key is None or expected_secret is None or not secrets.compare_digest(key, expected_secret):
        logger.warning(
            "CRON_SCANNER_AUTH_FAILURE | endpoint=/scheduler/run-scanner | source_ip=%s | missing_key=%s | cron_secret_configured=%s | timestamp=%s",
            source_ip,
            key is None,
            expected_secret is not None,
            triggered_at,
        )
        raise HTTPException(status_code=403, detail="Forbidden")

    payload = _build_default_scanner_request()
    progress_queue: asyncio.Queue = asyncio.Queue()

    from ..services.lock_service import LockAcquisitionError

    try:
        scan_id = await ScanExecutionService.execute_scan(
            payload=payload,
            progress_queue=progress_queue,
            trigger_source="cron",
        )
        logger.info(
            "CRON_SCANNER_STARTED | scan_id=%s | start_time=%s | mode=%s | top_n=%s | lookback=%s | swing=%s | symbols=%s",
            scan_id,
            triggered_at,
            payload.mode.value,
            payload.top_n,
            payload.timeframe.lookback_window,
            payload.timeframe.swing,
            len(payload.symbols),
        )
    except LockAcquisitionError:
        logger.warning(
            "CRON_SCANNER_DUPLICATE | endpoint=/scheduler/run-scanner | source_ip=%s | timestamp=%s",
            source_ip,
            time.time(),
        )
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "message": "Scanner already running",
            },
        )
    except Exception:
        duration_sec = time.perf_counter() - started_perf
        logger.exception(
            "CRON_SCANNER_FAILED | completion_time=%s | duration_sec=%.2f | scanned_symbols=%s | shortlisted_count=%s",
            time.time(),
            duration_sec,
            0,
            0,
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Scanner execution failed",
            },
        )

    while True:
        msg = await progress_queue.get()
        if msg.get("status") == "complete":
            result = msg.get("result") or {}
            response = _cron_scanner_response(msg.get("scan_id") or scan_id, result)
            duration_sec = time.perf_counter() - started_perf
            logger.info(
                "CRON_SCANNER_COMPLETED | scan_id=%s | start_time=%s | completion_time=%s | duration_sec=%.2f | scanned_symbols=%s | shortlisted_count=%s",
                response["scan_id"],
                triggered_at,
                time.time(),
                duration_sec,
                response["scanned_symbols"],
                response["shortlisted_count"],
            )
            return JSONResponse(status_code=200, content=response)

        if msg.get("status") == "error":
            duration_sec = time.perf_counter() - started_perf
            logger.error(
                "CRON_SCANNER_FAILED | scan_id=%s | completion_time=%s | duration_sec=%.2f | error_type=%s | message=%s | scanned_symbols=%s | shortlisted_count=%s",
                msg.get("scan_id") or scan_id,
                time.time(),
                duration_sec,
                msg.get("error_type"),
                msg.get("message"),
                0,
                0,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": "Scanner execution failed",
                    "scan_id": msg.get("scan_id") or scan_id,
                },
            )

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
