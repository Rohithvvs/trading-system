from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas.paper_trading import (
    PaperOrderActionResponse,
    PaperOrderCreateRequest,
    PaperPositionUpdateRequest,
    PaperQuoteResponse,
    PaperTradingAccountResetRequest,
    PaperTradingDashboardResponse,
    PaperWorkspaceSnapshot,
    RecommendationPrefillRequest,
    RecommendationPrefillResponse,
)
from ..services.paper_trading_service import PaperTradingService
from ..utils import sanitize_for_json


router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])


def get_service(db: Session = Depends(get_db)) -> PaperTradingService:
    return PaperTradingService(db)


@router.get("/dashboard", response_model=PaperTradingDashboardResponse)
def get_dashboard(
    selected_symbol: str | None = Query(default=None),
    service: PaperTradingService = Depends(get_service),
) -> PaperTradingDashboardResponse:
    response = service.get_dashboard(selected_symbol=selected_symbol)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.get("/account", response_model=PaperTradingDashboardResponse)
def get_account(service: PaperTradingService = Depends(get_service)) -> PaperTradingDashboardResponse:
    response = service.get_dashboard()
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/account/reset", response_model=PaperTradingDashboardResponse)
def reset_account(
    payload: PaperTradingAccountResetRequest,
    service: PaperTradingService = Depends(get_service),
) -> PaperTradingDashboardResponse:
    response = service.reset_account(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/orders", response_model=PaperOrderActionResponse)
def place_order(
    payload: PaperOrderCreateRequest,
    service: PaperTradingService = Depends(get_service),
) -> PaperOrderActionResponse:
    try:
        response = service.place_order(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/orders/{order_id}/cancel", response_model=PaperOrderActionResponse)
def cancel_order(order_id: int, service: PaperTradingService = Depends(get_service)) -> PaperOrderActionResponse:
    try:
        response = service.cancel_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/positions/{position_id}/close", response_model=PaperOrderActionResponse)
def close_position(position_id: int, service: PaperTradingService = Depends(get_service)) -> PaperOrderActionResponse:
    try:
        response = service.close_position(position_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.patch("/positions/{position_id}", response_model=PaperOrderActionResponse)
def update_position(
    position_id: int,
    payload: PaperPositionUpdateRequest,
    service: PaperTradingService = Depends(get_service),
) -> PaperOrderActionResponse:
    try:
        response = service.update_position(position_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/from-recommendation", response_model=RecommendationPrefillResponse)
def from_recommendation(
    payload: RecommendationPrefillRequest,
    service: PaperTradingService = Depends(get_service),
) -> RecommendationPrefillResponse:
    response = service.recommendation_prefill(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.get("/symbols", response_model=list[str])
def get_symbols(service: PaperTradingService = Depends(get_service)) -> list[str]:
    return JSONResponse(content=sanitize_for_json(service.get_dashboard().symbols))


@router.get("/symbols/{symbol}/workspace", response_model=PaperWorkspaceSnapshot)
def get_workspace(symbol: str, service: PaperTradingService = Depends(get_service)) -> PaperWorkspaceSnapshot:
    try:
        response = service.get_workspace(symbol.strip().upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.get("/symbols/{symbol}/quote", response_model=PaperQuoteResponse)
def get_quote(symbol: str, service: PaperTradingService = Depends(get_service)) -> PaperQuoteResponse:
    try:
        response = service.get_quote(symbol.strip().upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))
