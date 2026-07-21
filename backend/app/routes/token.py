from fastapi import APIRouter, Depends, Header, HTTPException, Query, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import os
import secrets
import time
from typing import Optional

from ..db import get_db
from ..schemas import FyersTokenCreate
from ..services import token_service


router = APIRouter(prefix="/api/token", tags=["token"])
logger = logging.getLogger("app.token")


def _require_scheduler_secret(
    request: Request,
    x_scheduler_secret: Optional[str],
) -> None:
    """Same secret gate as POST /scheduler/daily-scan (for server cron jobs)."""
    source_ip = request.client.host if request.client else "unknown"
    timestamp = time.time()
    expected_secret = os.environ.get("SCHEDULER_SECRET")

    if x_scheduler_secret is None:
        logger.warning(
            "TOKEN_GENERATE_AUTH_FAILURE | reason=missing_header | source_ip=%s | timestamp=%s",
            source_ip,
            timestamp,
        )
        raise HTTPException(status_code=401, detail="Unauthorized")

    if expected_secret is None or not secrets.compare_digest(
        x_scheduler_secret, expected_secret
    ):
        logger.warning(
            "TOKEN_GENERATE_AUTH_FAILURE | reason=invalid_secret_or_unconfigured | source_ip=%s | timestamp=%s",
            source_ip,
            timestamp,
        )
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/generate")
async def generate_access_token_route(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_scheduler_secret: Optional[str] = Header(
        default=None, alias="X-Scheduler-Secret"
    ),
):
    """Cron-safe Fyers access-token generation + DB persist.

    Fully automated (OTP → TOTP → PIN → auth_code → access_token → Neon).
    No browser / captcha. Requires header ``X-Scheduler-Secret`` matching
    env ``SCHEDULER_SECRET`` (same as ``POST /scheduler/daily-scan``).

    Never returns the raw access token — only masked preview + monitoring fields.
    """
    _require_scheduler_secret(request, x_scheduler_secret)
    source_ip = request.client.host if request.client else "unknown"
    logger.info(
        "TOKEN_GENERATE_ACCEPTED | trigger_source=cron | endpoint=/api/token/generate | source_ip=%s",
        source_ip,
    )

    try:
        result = await token_service.generate_and_persist_fyers_token(db)
    except Exception as exc:
        # Map known generator failures; never leak raw token material.
        from fyers_token import FyersAuthError, FyersConfigError, FyersConnectionError

        err_type = type(exc).__name__
        err_msg = str(exc)
        # Truncate/redact-ish for API clients
        if len(err_msg) > 240:
            err_msg = err_msg[:240] + "..."
        logger.warning(
            "TOKEN_GENERATE_FAILED | error_type=%s | error=%s",
            err_type,
            err_msg,
        )

        if isinstance(exc, FyersConfigError):
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "Failed",
                    "error_type": err_type,
                    "message": err_msg,
                },
            ) from exc
        if isinstance(exc, FyersAuthError):
            raise HTTPException(
                status_code=502,
                detail={
                    "status": "Failed",
                    "error_type": err_type,
                    "message": err_msg,
                },
            ) from exc
        if isinstance(exc, (FyersConnectionError, TimeoutError)):
            raise HTTPException(
                status_code=504,
                detail={
                    "status": "Failed",
                    "error_type": err_type,
                    "message": err_msg,
                },
            ) from exc
        raise HTTPException(
            status_code=500,
            detail={
                "status": "Failed",
                "error_type": err_type,
                "message": err_msg or "Token generation failed",
            },
        ) from exc

    # Enrich with connection status (no raw token).
    try:
        status = await token_service.get_token_status(db)
    except Exception:
        status = {}

    body = {
        "status": result.get("status") or "Success",
        "saved_at": result.get("saved_at"),
        "token_preview": result.get("token_preview"),
        "connection_status": status.get("connection_status"),
        "access_token_active": status.get("access_token_active"),
        "expires_at": status.get("expires_at"),
        "message": "Fyers access token generated and stored",
    }
    logger.info(
        "TOKEN_GENERATE_SUCCESS | status=%s | preview=%s | connection=%s",
        body.get("status"),
        body.get("token_preview"),
        body.get("connection_status"),
    )
    return JSONResponse(content=body, status_code=200)


