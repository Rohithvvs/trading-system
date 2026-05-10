from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas.workstation import AlertCreate, RiskSettingsRequest, SavedScanCreate
from ..services.workstation_service import WorkstationService
from ..utils import sanitize_for_json


router = APIRouter(prefix="/workstation", tags=["workstation"])


def service(db: Session = Depends(get_db)) -> WorkstationService:
    return WorkstationService(db)


@router.get("/universes")
def list_universes(svc: WorkstationService = Depends(service)):
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in svc.list_universes()]))


@router.get("/market-overview")
def market_overview(svc: WorkstationService = Depends(service)):
    return JSONResponse(content=sanitize_for_json(svc.market_overview().model_dump(mode="json")))


@router.get("/saved-scans")
def list_saved_scans(svc: WorkstationService = Depends(service)):
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in svc.list_saved_scans()]))


@router.post("/saved-scans")
def save_scan(payload: SavedScanCreate, svc: WorkstationService = Depends(service)):
    return JSONResponse(content=sanitize_for_json(svc.save_scan(payload).model_dump(mode="json")))


@router.delete("/saved-scans/{scan_id}")
def delete_saved_scan(scan_id: int, svc: WorkstationService = Depends(service)):
    svc.delete_saved_scan(scan_id)
    return JSONResponse(content={"deleted": scan_id})


@router.get("/scan-history")
def scan_history(limit: int = Query(20, ge=1, le=100), svc: WorkstationService = Depends(service)):
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in svc.list_scan_history(limit)]))


@router.get("/scan-history/{scan_id}/compare")
def compare_scan(scan_id: int, svc: WorkstationService = Depends(service)):
    try:
        data = svc.compare_scan(scan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


@router.get("/alerts")
def list_alerts(svc: WorkstationService = Depends(service)):
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in svc.list_alerts()]))


@router.post("/alerts")
def create_alert(payload: AlertCreate, svc: WorkstationService = Depends(service)):
    try:
        item = svc.create_alert(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(item.model_dump(mode="json")))


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, svc: WorkstationService = Depends(service)):
    svc.delete_alert(alert_id)
    return JSONResponse(content={"deleted": alert_id})


@router.get("/risk-settings")
def get_risk_settings(svc: WorkstationService = Depends(service)):
    return JSONResponse(content=sanitize_for_json(svc.get_risk_settings().model_dump(mode="json")))


@router.put("/risk-settings")
def update_risk_settings(payload: RiskSettingsRequest, svc: WorkstationService = Depends(service)):
    return JSONResponse(content=sanitize_for_json(svc.update_risk_settings(payload).model_dump(mode="json")))


@router.get("/api-health")
def api_health(svc: WorkstationService = Depends(service)):
    return JSONResponse(content=sanitize_for_json(svc.api_health().model_dump(mode="json")))
