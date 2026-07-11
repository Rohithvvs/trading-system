"""Phase 1 retail trading platform REST + WebSocket APIs."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..core.deps import get_current_user_id_sync
from ..db import get_sync_db
from ..schemas.retail import (
    ChartLayoutCreate,
    ChartLayoutUpdate,
    NotificationCreate,
    NotificationMarkRequest,
    OrderPreviewRequest,
    RiskLimitsUpdate,
    WatchlistCreate,
    WatchlistImportRequest,
    WatchlistItemCreate,
    WatchlistItemsReorderRequest,
    WatchlistReorderRequest,
    WatchlistUpdate,
)
from ..services.chart_service import ChartService
from ..services.market_quotes_service import MarketQuotesService
from ..services.notification_center_service import NotificationCenterService
from ..services.order_ticket_service import OrderTicketService
from ..services.paper_trading_service import PaperTradingService
from ..services.portfolio_views_service import PortfolioViewsService
from ..services.risk_enforcement_service import RiskEnforcementService
from ..services.symbol_search_service import SymbolSearchService
from ..services.watchlist_service import WatchlistService
from ..utils import sanitize_for_json

logger = logging.getLogger(__name__)
router = APIRouter(tags=["retail"])


def _uid(user_id: uuid.UUID = Depends(get_current_user_id_sync)) -> uuid.UUID:
    return user_id


# ─── Watchlists ───────────────────────────────────────────────────────────────

@router.get("/watchlists")
def list_watchlists(
    include_items: bool = Query(True),
    search: str | None = Query(None),
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    svc = WatchlistService(db, user_id)
    data = svc.list_watchlists(include_items=include_items, search=search)
    return JSONResponse(content=sanitize_for_json([w.model_dump(mode="json") for w in data]))


@router.post("/watchlists")
def create_watchlist(
    payload: WatchlistCreate,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    try:
        wl = WatchlistService(db, user_id).create_watchlist(payload)
        return JSONResponse(content=sanitize_for_json(wl.model_dump(mode="json")))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/watchlists/reorder")
def reorder_watchlists(
    payload: WatchlistReorderRequest,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    data = WatchlistService(db, user_id).reorder_watchlists(payload.ordered_ids)
    return JSONResponse(content=sanitize_for_json([w.model_dump(mode="json") for w in data]))


@router.post("/watchlists/import")
def import_watchlist(
    payload: WatchlistImportRequest,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    wl = WatchlistService(db, user_id).import_watchlist(payload)
    return JSONResponse(content=sanitize_for_json(wl.model_dump(mode="json")))


@router.get("/watchlists/{watchlist_id}")
def get_watchlist(
    watchlist_id: int,
    search: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    try:
        wl = WatchlistService(db, user_id).get_watchlist(watchlist_id, search=search, offset=offset, limit=limit)
        return JSONResponse(content=sanitize_for_json(wl.model_dump(mode="json")))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/watchlists/{watchlist_id}")
def update_watchlist(
    watchlist_id: int,
    payload: WatchlistUpdate,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    try:
        wl = WatchlistService(db, user_id).update_watchlist(watchlist_id, payload)
        return JSONResponse(content=sanitize_for_json(wl.model_dump(mode="json")))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/watchlists/{watchlist_id}")
def delete_watchlist(
    watchlist_id: int,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    try:
        WatchlistService(db, user_id).delete_watchlist(watchlist_id)
        return JSONResponse(content={"deleted": watchlist_id})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/watchlists/{watchlist_id}/items")
def add_watchlist_item(
    watchlist_id: int,
    payload: WatchlistItemCreate,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    try:
        wl = WatchlistService(db, user_id).add_item(watchlist_id, payload)
        return JSONResponse(content=sanitize_for_json(wl.model_dump(mode="json")))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/watchlists/{watchlist_id}/items/{item_id}")
def remove_watchlist_item(
    watchlist_id: int,
    item_id: int,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    try:
        wl = WatchlistService(db, user_id).remove_item(watchlist_id, item_id)
        return JSONResponse(content=sanitize_for_json(wl.model_dump(mode="json")))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/watchlists/{watchlist_id}/items/reorder")
def reorder_watchlist_items(
    watchlist_id: int,
    payload: WatchlistItemsReorderRequest,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    try:
        wl = WatchlistService(db, user_id).reorder_items(watchlist_id, payload.ordered_item_ids)
        return JSONResponse(content=sanitize_for_json(wl.model_dump(mode="json")))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/watchlists/{watchlist_id}/export")
def export_watchlist(
    watchlist_id: int,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    try:
        data = WatchlistService(db, user_id).export_watchlist(watchlist_id)
        return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ─── Market quotes / board / indices / heatmap ────────────────────────────────

@router.get("/market/quotes")
def batch_quotes(
    symbols: str = Query(..., description="Comma-separated symbols"),
    db: Session = Depends(get_sync_db),
    user_id: uuid.UUID = Depends(_uid),
):
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    data = MarketQuotesService(db).get_quotes_batch(syms)
    return JSONResponse(content=sanitize_for_json(data))


@router.get("/market/quote-board")
def quote_board(
    search: str | None = Query(None),
    sector: str | None = Query(None),
    sort_by: str = Query("symbol"),
    sort_dir: str = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_sync_db),
    user_id: uuid.UUID = Depends(_uid),
):
    data = MarketQuotesService(db).get_quote_board(
        search=search, sector=sector, sort_by=sort_by, sort_dir=sort_dir, page=page, page_size=page_size
    )
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


@router.get("/market/indices")
def market_indices(
    db: Session = Depends(get_sync_db),
    user_id: uuid.UUID = Depends(_uid),
):
    data = MarketQuotesService(db).get_indices_strip()
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


@router.get("/market/heatmap")
def market_heatmap(
    group_by: str = Query("sector"),
    db: Session = Depends(get_sync_db),
    user_id: uuid.UUID = Depends(_uid),
):
    if group_by not in ("sector", "industry", "market_cap", "index"):
        group_by = "sector"
    data = MarketQuotesService(db).get_heatmap(group_by=group_by)
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


# ─── Symbol search ────────────────────────────────────────────────────────────

@router.get("/search/symbols")
def search_symbols(
    q: str = Query("", max_length=80),
    limit: int = Query(20, ge=1, le=50),
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    data = SymbolSearchService(db, user_id).search(q, limit=limit)
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


@router.post("/search/symbols/{symbol}/record")
def record_symbol_search(
    symbol: str,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    SymbolSearchService(db, user_id).record_search(symbol)
    return JSONResponse(content={"recorded": symbol.upper()})


@router.post("/search/favorites/{symbol}")
def add_favorite(
    symbol: str,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    SymbolSearchService(db, user_id).add_favorite(symbol)
    return JSONResponse(content={"favorited": symbol.upper()})


@router.delete("/search/favorites/{symbol}")
def remove_favorite(
    symbol: str,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    SymbolSearchService(db, user_id).remove_favorite(symbol)
    return JSONResponse(content={"removed": symbol.upper()})


# ─── Charts (static paths before {symbol}) ────────────────────────────────────

@router.get("/charts/layouts/list")
def list_chart_layouts(
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    data = ChartService(db, user_id).list_layouts()
    return JSONResponse(content=sanitize_for_json([x.model_dump(mode="json") for x in data]))


@router.post("/charts/layouts")
def save_chart_layout(
    payload: ChartLayoutCreate,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    try:
        data = ChartService(db, user_id).save_layout(payload)
        return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/charts/layouts/{layout_id}")
def update_chart_layout(
    layout_id: int,
    payload: ChartLayoutUpdate,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    try:
        data = ChartService(db, user_id).update_layout(layout_id, payload)
        return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/charts/layouts/{layout_id}")
def delete_chart_layout(
    layout_id: int,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    ChartService(db, user_id).delete_layout(layout_id)
    return JSONResponse(content={"deleted": layout_id})


@router.get("/charts/{symbol}")
def chart_data(
    symbol: str,
    timeframe: str = Query("1D"),
    indicators: str = Query("EMA,SMA,VWAP,RSI,MACD,ATR,Supertrend,Bollinger"),
    lookback: int = Query(300, ge=50, le=2000),
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    inds = [x.strip() for x in indicators.split(",") if x.strip()]
    data = ChartService(db, user_id).get_chart_data(symbol, timeframe=timeframe, indicators=inds, lookback=lookback)
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


# ─── Notifications ────────────────────────────────────────────────────────────

@router.get("/notifications")
def list_notifications(
    category: str | None = Query(None),
    search: str | None = Query(None),
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    data = NotificationCenterService(db, user_id).list_notifications(
        category=category, search=search, unread_only=unread_only, page=page, page_size=page_size
    )
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


@router.get("/notifications/unread-count")
def unread_count(
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    n = NotificationCenterService(db, user_id).unread_count()
    return JSONResponse(content={"unread_count": n})


@router.post("/notifications")
def create_notification(
    payload: NotificationCreate,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    data = NotificationCenterService(db, user_id).create(payload)
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


@router.post("/notifications/mark")
def mark_notifications(
    payload: NotificationMarkRequest,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    n = NotificationCenterService(db, user_id).mark_read(ids=payload.ids, mark_read=payload.mark_read)
    return JSONResponse(content={"updated": n})


@router.post("/notifications/mark-all-read")
def mark_all_read(
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    n = NotificationCenterService(db, user_id).mark_all_read()
    return JSONResponse(content={"updated": n})


@router.delete("/notifications")
def delete_notifications(
    ids: str = Query(..., description="Comma-separated notification ids"),
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    n = NotificationCenterService(db, user_id).delete(id_list)
    return JSONResponse(content={"deleted": n})


# ─── Holdings / Positions / Orders ────────────────────────────────────────────

@router.get("/holdings")
def get_holdings(
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    data = PortfolioViewsService(db, user_id).get_holdings()
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


@router.get("/holdings/export")
def export_holdings_csv(
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    data = PortfolioViewsService(db, user_id).get_holdings()
    lines = ["symbol,qty,avg_price,ltp,invested,current_value,pnl,pnl_pct,day_pnl,sector"]
    for h in data.holdings:
        lines.append(
            f"{h.symbol},{h.qty},{h.avg_price},{h.ltp},{h.invested},{h.current_value},{h.pnl},{h.pnl_pct},{h.day_pnl},{h.sector or ''}"
        )
    csv = "\n".join(lines)

    def gen():
        yield csv

    return StreamingResponse(
        gen(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=holdings.csv"},
    )


@router.get("/positions")
def get_positions(
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    data = PortfolioViewsService(db, user_id).get_positions()
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


@router.get("/orders")
def get_orders(
    status: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    data = PortfolioViewsService(db, user_id).get_orders(
        status=status, search=search, page=page, page_size=page_size
    )
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


# ─── Order ticket preview + risk ──────────────────────────────────────────────

@router.post("/order-ticket/preview")
def order_preview(
    payload: OrderPreviewRequest,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    paper = PaperTradingService(db, user_id=user_id)
    account = paper._get_or_create_account()  # noqa: SLF001
    data = OrderTicketService(db, user_id, account).preview(payload)
    return JSONResponse(content=sanitize_for_json(data.model_dump(mode="json")))


@router.get("/risk/limits")
def get_risk_limits(
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    risk = RiskEnforcementService(db, user_id)
    limits = risk.get_or_create_limits()
    paper = PaperTradingService(db, user_id=user_id)
    account = paper._get_or_create_account()  # noqa: SLF001
    daily = float(risk._daily_pnl(account.id))  # noqa: SLF001
    exposure = float(risk._current_exposure(account.id))  # noqa: SLF001
    from sqlalchemy import func, select
    from ..models.paper_trading import PaperPosition

    open_n = (
        db.scalar(
            select(func.count()).select_from(PaperPosition).where(
                PaperPosition.account_id == account.id, PaperPosition.status == "OPEN"
            )
        )
        or 0
    )
    return JSONResponse(
        content=sanitize_for_json(
            {
                "max_daily_loss": float(limits.max_daily_loss),
                "max_trade_loss": float(limits.max_trade_loss),
                "max_position_size": float(limits.max_position_size),
                "max_exposure": float(limits.max_exposure),
                "max_sector_exposure_pct": float(limits.max_sector_exposure_pct),
                "max_leverage": float(limits.max_leverage),
                "max_open_positions": limits.max_open_positions,
                "enabled": limits.enabled,
                "daily_pnl": daily,
                "current_exposure": exposure,
                "open_positions": int(open_n),
            }
        )
    )


@router.put("/risk/limits")
def update_risk_limits(
    payload: RiskLimitsUpdate,
    user_id: uuid.UUID = Depends(_uid),
    db: Session = Depends(get_sync_db),
):
    row = RiskEnforcementService(db, user_id).update_limits(**payload.model_dump(exclude_unset=True))
    return JSONResponse(
        content=sanitize_for_json(
            {
                "max_daily_loss": float(row.max_daily_loss),
                "max_trade_loss": float(row.max_trade_loss),
                "max_position_size": float(row.max_position_size),
                "max_exposure": float(row.max_exposure),
                "max_sector_exposure_pct": float(row.max_sector_exposure_pct),
                "max_leverage": float(row.max_leverage),
                "max_open_positions": row.max_open_positions,
                "enabled": row.enabled,
            }
        )
    )


# ─── WebSocket live quotes ────────────────────────────────────────────────────

@router.websocket("/ws/quotes")
async def ws_quotes(websocket: WebSocket):
    """Stream live quotes for subscribed symbols. Client sends: {"action":"subscribe","symbols":["RELIANCE"]}"""
    await websocket.accept()
    subscribed: set[str] = set()
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                msg = json.loads(raw)
                action = msg.get("action")
                if action == "subscribe":
                    for s in msg.get("symbols") or []:
                        subscribed.add(str(s).upper().replace("NSE:", "").replace("-EQ", ""))
                elif action == "unsubscribe":
                    for s in msg.get("symbols") or []:
                        subscribed.discard(str(s).upper())
                elif action == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                logger.debug("ws message error: %s", exc)

            if subscribed:
                # Run sync quote fetch in thread
                def _fetch() -> dict[str, Any]:
                    from ..db.session import SessionLocal

                    db = SessionLocal()
                    try:
                        return MarketQuotesService(db).get_quotes_batch(list(subscribed))
                    finally:
                        db.close()

                quotes = await asyncio.to_thread(_fetch)
                await websocket.send_json(
                    {
                        "type": "quotes",
                        "data": sanitize_for_json(quotes),
                    }
                )
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        logger.info("ws quotes client disconnected")
    except Exception as exc:
        logger.warning("ws quotes error: %s", exc)
        try:
            await websocket.close()
        except Exception:
            pass
