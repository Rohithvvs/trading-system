from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..schemas.workstation import AlertCreate, RiskSettingsRequest, SavedScanCreate, MarketOverviewResponse
from ..services.workstation_service import WorkstationService
from ..utils import sanitize_for_json


router = APIRouter(prefix="/workstation", tags=["workstation"])


def service(db: AsyncSession = Depends(get_db)) -> WorkstationService:
    return WorkstationService(db)


@router.get("/universes")
async def list_universes(svc: WorkstationService = Depends(service)):
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in await svc.list_universes()]))


@router.get("/market-overview", response_model=MarketOverviewResponse)
async def market_overview(svc: WorkstationService = Depends(service)):
    overview = await svc.market_overview()
    return JSONResponse(content=sanitize_for_json(overview.model_dump(mode="json")))


@router.get("/saved-scans")
async def list_saved_scans(svc: WorkstationService = Depends(service)):
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in await svc.list_saved_scans()]))


@router.post("/saved-scans")
async def save_scan(payload: SavedScanCreate, svc: WorkstationService = Depends(service)):
    scan = await svc.save_scan(payload)
    return JSONResponse(content=sanitize_for_json(scan.model_dump(mode="json")))


@router.delete("/saved-scans/{scan_id}")
async def delete_saved_scan(scan_id: int, svc: WorkstationService = Depends(service)):
    await svc.delete_saved_scan(scan_id)
    return JSONResponse(content={"deleted": scan_id})


@router.get("/scan-history")
async def scan_history(limit: int = Query(20, ge=1, le=100), svc: WorkstationService = Depends(service)):
    history = await svc.list_scan_history(limit)
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in history]))


@router.get("/scan-history/{scan_id}/compare")
async def compare_scan(scan_id: int, svc: WorkstationService = Depends(service)):
    try:
        data = await svc.compare_scan(scan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


@router.get("/alerts")
async def list_alerts(svc: WorkstationService = Depends(service)):
    alerts = await svc.list_alerts()
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in alerts]))


@router.post("/alerts")
async def create_alert(payload: AlertCreate, svc: WorkstationService = Depends(service)):
    try:
        item = await svc.create_alert(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(item.model_dump(mode="json")))


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int, svc: WorkstationService = Depends(service)):
    await svc.delete_alert(alert_id)
    return JSONResponse(content={"deleted": alert_id})


@router.get("/risk-settings")
async def get_risk_settings(svc: WorkstationService = Depends(service)):
    settings = await svc.get_risk_settings()
    return JSONResponse(content=sanitize_for_json(settings.model_dump(mode="json")))


@router.put("/risk-settings")
async def update_risk_settings(payload: RiskSettingsRequest, svc: WorkstationService = Depends(service)):
    settings = await svc.update_risk_settings(payload)
    return JSONResponse(content=sanitize_for_json(settings.model_dump(mode="json")))


@router.get("/api-health")
async def api_health(svc: WorkstationService = Depends(service)):
    health = await svc.api_health()
    return JSONResponse(content=sanitize_for_json(health.model_dump(mode="json")))
