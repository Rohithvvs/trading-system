from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.session import get_db
from ..services.diagnostics_service import diagnostics

router = APIRouter(prefix="/system/shadow-run", tags=["system"])

@router.get("/status")
async def shadow_run_status(db: AsyncSession = Depends(get_db)):
    db_health = await diagnostics.get_db_health(db)
    memory_metrics = diagnostics.get_memory_metrics()
    
    return {
        "latest_scan": diagnostics.scanner_runs[-1] if diagnostics.scanner_runs else None,
        "latest_scheduler_runs": diagnostics.scheduler_runs[-5:], # last 5 to keep it reasonable
        "db_health": db_health,
        "fyers_health": diagnostics.fyers_metrics,
        "memory_metrics": memory_metrics
    }

@router.get("/report")
async def shadow_run_report(db: AsyncSession = Depends(get_db)):
    return await diagnostics.get_shadow_run_report(db)

@router.get("/health/ready")
async def health_ready(db: AsyncSession = Depends(get_db)):
    import datetime
    from sqlalchemy import text
    from ..config import settings
    from ..services.token_service import get_current_access_token
    
    checks = {
        "database": False,
        "scheduler": False,
        "diagnostics": True,
        "snapshot_storage": False,
        "fyers_token": False
    }

    # CHECK 1: DATABASE
    try:
        res = await db.execute(text("SELECT 1"))
        if res.scalar() == 1:
            checks["database"] = True
    except Exception:
        pass

    # CHECK 2: SCHEDULER
    try:
        from ..main import scheduler
        if scheduler.running:
            checks["scheduler"] = True
    except Exception:
        pass

    # CHECK 4: SNAPSHOT STORAGE
    try:
        await db.execute(text("SELECT 1 FROM scan_snapshots LIMIT 1"))
        checks["snapshot_storage"] = True
    except Exception:
        pass

    # CHECK 5: FYERS
    try:
        token = await get_current_access_token(db)
        if token or settings.fyers_access_token:
            checks["fyers_token"] = True
    except Exception:
        pass

    ready = all(checks.values())
    
    return {
        "ready": ready,
        "checks": checks,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
