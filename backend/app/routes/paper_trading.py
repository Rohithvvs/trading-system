from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas.paper_trading import (
    PaperOrderActionResponse,
    PaperOrderCreateRequest,
    PaperOrderResponse,
    PaperOrderUpdateRequest,
    PaperPositionResponse,
    PaperPositionUpdateRequest,
    PaperQuoteResponse,
    PaperTradingAccountResetRequest,
    PaperTradingDashboardResponse,
    PaperWorkspaceSnapshot,
    RecommendationPrefillRequest,
    RecommendationPrefillResponse,
    NotificationItem,
    NotificationMarkReadRequest,
    AlertCreateRequest,
    AlertItem,
    AnalyticsResponse,
    PaperAccountCapitalUpdateRequest,
    TransactionPageResponse,
    MarketEngineStatusResponse,
)
from ..services.paper_trading_service import PaperTradingService
from ..services.market_engine_service import market_engine
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


@router.get("/account/summary")
def get_account_summary(service: PaperTradingService = Depends(get_service)):
    """Return a compact account summary for dashboard widgets.

    Fields returned:
    - total_capital, available_funds, invested_value, unrealized_pnl,
      realized_pnl, total_pnl, daily_pnl, daily_pnl_pct, market_status
    """
    dashboard = service.get_dashboard()
    account = dashboard.account

    invested_value = float(account.total_invested)
    unrealized_pnl = float(account.unrealized_pnl)
    realized_pnl = float(account.realized_pnl)

    # Define total capital as cash + invested (equity-like)
    total_capital = round(float(account.balance) + invested_value, 2)
    available_funds = round(total_capital - invested_value, 2)
    total_pnl = round(unrealized_pnl + realized_pnl, 2)

    # Compute today's realized P&L in IST timezone
    from datetime import datetime, timezone, timedelta
    try:
        from zoneinfo import ZoneInfo
        ist = ZoneInfo("Asia/Kolkata")
    except Exception:
        # Fallback to fixed offset if zoneinfo is unavailable
        ist = timezone(timedelta(hours=5, minutes=30))

    now_ist = datetime.now(ist)
    start_ist = datetime(now_ist.year, now_ist.month, now_ist.day, 0, 0, 0, tzinfo=ist)
    start_utc = start_ist.astimezone(timezone.utc)
    end_utc = (start_ist + timedelta(days=1)).astimezone(timezone.utc)

    daily_pnl = 0.0
    for trade in dashboard.trades:
        closed_at = getattr(trade, "closed_at", None)
        if not closed_at:
            continue
        if closed_at.tzinfo is None:
            closed_utc = closed_at.replace(tzinfo=timezone.utc)
        else:
            closed_utc = closed_at.astimezone(timezone.utc)
        if start_utc <= closed_utc < end_utc:
            daily_pnl += float(getattr(trade, "pnl", 0.0))

    daily_pnl = round(daily_pnl, 2)
    daily_pnl_pct = round((daily_pnl / total_capital) * 100, 2) if total_capital else 0.0

    # Market status based on IST clock
    now_time = now_ist.time()
    pre_open_start = datetime(now_ist.year, now_ist.month, now_ist.day, 9, 0, tzinfo=ist).time()
    pre_open_end = datetime(now_ist.year, now_ist.month, now_ist.day, 9, 15, tzinfo=ist).time()
    open_start = datetime(now_ist.year, now_ist.month, now_ist.day, 9, 15, tzinfo=ist).time()
    open_end = datetime(now_ist.year, now_ist.month, now_ist.day, 15, 30, tzinfo=ist).time()

    if pre_open_start <= now_time < pre_open_end:
        market_status = "PRE-OPEN 🟡"
    elif open_start <= now_time < open_end:
        market_status = "OPEN 🟢"
    else:
        market_status = "CLOSED 🔴"

    payload = {
        "total_capital": total_capital,
        "available_funds": available_funds,
        "invested_value": invested_value,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "total_pnl": total_pnl,
        "daily_pnl": daily_pnl,
        "daily_pnl_pct": daily_pnl_pct,
        "market_status": market_status,
    }

    return JSONResponse(content=sanitize_for_json(payload))


@router.post("/account/reset", response_model=PaperTradingDashboardResponse)
def reset_account(
    payload: PaperTradingAccountResetRequest,
    service: PaperTradingService = Depends(get_service),
) -> PaperTradingDashboardResponse:
    response = service.reset_account(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.put("/account/capital")
def update_account_capital(
    payload: PaperAccountCapitalUpdateRequest,
    service: PaperTradingService = Depends(get_service),
):
    try:
        response = service.update_starting_capital(payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


@router.post("/engine/start", response_model=MarketEngineStatusResponse)
def start_market_engine() -> MarketEngineStatusResponse:
    market_engine.request_start()
    return JSONResponse(content=sanitize_for_json(market_engine.status()))


@router.post("/engine/stop", response_model=MarketEngineStatusResponse)
def stop_market_engine() -> MarketEngineStatusResponse:
    market_engine.request_stop()
    return JSONResponse(content=sanitize_for_json(market_engine.status()))


@router.get("/engine/status", response_model=MarketEngineStatusResponse)
def get_market_engine_status() -> MarketEngineStatusResponse:
    return JSONResponse(content=sanitize_for_json(market_engine.status()))


@router.post("/engine/heartbeat", response_model=MarketEngineStatusResponse)
def market_engine_heartbeat() -> MarketEngineStatusResponse:
    market_engine.heartbeat()
    return JSONResponse(content=sanitize_for_json(market_engine.status()))


@router.get("/orders/pending", response_model=list[PaperOrderResponse])
def list_pending_orders(service: PaperTradingService = Depends(get_service)):
    response = service.get_dashboard()
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in response.open_orders]))


