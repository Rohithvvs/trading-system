from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..services.latest_scan_service import LatestScanService
from ..utils import get_logger
from ..observability.scan_diagnostics import log_dashboard_request

router = APIRouter(prefix="/scanner", tags=["scanner"])
logger = get_logger("app.routes.scanner")

@router.get("/latest")
async def get_latest_completed_scan(db: AsyncSession = Depends(get_db)):
    import time
    from ..services.diagnostics_service import diagnostics
    start_t = time.perf_counter()
    
    service = LatestScanService(db)
    result = await service.get_latest_completed_scan()
    
    duration_ms = int((time.perf_counter() - start_t) * 1000)
    
    if not result:
        diagnostics.record_dashboard_snapshot({
            "response_time_ms": duration_ms,
            "snapshot_id": None,
            "record_count": 0
        })
        log_dashboard_request(scan_id=None, endpoint="/scanner/latest", returned_records=0, query_duration_ms=duration_ms)
        return {"message": "No completed scans found", "buy_candidates": [], "watch_candidates": [], "rejected_candidates": []}
    
    record_count = len(result.get("buy_candidates", [])) + len(result.get("watch_candidates", [])) + len(result.get("rejected_candidates", []))
    diagnostics.record_dashboard_snapshot({
        "response_time_ms": duration_ms,
        "snapshot_id": result.get("snapshot_id", "unknown"),
        "record_count": record_count
    })
    log_dashboard_request(scan_id=result.get("scan_timestamp", "unknown"), endpoint="/scanner/latest", returned_records=record_count, query_duration_ms=duration_ms)
    return result