@router.post("/save-access-token")
async def save_access_token_route(payload: FyersTokenCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    token = payload.access_token
    if not token or not str(token).strip():
        raise HTTPException(status_code=400, detail="access_token cannot be empty")
    token = str(token).strip()
    # Local sanity check (parity with settings token validate path)
    if len(token) < 10:
        raise HTTPException(
            status_code=400,
            detail="Access token is empty or too short.",
        )

    result = await token_service.save_access_token(token, db)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    
    # Auto-trigger scan
    from datetime import datetime, timezone
    import pytz
    
    try:
        ist = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(ist)
        
        market_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now_ist.replace(hour=22, minute=0, second=0, microsecond=0)
        
        if market_open <= now_ist <= market_close:
            from ..services.diagnostics_service import diagnostics
            is_running = diagnostics.last_scan_status == "RUNNING"
            
            recent_scan = False
            try:
                from ..services.latest_scan_service import LatestScanService
                scan_service = LatestScanService(db)
                latest_scan = await scan_service.get_latest_completed_scan()
                if latest_scan and latest_scan.get("last_scan_completed_at"):
                    last_scan_time = datetime.fromisoformat(latest_scan["last_scan_completed_at"])
                    # Use UTC for diff since isoformat is typically UTC (or convert accordingly)
                    now_utc = datetime.now(timezone.utc)
                    if last_scan_time.tzinfo is None:
                        last_scan_time = last_scan_time.replace(tzinfo=timezone.utc)
                    time_since_scan = (now_utc - last_scan_time).total_seconds()
                    if time_since_scan < 900:  # 15 minutes
                        recent_scan = True
            except Exception as scan_e:
                logger.error("Failed to check last scan time: %s", scan_e)
            
            if is_running:
                logger.info("AUTO_SCAN_SKIPPED_ALREADY_RUNNING: Scanner is currently active.")
            elif recent_scan:
                logger.info("AUTO_SCAN_SKIPPED_RECENT_SCAN: Last completed scanner execution is < 15 minutes old.")
            else:
                logger.info("Auto scan after token save is disabled.")
                # from ..main import automated_screening_job
                # background_tasks.add_task(automated_screening_job)
        else:
            logger.info("AUTO_SCAN_SKIPPED_OUTSIDE_WINDOW: Auto-trigger scanner only allowed between 09:15 and 22:00 IST.")
    except Exception as e:
        logger.error("Failed auto-trigger logic: %s", e)
    
    return result


@router.get("/status")
async def token_status(db: AsyncSession = Depends(get_db)):
    try:
        status = await token_service.get_token_status(db)
    except Exception as exc:
        logger.exception("Failed to load token status: %s", exc)
        raise HTTPException(status_code=500, detail="Unable to load token status.")
    return JSONResponse(content=status)


@router.get("/history")
async def token_history(limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    try:
        history = await token_service.get_token_history(db, limit=limit)
    except Exception as exc:
        logger.exception("Failed to load token history: %s", exc)
        raise HTTPException(status_code=500, detail="Unable to load token history.")
    return JSONResponse(content={"history": history})


@router.get("/diagnostic")
async def token_diagnostic(db: AsyncSession = Depends(get_db)):
    """Ops diagnostic — no raw token material. Uses same status model as /api/token/status."""
    from ..db.session import engine

    try:
        status = await token_service.get_token_status(db)
    except Exception as exc:
        logger.exception("Failed to load token diagnostic: %s", exc)
        raise HTTPException(status_code=500, detail="Unable to load token diagnostic.")

    return {
        # Never expose full DATABASE_URL credentials in logs/UI — host/driver only when possible
        "db_url": str(engine.url).split("@")[-1] if "@" in str(engine.url) else str(engine.url).split("://")[0],
        "token_row_exists": status.get("status") not in (None, "no_token", "no_row"),
        "token_is_set": bool(status.get("access_token_active")),
        "token_preview": None,  # never expose raw/encrypted token material
        "token_status": status.get("status") or "no_row",
        "connection_status": status.get("connection_status"),
        "last_error": status.get("last_error"),
        "token_saved_at": status.get("access_token_saved_at"),
        "automation_metrics": status.get("automation_metrics"),
    }


internal_router = APIRouter(tags=["internal"])


@internal_router.post("/internal/refresh-fyers-token")
async def refresh_fyers_token_route(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_scheduler_secret: Optional[str] = Header(
        default=None, alias="X-Scheduler-Secret"
    ),
):
    """Internal protected endpoint to trigger Fyers access token generation and persistence."""
    _require_scheduler_secret(request, x_scheduler_secret)

    try:
        await token_service.generate_and_persist_fyers_token(db)
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Access token generated and saved successfully",
            },
        )
    except Exception as exc:
        logger.error(
            "INTERNAL_REFRESH_TOKEN_FAILED | error_type=%s | error=%s",
            type(exc).__name__,
            str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to generate access token after retries",
            },
        )

