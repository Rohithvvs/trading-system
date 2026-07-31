from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import datetime
from datetime import timezone
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
    PaperAccountCapitalUpdateRequest,
    TransactionPageResponse,
    MarketEngineStatusResponse,
    PaperTradeHistoryItem,
)
from ..services.paper_trading_service import PaperTradingService
from ..services.market_engine_service import market_engine
from ..utils import sanitize_for_json
from ..config import settings
from ..core.deps import get_current_user_id_sync, require_feature_sync
import uuid


router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])


def get_service(
    user_id: uuid.UUID = Depends(get_current_user_id_sync),
    db: Session = Depends(get_sync_db),
) -> PaperTradingService:
    """
    Always scope paper trading to the authenticated user from the session cookie.
    Never accept user_id from request body/query.
    """
    return PaperTradingService(db, user_id=user_id)


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
    """Return paper capital fields shared by Paper Desk, Order page, and widgets.

    Single source of truth for available cash. Derived from the same
    ``dashboard.account`` summary used by ``GET /paper-trading/dashboard``.

    Always includes both naming conventions so consumers never desync:
    - Capital: available_cash, available_funds, balance, cash_balance, equity
    - Widgets: total_capital, invested_value, total_pnl, daily_pnl, daily_pnl_pct
    - Risk: max_risk_per_trade, reserved_cash
    """
    logger = logging.getLogger("app.paper_trading")
    dashboard = service.get_dashboard()
    account = dashboard.account

    invested_value = float(account.total_invested)
    unrealized_pnl = float(account.unrealized_pnl)
    realized_pnl = float(account.realized_pnl)
    balance = float(account.balance)
    # Prefer reserved-aware available_cash (matches order validation / dashboard strip).
    available_cash = float(account.available_cash)
    equity = float(account.equity)
    starting_balance = float(account.starting_balance)
    reserved_cash = float(account.reserved_cash)
    max_risk_per_trade = float(account.max_risk_per_trade)

    # Equity-like total capital; available_funds aliases available_cash so Desk + Order match.
    total_capital = round(float(account.equity), 2) if equity else round(balance + invested_value, 2)
    available_funds = round(available_cash, 2)
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

    payload = {
        # Identity / full account capital (same semantics as dashboard.account)
        "account_id": account.account_id,
        "account_name": account.account_name,
        "base_currency": account.base_currency,
        "starting_balance": starting_balance,
        "balance": balance,
        "cash_balance": balance,
        "equity": equity,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "total_invested": invested_value,
        "reserved_cash": reserved_cash,
        "available_cash": available_cash,
        "open_positions_count": account.open_positions_count,
        "open_orders_count": account.open_orders_count,
        "max_risk_per_trade": max_risk_per_trade,
        "updated_at": account.updated_at,
        # Widget / alias fields (kept for Paper Desk widgets)
        "total_capital": total_capital,
        "available_funds": available_funds,
        "invested_value": invested_value,
        "total_pnl": total_pnl,
        "daily_pnl": daily_pnl,
        "daily_pnl_pct": daily_pnl_pct,
    }

    logger.info(
        "PAPER_ACCOUNT_SUMMARY | account_id=%s available_cash=%s balance=%s "
        "available_funds=%s equity=%s reserved_cash=%s invested=%s",
        account.account_id,
        available_cash,
        balance,
        available_funds,
        equity,
        reserved_cash,
        invested_value,
    )

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
            key = f"test:{payload.symbol}:{payload.side}:{payload.type}:{payload.qty}:{datetime.datetime.now(timezone.utc).timestamp()}"
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

    # 3. 30-MINUTE INTERVAL CHECK: Check if last scan is older than 30 mins
    if not should_run:
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
) -> PaperOrderActionResponse:
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
def cancel_order(
    order_id: int, 
    service: PaperTradingService = Depends(get_service),
) -> PaperOrderActionResponse:
    try:
        response = service.cancel_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/positions/{position_id}/close", response_model=PaperOrderActionResponse)
def close_position(
    position_id: int, 
    service: PaperTradingService = Depends(get_service),
) -> PaperOrderActionResponse:
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
    """Live quote for paper trading. Always returns a structured payload.

    Provider failures are degraded inside the service (last-known / candle
    fallback) rather than hard-failing the poller. Invalid symbols still 400.
    """
    logger = logging.getLogger("app.paper_trading")
    started = time.perf_counter()
    try:
        response = service.get_quote(symbol.strip().upper())
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "QUOTE_HTTP_OK | symbol=%s | source=%s | latency_ms=%s | status_code=200",
            response.symbol,
            response.source,
            latency_ms,
        )
        return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))
    except ValueError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "QUOTE_HTTP_REJECTED | symbol=%s | status_code=400 | latency_ms=%s | exception=ValueError | error=%s",
            symbol,
            latency_ms,
            str(exc)[:200],
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.exception(
            "QUOTE_HTTP_FAILURE | symbol=%s | status_code=503 | latency_ms=%s | exception=%s | error=%s",
            symbol,
            latency_ms,
            type(exc).__name__,
            str(exc)[:200],
        )
        # Structured degraded status instead of generic 500 so UI can recover
        raise HTTPException(
            status_code=503,
            detail={
                "market_status": "degraded",
                "reason": "Quote Provider Timeout" if "timeout" in str(exc).lower() else "Market data service unavailable",
                "symbol": symbol.strip().upper(),
                "exception": type(exc).__name__,
            },
        ) from exc


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


