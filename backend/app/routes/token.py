from sqlalchemy import select, update
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from ..db import get_db
from ..schemas import FyersTokenCreate
from ..services import token_service


router = APIRouter(prefix="/api/token", tags=["token"])
logger = logging.getLogger("app.token")


@router.post("/save-access-token")
async def save_access_token_route(payload: FyersTokenCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    logger.info("=" * 50)
    logger.info("POST /api/token HIT")
    logger.info("=" * 50)

    token = payload.access_token
    if not token or not token.strip():
        logger.error("Rejecting token payload: empty access_token field")
        raise HTTPException(status_code=400, detail="access_token cannot be empty")

    logger.info("Token accepted. Calling token_service.save_access_token...")
    result = await token_service.save_access_token(token, db)
    logger.info("Service result   : %s", result.get("status"))

    if result.get("status") == "error":
        logger.error("Save failed: %s", result.get("message"))
        raise HTTPException(status_code=500, detail=result.get("message"))

    logger.info("HTTP 200 OK returning success")
    
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
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(content=status)


@router.get("/history")
async def token_history(limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    try:
        history = await token_service.get_token_history(db, limit=limit)
    except Exception as exc:
        logger.exception("Failed to load token history: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(content={"history": history})


@router.get("/diagnostic")
async def token_diagnostic(db: AsyncSession = Depends(get_db)):
    
    from ..models import FyersToken
    from ..db.session import engine

    row = (await db.scalars(select(FyersToken).filter(FyersToken.is_active == True).order_by(FyersToken.created_at.desc()))).first()
    return {
        "db_url": str(engine.url),
        "token_row_exists": row is not None,
        "token_is_set": bool(row and row.access_token),
        "token_preview": ("..." + row.access_token[-8:]) if (row and row.access_token and len(row.access_token) >= 8) else None,
        "token_status": row.status if row else "no_row",
        "token_saved_at": str(row.access_token_saved_at) if (row and row.access_token_saved_at) else None,
    }
