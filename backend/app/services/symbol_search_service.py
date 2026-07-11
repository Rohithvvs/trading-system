"""Professional symbol search with recent, trending, favorites, caching."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models.retail import FavoriteSymbol, SymbolSearchHistory
from ..models.stock import StockMaster
from ..schemas.retail import SymbolSearchResponse, SymbolSearchResult

_SEARCH_CACHE: dict[str, tuple[float, list[SymbolSearchResult]]] = {}
_CACHE_TTL = 30.0


class SymbolSearchService:
    def __init__(self, db: Session, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def search(self, query: str, limit: int = 20) -> SymbolSearchResponse:
        q = (query or "").strip()
        limit = min(max(1, limit), 50)
        results: list[SymbolSearchResult] = []

        if q:
            cache_key = f"{q.upper()}:{limit}"
            cached = _SEARCH_CACHE.get(cache_key)
            if cached and time.time() - cached[0] < _CACHE_TTL:
                results = cached[1]
            else:
                results = self._query_db(q, limit)
                _SEARCH_CACHE[cache_key] = (time.time(), results)

        fav_set = self._favorite_set()
        for r in results:
            r.is_favorite = r.symbol in fav_set

        return SymbolSearchResponse(
            results=results,
            recent=self._recent(fav_set),
            trending=self._trending(fav_set),
            favorites=self._favorites(fav_set),
            query=q,
            total=len(results),
        )

    def record_search(self, symbol: str, query: str | None = None) -> None:
        symbol = symbol.strip().upper()
        self.db.add(
            SymbolSearchHistory(
                user_id=self.user_id,
                symbol=symbol,
                query=query,
                searched_at=datetime.now(timezone.utc),
            )
        )
        # Keep last 50 per user
        ids = list(
            self.db.scalars(
                select(SymbolSearchHistory.id)
                .where(SymbolSearchHistory.user_id == self.user_id)
                .order_by(SymbolSearchHistory.searched_at.desc())
                .offset(50)
            ).all()
        )
        if ids:
            self.db.execute(delete(SymbolSearchHistory).where(SymbolSearchHistory.id.in_(ids)))
        self.db.commit()

    def add_favorite(self, symbol: str) -> None:
        symbol = symbol.strip().upper()
        existing = self.db.scalar(
            select(FavoriteSymbol).where(FavoriteSymbol.user_id == self.user_id, FavoriteSymbol.symbol == symbol)
        )
        if not existing:
            self.db.add(FavoriteSymbol(user_id=self.user_id, symbol=symbol))
            self.db.commit()

    def remove_favorite(self, symbol: str) -> None:
        symbol = symbol.strip().upper()
        row = self.db.scalar(
            select(FavoriteSymbol).where(FavoriteSymbol.user_id == self.user_id, FavoriteSymbol.symbol == symbol)
        )
        if row:
            self.db.delete(row)
            self.db.commit()

    def _query_db(self, query: str, limit: int) -> list[SymbolSearchResult]:
        term = f"%{query}%"
        rows = list(
            self.db.scalars(
                select(StockMaster)
                .where(
                    StockMaster.is_active == True,  # noqa: E712
                    or_(
                        StockMaster.symbol.ilike(term),
                        StockMaster.company_name.ilike(term),
                        StockMaster.isin.ilike(term),
                        StockMaster.sector.ilike(term),
                    ),
                )
                .order_by(StockMaster.symbol.asc())
                .limit(limit)
            ).all()
        )
        if not rows:
            # Fallback to nifty500 config list
            q_up = query.upper()
            matches = [s for s in settings.nifty500_symbols if q_up in s.upper()][:limit]
            return [
                SymbolSearchResult(symbol=s, company_name=s, instrument_type="EQ", universe="NIFTY500")
                for s in matches
            ]
        return [self._to_result(r) for r in rows]

    def _recent(self, fav_set: set[str]) -> list[SymbolSearchResult]:
        rows = list(
            self.db.scalars(
                select(SymbolSearchHistory)
                .where(SymbolSearchHistory.user_id == self.user_id)
                .order_by(SymbolSearchHistory.searched_at.desc())
                .limit(20)
            ).all()
        )
        seen: set[str] = set()
        out: list[SymbolSearchResult] = []
        for r in rows:
            if r.symbol in seen:
                continue
            seen.add(r.symbol)
            res = self._lookup(r.symbol)
            res.is_favorite = r.symbol in fav_set
            out.append(res)
            if len(out) >= 10:
                break
        return out

    def _trending(self, fav_set: set[str]) -> list[SymbolSearchResult]:
        # Trending = most frequent recent searches globally (last 100 records) or top nifty names
        try:
            rows = self.db.execute(
                select(SymbolSearchHistory.symbol, func.count().label("c"))
                .group_by(SymbolSearchHistory.symbol)
                .order_by(func.count().desc())
                .limit(10)
            ).all()
            if rows:
                out = []
                for sym, _ in rows:
                    res = self._lookup(sym)
                    res.is_favorite = sym in fav_set
                    out.append(res)
                return out
        except Exception:
            pass
        defaults = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC"]
        return [self._lookup(s, fav_set) for s in defaults]

    def _favorites(self, fav_set: set[str]) -> list[SymbolSearchResult]:
        return [self._lookup(s, fav_set) for s in sorted(fav_set)]

    def _favorite_set(self) -> set[str]:
        return set(
            self.db.scalars(select(FavoriteSymbol.symbol).where(FavoriteSymbol.user_id == self.user_id)).all()
        )

    def _lookup(self, symbol: str, fav_set: set[str] | None = None) -> SymbolSearchResult:
        row = self.db.scalar(select(StockMaster).where(StockMaster.symbol == symbol.upper()))
        if row:
            res = self._to_result(row)
        else:
            res = SymbolSearchResult(symbol=symbol.upper(), company_name=symbol.upper(), instrument_type="EQ")
        if fav_set is not None:
            res.is_favorite = symbol.upper() in fav_set
        return res

    def _to_result(self, r: StockMaster) -> SymbolSearchResult:
        series = (r.series or "EQ").upper()
        instrument = "EQ"
        if "ETF" in series or (r.company_name and "ETF" in r.company_name.upper()):
            instrument = "ETF"
        elif series in ("FUT", "FUTSTK", "FUTIDX"):
            instrument = "FUTURE"
        elif series in ("OPT", "OPTSTK", "OPTIDX"):
            instrument = "OPTION"
        return SymbolSearchResult(
            symbol=r.symbol,
            company_name=r.company_name,
            exchange="NSE",
            sector=r.sector,
            industry=r.sector,
            isin=r.isin,
            series=r.series,
            instrument_type=instrument,
            universe=r.universe,
        )