@router.get("/analytics")
def get_analytics(
    period: str = Query(
        default="all",
        description="today|week|month|last_month|last_3_months|last_6_months|last_year|all",
    ),
    service: PaperTradingService = Depends(get_service),
    _feat=Depends(require_feature_sync("portfolio_analytics")),
):
    """Paper trading analytics. Calculated from closed trades; returns empty defaults when no trades exist."""
    logger = logging.getLogger("app.http.paper_trading")
    try:
        data = service.get_analytics(period=period)
    except ValueError as exc:
        logger.exception("Analytics ValueError: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Analytics unexpected error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"error_type": "ANALYTICS_ERROR", "message": "Failed to compute paper trading analytics."},
        ) from exc

    # Always sanitize — Numeric/Decimal columns must never reach JSONResponse.
    from ..utils import collect_decimal_paths, assert_json_serializable, find_non_jsonable

    decimal_paths = collect_decimal_paths(data, "analytics")
    if decimal_paths:
        logger.info(
            "ANALYTICS_DECIMAL_PATHS | count=%s | paths=%s",
            len(decimal_paths),
            decimal_paths[:50],
        )

    try:
        safe = assert_json_serializable(sanitize_for_json(data), root_name="analytics")
    except TypeError as exc:
        remaining = find_non_jsonable(sanitize_for_json(data), "analytics")
        for path in remaining:
            logger.error("ANALYTICS_JSON_UNSUPPORTED | path=%s", path)
        logger.exception("ANALYTICS_JSON_SERIALIZE_FAILED | error=%s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": "JSON_SERIALIZE_ERROR",
                "message": "Analytics data could not be serialized.",
                "paths": remaining,
            },
        ) from exc

    return JSONResponse(content=safe)


@router.get("/daily-analytics")
def get_daily_analytics(
    period: str = Query(default="today"),
    start_date: str | None = Query(default=None, description="YYYY-MM-DD for custom"),
    end_date: str | None = Query(default=None, description="YYYY-MM-DD for custom"),
    include_ai: bool = Query(default=True),
    service: PaperTradingService = Depends(get_service),
    _feat=Depends(require_feature_sync("portfolio_analytics")),
):
    """
    User-scoped Daily Analytics dashboard payload.
    Always filtered by authenticated user's paper account.
    """
    from ..services.daily_analytics_service import DailyAnalyticsService
    from ..utils import assert_json_serializable

    das = DailyAnalyticsService(service.db, user_id=service.user_id)
    try:
        data = das.build(period=period, start_date=start_date, end_date=end_date, include_ai=include_ai)
        safe = assert_json_serializable(sanitize_for_json(data), root_name="daily_analytics")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logging.getLogger("app.http.paper_trading").exception("Daily analytics failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to build daily analytics") from exc
    return JSONResponse(content=safe)


@router.get("/daily-journal")
def get_daily_journal(
    journal_date: str | None = Query(default=None, description="YYYY-MM-DD IST"),
    service: PaperTradingService = Depends(get_service),
):
    from ..services.daily_analytics_service import DailyAnalyticsService
    das = DailyAnalyticsService(service.db, user_id=service.user_id)
    account = service._get_or_create_account()
    data = das._get_journal(account.id, journal_date or "")
    return JSONResponse(content=sanitize_for_json(data))


@router.put("/daily-journal")
def put_daily_journal(
    payload: dict,
    service: PaperTradingService = Depends(get_service),
):
    """Auto-save journal fields for the authenticated user's paper account only."""
    from ..services.daily_analytics_service import DailyAnalyticsService
    das = DailyAnalyticsService(service.db, user_id=service.user_id)
    try:
        data = das.save_journal(
            journal_date=payload.get("journal_date"),
            observations=payload.get("observations"),
            mistakes=payload.get("mistakes"),
            lessons=payload.get("lessons"),
            tomorrow_plan=payload.get("tomorrow_plan"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(content=sanitize_for_json(data))

@router.get("/engine-status")
async def get_engine_status(service: PaperTradingService = Depends(get_service)):
    logger = logging.getLogger("app.http")
    logger.info("ENGINE_STATUS_REQUESTED | timestamp=%s", datetime.datetime.now(timezone.utc).isoformat())
    start_time = time.time()
    try:
        status = await service.get_engine_status()
        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "ENGINE_STATUS_RESPONSE | timestamp=%s | response_duration_ms=%s | open_positions=%s | tracked_symbols=%s",
            datetime.datetime.now(timezone.utc).isoformat(),
            duration_ms,
            status.get("open_positions", 0),
            status.get("tracked_symbols", 0)
        )
        return JSONResponse(content=sanitize_for_json(status))
    except Exception as e:
        logger.error("ENGINE_STATUS_FAILED | timestamp=%s | error=%s", datetime.datetime.now(timezone.utc).isoformat(), str(e))
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
