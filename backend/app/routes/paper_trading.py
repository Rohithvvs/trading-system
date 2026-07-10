from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import datetime
import logging
import time
from zoneinfo import ZoneInfo

from ..db import get_sync_db
from sqlalchemy.orm import Session
from ..db.scan_store import get_last_scan_time
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
    PaperTradeHistoryItem,
)
from ..services.paper_trading_service import PaperTradingService
from ..services.market_engine_service import market_engine
from ..utils import sanitize_for_json
from ..config import settings


router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])


def get_service(db: Session = Depends(get_sync_db)) -> PaperTradingService:
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

    # Use centralized TradingHoursService for consistent status (includes holidays)
    try:
        from ..services.trading_hours_service import trading_hours
        status_info = trading_hours.get_market_status()
        if status_info["status"] == "OPEN":
            market_status = "OPEN 🟢"
        elif status_info["status"] == "PRE_OPEN":
            market_status = "PRE-OPEN 🟡"
        else:
            market_status = "CLOSED 🔴"
    except Exception:
        # Fallback to previous simple logic
        now_time = now_ist.time()
        pre_open_start = datetime.datetime(now_ist.year, now_ist.month, now_ist.day, 9, 0, tzinfo=ist).time()
        pre_open_end = datetime.datetime(now_ist.year, now_ist.month, now_ist.day, 9, 15, tzinfo=ist).time()
        open_start = datetime.datetime(now_ist.year, now_ist.month, now_ist.day, 9, 15, tzinfo=ist).time()
        open_end = datetime.datetime(now_ist.year, now_ist.month, now_ist.day, 15, 30, tzinfo=ist).time()

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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    service: PaperTradingService = Depends(get_service),
) -> PaperOrderActionResponse:
    logger = logging.getLogger("app.paper_trading")
    logger.info("ORDER_REQUEST_RECEIVED | symbol=%s side=%s type=%s", payload.symbol, payload.side, payload.type)
    try:
        key = payload.idempotency_key or idempotency_key or x_idempotency_key
        if not key and settings.app_env == "test":
            key = f"test:{payload.symbol}:{payload.side}:{payload.type}:{payload.qty}:{datetime.datetime.utcnow().timestamp()}"
        if not key:
            logger.warning("ORDER_IDEMPOTENCY_MISSING | symbol=%s", payload.symbol)
            raise HTTPException(status_code=400, detail="Idempotency-Key header or idempotency_key body field is required.")
        logger.info("ORDER_IDEMPOTENCY_PRESENT | symbol=%s", payload.symbol)
        payload.idempotency_key = key.strip()
        logger.info("ORDER_SUBMISSION_STARTED | symbol=%s side=%s type=%s", payload.symbol, payload.side, payload.type)
        response = service.place_order(payload)
        logger.info("ORDER_SUBMISSION_SUCCESS | symbol=%s order_id=%s", payload.symbol, getattr(response, 'order_id', None))
    except HTTPException:
        logger.warning("ORDER_SUBMISSION_FAILED | symbol=%s reason=HTTPException", payload.symbol)
        raise
    except ValueError as exc:
        logger.warning("ORDER_SUBMISSION_FAILED | symbol=%s reason=ValueError error=%s", payload.symbol, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("ORDER_SUBMISSION_FAILED | symbol=%s reason=Exception error=%s", payload.symbol, str(exc))
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/engine/start", response_model=MarketEngineStatusResponse)
async def start_market_engine() -> MarketEngineStatusResponse:
    await market_engine.request_start()
    return JSONResponse(content=sanitize_for_json(await market_engine.status()))


@router.post("/engine/stop", response_model=MarketEngineStatusResponse)
async def stop_market_engine() -> MarketEngineStatusResponse:
    await market_engine.request_stop()
    return JSONResponse(content=sanitize_for_json(await market_engine.status()))


@router.get("/engine/status", response_model=MarketEngineStatusResponse)
async def get_market_engine_status() -> MarketEngineStatusResponse:
    return JSONResponse(content=sanitize_for_json(await market_engine.status()))


import asyncio
import concurrent.futures

# Dedicated executor for heavy Pandas background scans to prevent starving FastAPI worker threads
_scan_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

async def _run_automated_background_scan_sync():
    """Runs a complete Nifty 500 swing scan and caches it in SQLite."""
    logger = logging.getLogger("app.background")
    logger.info("Starting automated background scan...")
    try:
        from ..agents import RouterAgent
        from ..schemas.analysis import ScreenerRequest, AnalysisMode, TimeframeConfig
        
        req = ScreenerRequest(
            mode=AnalysisMode.SWING,
            timeframe_config=TimeframeConfig(intraday="5m", swing="1d", lookback_window=180),
            universe="NIFTY500",
            custom_symbols=[],
            top_n=20
        )
        await RouterAgent(None).screener_full(req)
        logger.info("Automated background scan completed successfully.")
    except Exception as e:
        logger.error("Automated background scan failed: %s", e, exc_info=True)

async def _run_automated_background_scan():
    """Async wrapper that directly awaits the scan (no thread executor needed)."""
    await _run_automated_background_scan_sync()


@router.post("/engine/heartbeat", response_model=MarketEngineStatusResponse)
async def market_engine_heartbeat(background_tasks: BackgroundTasks) -> MarketEngineStatusResponse:
    await market_engine.heartbeat()
    
    # 1. Immediately log the incoming cron keep-alive ping is done via market_engine.heartbeat() internal logs.
    logger = logging.getLogger("app.heartbeat")
    
    now_ist = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    # 1) When was the last scan done?
    last_scan_str = await get_last_scan_time()
    should_run = False
    
    if last_scan_str:
        # SQLite datetime('now') stores UTC. Parse it and convert to IST.
        try:
            last_scan_utc = datetime.datetime.strptime(last_scan_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
            last_scan_ist = last_scan_utc.astimezone(ZoneInfo("Asia/Kolkata"))
        except ValueError:
            # Fallback if the format is different
            last_scan_ist = datetime.datetime.fromisoformat(last_scan_str).astimezone(ZoneInfo("Asia/Kolkata"))
    else:
        last_scan_ist = None

    # 2. MORNING 9:00 AM CHECK: Between 09:00 AM and 09:15 AM IST and no scan has run yet today
    if datetime.time(9, 0) <= now_ist.time() <= datetime.time(9, 15):
        if not last_scan_ist or last_scan_ist.date() != now_ist.date():
            logger.info("Triggering morning baseline scan (9:00 AM - 9:15 AM window).")
            should_run = True

    # 3. 30-MINUTE INTERVAL CHECK: During market hours, check if last scan is older than 30 mins
    if not should_run and market_engine.is_market_hours():
        if last_scan_ist:
            mins_since_last = (now_ist - last_scan_ist).total_seconds() / 60.0
            if mins_since_last > 30:
                logger.info(f"Triggering interval scan. Last scan was {mins_since_last:.1f} mins ago.")
                should_run = True
        else:
            logger.info("Triggering initial interval scan (no previous scan found).")
            should_run = True

    if should_run:
        logger.info("Auto scan from heartbeat is disabled.")
        # background_tasks.add_task(_run_automated_background_scan)

    return JSONResponse(content=sanitize_for_json(await market_engine.status()))


@router.get("/orders/pending", response_model=list[PaperOrderResponse])
def list_pending_orders(service: PaperTradingService = Depends(get_service)):
    orders = service.get_pending_orders()
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in orders]))