@router.get("/positions", response_model=list[PaperPositionResponse])
def get_positions(service: PaperTradingService = Depends(get_service)) -> list[PaperPositionResponse]:
    response = service.get_dashboard()
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")["positions"]))


@router.post("/positions/squareoff-all", response_model=PaperTradingDashboardResponse)
def squareoff_all(service: PaperTradingService = Depends(get_service)) -> PaperTradingDashboardResponse:
    try:
        response = service.square_off_all()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.get("/account/transactions", response_model=TransactionPageResponse)
def get_account_transactions(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: PaperTradingService = Depends(get_service),
):
    try:
        data = service.get_transactions(page=page, per_page=per_page)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(data))


@router.put("/orders/{order_id}", response_model=PaperOrderActionResponse)
def modify_order(order_id: int, payload: PaperOrderUpdateRequest, service: PaperTradingService = Depends(get_service)) -> PaperOrderActionResponse:
    try:
        response = service.modify_order(order_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.delete("/orders/{order_id}", response_model=PaperOrderActionResponse)
def delete_order(order_id: int, service: PaperTradingService = Depends(get_service)) -> PaperOrderActionResponse:
    try:
        response = service.cancel_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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


@router.get("/notifications/unread", response_model=list[NotificationItem])
def get_unread_notifications(service: PaperTradingService = Depends(get_service)):
    items = service.get_unread_notifications()
    payload = [
        {
            "id": n.id,
            "message": n.message,
            "level": n.level,
            "is_read": bool(n.is_read),
            "created_at": n.created_at,
        }
        for n in items
    ]
    return JSONResponse(content=sanitize_for_json(payload))


@router.post("/notifications/mark-read")
def mark_notifications_read(payload: NotificationMarkReadRequest, service: PaperTradingService = Depends(get_service)):
    try:
        service.mark_notifications_read(payload.ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json({"marked": len(payload.ids)}))


@router.get("/notifications", response_model=list[NotificationItem])
def list_notifications(unread: bool | None = None, limit: int = 10, service: PaperTradingService = Depends(get_service)):
    try:
        items = service.get_notifications(unread=unread, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = [
        {"id": n.id, "message": n.message, "level": n.level, "is_read": bool(n.is_read), "created_at": n.created_at}
        for n in items
    ]
    return JSONResponse(content=sanitize_for_json(payload))


@router.post("/notifications/read-all")
def read_all_notifications(service: PaperTradingService = Depends(get_service)):
    try:
        count = service.mark_all_notifications_read()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json({"marked": count}))


@router.get("/gap-replay-summary")
def get_gap_replay_summary(request: Request):
    summary = getattr(request.app.state, "last_gap_replay", None)
    if not summary:
        return JSONResponse(content=sanitize_for_json({"status": "no_replay", "message": "No gap replay data available"}))
    return JSONResponse(
        content=sanitize_for_json({
            "status": "ok",
            "gap_start": summary.get("gap_start"),
            "gap_end": summary.get("gap_end"),
            "orders_filled": summary.get("orders_filled", []),
            "positions_exited": summary.get("positions_exited", []),
            "warnings": summary.get("warnings", []),
            "skipped_reason": summary.get("skipped_reason"),
        })
    )


@router.get("/alerts", response_model=list[AlertItem])
def list_alerts(service: PaperTradingService = Depends(get_service)):
    try:
        items = service.get_alerts()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = [
        {
            "id": a.id,
            "symbol": a.symbol,
            "condition": a.condition,
            "target_price": a.target_price,
            "status": a.status,
            "created_at": a.created_at,
            "triggered_at": a.triggered_at,
            "triggered_price": a.triggered_price,
        }
        for a in items
    ]
    return JSONResponse(content=sanitize_for_json(payload))


@router.post("/alerts", response_model=AlertItem)
def create_alert(payload: AlertCreateRequest, service: PaperTradingService = Depends(get_service)):
    try:
        a = service.create_alert(payload.symbol, payload.condition, payload.price)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json({
        "id": a.id,
        "symbol": a.symbol,
        "condition": a.condition,
        "target_price": a.target_price,
        "status": a.status,
        "created_at": a.created_at,
        "triggered_at": a.triggered_at,
        "triggered_price": a.triggered_price,
    }))


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, service: PaperTradingService = Depends(get_service)):
    try:
        service.delete_alert(alert_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json({"deleted": alert_id}))


@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(service: PaperTradingService = Depends(get_service)):
    try:
        data = service.get_analytics()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(data))
