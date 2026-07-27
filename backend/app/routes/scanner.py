import json
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..services.latest_scan_service import LatestScanService
from ..services.scanner_cache_service import scanner_cache_service, wants_force_refresh
from ..config.settings import settings
from ..utils import get_logger
from ..observability.scan_diagnostics import log_dashboard_request
from ..observability.metrics import (
    record_scanner_cache_force_refresh,
    record_scanner_cache_hit,
    record_scanner_cache_miss,
)

router = APIRouter(prefix="/scanner", tags=["scanner"])
logger = get_logger("app.routes.scanner")

CACHE_KEY_SCANNER_LATEST = "scanner:latest:v1"
ENDPOINT_SCANNER_LATEST = "/scanner/latest"


@router.get("/latest")
async def get_latest_completed_scan(
    request: Request,
    force: bool = Query(default=False, description="Force refresh cache"),
    db: AsyncSession = Depends(get_db),
):
    import time
    from ..services.diagnostics_service import diagnostics

    start_t = time.perf_counter()
    force_refresh = wants_force_refresh(force, request.headers.get("cache-control"))
    cache_enabled = settings.is_scanner_latest_cache_enabled()

    if force_refresh and cache_enabled:
        record_scanner_cache_force_refresh(ENDPOINT_SCANNER_LATEST)

    async def produce_json() -> str:
        service = LatestScanService(db)
        result = await service.get_latest_completed_scan()
        duration_ms = int((time.perf_counter() - start_t) * 1000)

        if not result:
            diagnostics.record_dashboard_snapshot(
                {
                    "response_time_ms": duration_ms,
                    "snapshot_id": None,
                    "record_count": 0,
                }
            )
            log_dashboard_request(
                scan_id=None,
                endpoint=ENDPOINT_SCANNER_LATEST,
                returned_records=0,
                query_duration_ms=duration_ms,
            )
            empty_json = json.dumps(
                {
                    "message": "No completed scans found",
                    "buy_candidates": [],
                    "watch_candidates": [],
                    "rejected_candidates": [],
                }
            )
            if cache_enabled:
                await scanner_cache_service.set_latest_scan(
                    CACHE_KEY_SCANNER_LATEST, empty_json, ttl_seconds=10
                )
            return empty_json

        record_count = (
            len(result.get("buy_candidates", []))
            + len(result.get("watch_candidates", []))
            + len(result.get("rejected_candidates", []))
        )
        diagnostics.record_dashboard_snapshot(
            {
                "response_time_ms": duration_ms,
                "snapshot_id": result.get("snapshot_id", "unknown"),
                "record_count": record_count,
            }
        )
        log_dashboard_request(
            scan_id=result.get("scan_timestamp", "unknown"),
            endpoint=ENDPOINT_SCANNER_LATEST,
            returned_records=record_count,
            query_duration_ms=duration_ms,
        )
        serialized_payload = json.dumps(result)
        if cache_enabled:
            await scanner_cache_service.set_latest_scan(
                CACHE_KEY_SCANNER_LATEST, serialized_payload
            )
        return serialized_payload

    payload, cache_status = await scanner_cache_service.resolve_latest_scan(
        CACHE_KEY_SCANNER_LATEST,
        produce_json,
        force=force_refresh,
        cache_enabled=cache_enabled,
    )

    if cache_status == "HIT":
        record_scanner_cache_hit(ENDPOINT_SCANNER_LATEST)
        duration_ms = int((time.perf_counter() - start_t) * 1000)
        logger.debug("GET /scanner/latest Cache HIT | duration_ms=%d", duration_ms)
    elif cache_status in ("MISS", "FALLBACK"):
        record_scanner_cache_miss(ENDPOINT_SCANNER_LATEST)

    return Response(
        content=payload,
        media_type="application/json",
        headers={"X-Cache-Status": cache_status},
    )