@router.get("/orders/history", response_model=list[PaperOrderResponse])
def list_order_history(service: PaperTradingService = Depends(get_service)):
    orders = service.get_order_history()
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in orders]))


@router.get("/trades", response_model=list[PaperTradeHistoryItem])
def list_trade_history(service: PaperTradingService = Depends(get_service)):
    trades = service.get_trades()
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in trades]))


@router.get("/positions", response_model=list[PaperPositionResponse])
def get_positions(service: PaperTradingService = Depends(get_service)) -> list[PaperPositionResponse]:
    positions = service.get_positions()
    return JSONResponse(content=sanitize_for_json([item.model_dump(mode="json") for item in positions]))


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
def modify_order(
    order_id: int, 
    payload: PaperOrderUpdateRequest, 
    service: PaperTradingService = Depends(get_service),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key")
) -> PaperOrderActionResponse:
    try:
        response = service.modify_order(order_id, payload, idempotency_key=x_idempotency_key)
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
def cancel_order(
    order_id: int, 
    service: PaperTradingService = Depends(get_service),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key")
) -> PaperOrderActionResponse:
    try:
        response = service.cancel_order(order_id, idempotency_key=x_idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/positions/{position_id}/close", response_model=PaperOrderActionResponse)
def close_position(
    position_id: int, 
    service: PaperTradingService = Depends(get_service),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key")
) -> PaperOrderActionResponse:
    try:
        response = service.close_position(position_id, idempotency_key=x_idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.patch("/positions/{position_id}", response_model=PaperOrderActionResponse)
def update_position(
    position_id: int,
    payload: PaperPositionUpdateRequest,
    service: PaperTradingService = Depends(get_service),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key")
) -> PaperOrderActionResponse:
    try:
        response = service.update_position(position_id, payload, idempotency_key=x_idempotency_key)
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
    dashboard = service.get_dashboard()
    return JSONResponse(content=sanitize_for_json(dashboard.symbols))


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

@router.get("/engine-status")
async def get_engine_status(service: PaperTradingService = Depends(get_service)):
    logger = logging.getLogger("app.http")
    logger.info("ENGINE_STATUS_REQUESTED | timestamp=%s", datetime.datetime.utcnow().isoformat())
    start_time = time.time()
    try:
        status = await service.get_engine_status()
        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "ENGINE_STATUS_RESPONSE | timestamp=%s | response_duration_ms=%s | open_positions=%s | tracked_symbols=%s",
            datetime.datetime.utcnow().isoformat(),
            duration_ms,
            status.get("open_positions", 0),
            status.get("tracked_symbols", 0)
        )
        return JSONResponse(content=sanitize_for_json(status))
    except Exception as e:
        logger.error("ENGINE_STATUS_FAILED | timestamp=%s | error=%s", datetime.datetime.utcnow().isoformat(), str(e))
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
