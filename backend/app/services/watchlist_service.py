"""Multi-watchlist CRUD with reorder, pin/favorite, import/export, live quotes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from ..models.retail import Watchlist, WatchlistItem
from ..models.stock import StockMaster
from ..schemas.retail import (
    WatchlistCreate,
    WatchlistExportResponse,
    WatchlistImportRequest,
    WatchlistItemCreate,
    WatchlistItemResponse,
    WatchlistResponse,
    WatchlistUpdate,
)
from .market_quotes_service import MarketQuotesService


class WatchlistService:
    def __init__(self, db: Session, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id
        self.quotes = MarketQuotesService(db)

    def list_watchlists(self, include_items: bool = True, search: str | None = None) -> list[WatchlistResponse]:
        q = (
            select(Watchlist)
            .where(Watchlist.user_id == self.user_id)
            .order_by(Watchlist.is_pinned.desc(), Watchlist.is_favorite.desc(), Watchlist.sort_order.asc(), Watchlist.id.asc())
        )
        if include_items:
            q = q.options(selectinload(Watchlist.items))
        rows = list(self.db.scalars(q).all())
        if not rows:
            # Bootstrap default watchlist for new users
            default = self.create_watchlist(WatchlistCreate(name="My Watchlist", symbols=["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]))
            return [default]
        return [self._serialize(w, search=search) for w in rows]

    def get_watchlist(self, watchlist_id: int, search: str | None = None, offset: int = 0, limit: int = 100) -> WatchlistResponse:
        wl = self._get_owned(watchlist_id, with_items=True)
        return self._serialize(wl, search=search, offset=offset, limit=limit)

    def create_watchlist(self, payload: WatchlistCreate) -> WatchlistResponse:
        max_order = self.db.scalar(
            select(func.coalesce(func.max(Watchlist.sort_order), -1)).where(Watchlist.user_id == self.user_id)
        )
        wl = Watchlist(
            user_id=self.user_id,
            name=payload.name,
            sort_order=(max_order or 0) + 1,
        )
        self.db.add(wl)
        self.db.flush()
        for i, sym in enumerate(payload.symbols):
            symbol = sym.strip().upper().replace("NSE:", "").replace("BSE:", "")
            if not symbol:
                continue
            self.db.add(WatchlistItem(watchlist_id=wl.id, symbol=symbol, sort_order=i))
        self.db.commit()
        return self.get_watchlist(wl.id)

    def update_watchlist(self, watchlist_id: int, payload: WatchlistUpdate) -> WatchlistResponse:
        wl = self._get_owned(watchlist_id)
        if payload.name is not None:
            wl.name = payload.name
        if payload.is_pinned is not None:
            wl.is_pinned = payload.is_pinned
        if payload.is_favorite is not None:
            wl.is_favorite = payload.is_favorite
        if payload.sort_by is not None:
            wl.sort_by = payload.sort_by
        if payload.sort_order is not None:
            wl.sort_order = payload.sort_order
        wl.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return self.get_watchlist(watchlist_id)

    def delete_watchlist(self, watchlist_id: int) -> None:
        wl = self._get_owned(watchlist_id)
        self.db.delete(wl)
        self.db.commit()

    def reorder_watchlists(self, ordered_ids: list[int]) -> list[WatchlistResponse]:
        for idx, wid in enumerate(ordered_ids):
            wl = self.db.scalar(select(Watchlist).where(Watchlist.id == wid, Watchlist.user_id == self.user_id))
            if wl:
                wl.sort_order = idx
        self.db.commit()
        return self.list_watchlists()

    def add_item(self, watchlist_id: int, payload: WatchlistItemCreate) -> WatchlistResponse:
        wl = self._get_owned(watchlist_id, with_items=True)
        existing = next((i for i in wl.items if i.symbol == payload.symbol), None)
        if existing:
            return self.get_watchlist(watchlist_id)
        max_order = max((i.sort_order for i in wl.items), default=-1)
        self.db.add(
            WatchlistItem(
                watchlist_id=watchlist_id,
                symbol=payload.symbol,
                exchange=payload.exchange,
                notes=payload.notes,
                sort_order=max_order + 1,
            )
        )
        wl.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return self.get_watchlist(watchlist_id)

    def remove_item(self, watchlist_id: int, item_id: int) -> WatchlistResponse:
        wl = self._get_owned(watchlist_id)
        item = self.db.scalar(
            select(WatchlistItem).where(WatchlistItem.id == item_id, WatchlistItem.watchlist_id == wl.id)
        )
        if item:
            self.db.delete(item)
            wl.updated_at = datetime.now(timezone.utc)
            self.db.commit()
        return self.get_watchlist(watchlist_id)

    def reorder_items(self, watchlist_id: int, ordered_item_ids: list[int]) -> WatchlistResponse:
        wl = self._get_owned(watchlist_id)
        for idx, iid in enumerate(ordered_item_ids):
            item = self.db.scalar(
                select(WatchlistItem).where(WatchlistItem.id == iid, WatchlistItem.watchlist_id == wl.id)
            )
            if item:
                item.sort_order = idx
        wl.sort_by = "custom"
        wl.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return self.get_watchlist(watchlist_id)

    def import_watchlist(self, payload: WatchlistImportRequest) -> WatchlistResponse:
        name = (payload.name or f"Imported {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}").strip()
        return self.create_watchlist(WatchlistCreate(name=name, symbols=payload.symbols))

    def export_watchlist(self, watchlist_id: int) -> WatchlistExportResponse:
        wl = self._get_owned(watchlist_id, with_items=True)
        symbols = [i.symbol for i in sorted(wl.items, key=lambda x: x.sort_order)]
        return WatchlistExportResponse(name=wl.name, symbols=symbols, exported_at=datetime.now(timezone.utc))

    def _get_owned(self, watchlist_id: int, with_items: bool = False) -> Watchlist:
        q = select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.user_id == self.user_id)
        if with_items:
            q = q.options(selectinload(Watchlist.items))
        wl = self.db.scalar(q)
        if not wl:
            raise ValueError("Watchlist not found")
        return wl

    def _serialize(
        self,
        wl: Watchlist,
        search: str | None = None,
        offset: int = 0,
        limit: int = 500,
    ) -> WatchlistResponse:
        items = list(getattr(wl, "items", []) or [])
        items.sort(key=lambda i: i.sort_order)
        if search:
            term = search.strip().upper()
            items = [i for i in items if term in i.symbol.upper()]

        symbols = [i.symbol for i in items]
        meta = self._symbol_meta(symbols)
        quotes = self.quotes.get_quotes_batch(symbols) if symbols else {}

        # Apply sort
        sort_by = wl.sort_by or "custom"
        if sort_by == "alphabet":
            items.sort(key=lambda i: i.symbol)
        elif sort_by == "change_pct":
            items.sort(key=lambda i: quotes.get(i.symbol, {}).get("change_pct") or -9999, reverse=True)
        elif sort_by == "volume":
            items.sort(key=lambda i: quotes.get(i.symbol, {}).get("volume") or 0, reverse=True)
        elif sort_by == "sector":
            items.sort(key=lambda i: (meta.get(i.symbol, {}).get("sector") or "ZZZ", i.symbol))

        page_items = items[offset : offset + limit]
        serialized: list[WatchlistItemResponse] = []
        for item in page_items:
            q = quotes.get(item.symbol, {})
            m = meta.get(item.symbol, {})
            serialized.append(
                WatchlistItemResponse(
                    id=item.id,
                    symbol=item.symbol,
                    exchange=item.exchange,
                    sort_order=item.sort_order,
                    notes=item.notes,
                    company_name=m.get("company_name"),
                    sector=m.get("sector"),
                    ltp=q.get("ltp"),
                    change=q.get("change"),
                    change_pct=q.get("change_pct"),
                    volume=q.get("volume"),
                    created_at=item.created_at,
                )
            )

        return WatchlistResponse(
            id=wl.id,
            name=wl.name,
            sort_order=wl.sort_order,
            is_pinned=wl.is_pinned,
            is_favorite=wl.is_favorite,
            sort_by=wl.sort_by,
            item_count=len(items),
            items=serialized,
            created_at=wl.created_at,
            updated_at=wl.updated_at,
        )

    def _symbol_meta(self, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        rows = self.db.scalars(select(StockMaster).where(StockMaster.symbol.in_(symbols))).all()
        return {
            r.symbol: {"company_name": r.company_name, "sector": r.sector, "isin": r.isin}
            for r in rows
        }
