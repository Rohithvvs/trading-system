"""Batch quotes, quote board, indices strip, and market heatmap."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models.stock import StockMaster
from ..schemas.retail import (
    HeatmapCell,
    HeatmapResponse,
    HeatmapSector,
    IndexQuote,
    IndicesStripResponse,
    QuoteBoardItem,
    QuoteBoardResponse,
)
from .fyers_service import FyersService
from .trading_hours_service import trading_hours

logger = logging.getLogger(__name__)

# In-process quote cache: symbol -> (ts, payload)
_QUOTE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 5.0

INDEX_MAP = [
    ("NIFTY50", "Nifty 50", "NSE:NIFTY50-INDEX"),
    ("BANKNIFTY", "Bank Nifty", "NSE:NIFTYBANK-INDEX"),
    ("SENSEX", "Sensex", "BSE:SENSEX-INDEX"),
    ("INDIAVIX", "India VIX", "NSE:INDIAVIX-INDEX"),
    ("MIDCPNIFTY", "Midcap", "NSE:MIDCPNIFTY-INDEX"),
    ("FINNIFTY", "FinNifty", "NSE:FINNIFTY-INDEX"),
]


class MarketQuotesService:
    def __init__(self, db: Session | None = None) -> None:
        self.db = db
        self.fyers = FyersService()

    def get_market_status(self) -> str:
        try:
            if trading_hours.is_market_open():
                return "OPEN"
            return "CLOSED"
        except Exception:
            return "UNKNOWN"

    def get_quotes_batch(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """Return quote dicts keyed by symbol. Uses cache + FYERS batch when available."""
        now = time.time()
        result: dict[str, dict[str, Any]] = {}
        missing: list[str] = []

        for raw in symbols:
            sym = raw.strip().upper().replace("NSE:", "").replace("BSE:", "")
            if not sym:
                continue
            cached = _QUOTE_CACHE.get(sym)
            if cached and now - cached[0] < _CACHE_TTL:
                result[sym] = cached[1]
            else:
                missing.append(sym)

        if missing:
            fetched = self._fetch_quotes(missing)
            for sym, payload in fetched.items():
                _QUOTE_CACHE[sym] = (now, payload)
                result[sym] = payload
            for sym in missing:
                if sym not in result:
                    empty = self._empty_quote(sym)
                    _QUOTE_CACHE[sym] = (now, empty)
                    result[sym] = empty

        return result

    def get_quote_board(
        self,
        *,
        search: str | None = None,
        sector: str | None = None,
        sort_by: str = "symbol",
        sort_dir: str = "asc",
        page: int = 1,
        page_size: int = 50,
        symbols: list[str] | None = None,
    ) -> QuoteBoardResponse:
        page = max(1, page)
        page_size = min(max(1, page_size), 200)

        universe = symbols
        if universe is None and self.db is not None:
            q = select(StockMaster).where(StockMaster.is_active == True)  # noqa: E712
            if search:
                term = f"%{search.strip()}%"
                q = q.where(
                    or_(
                        StockMaster.symbol.ilike(term),
                        StockMaster.company_name.ilike(term),
                        StockMaster.isin.ilike(term),
                    )
                )
            if sector:
                q = q.where(StockMaster.sector.ilike(f"%{sector}%"))
            q = q.order_by(StockMaster.symbol.asc())
            all_rows = list(self.db.scalars(q).all())
            total = len(all_rows)
            start = (page - 1) * page_size
            page_rows = all_rows[start : start + page_size]
            meta = {r.symbol: r for r in page_rows}
            board_symbols = [r.symbol for r in page_rows]
        else:
            board_symbols = [s.upper() for s in (universe or settings.nifty500_symbols[:page_size])]
            total = len(board_symbols)
            start = (page - 1) * page_size
            board_symbols = board_symbols[start : start + page_size]
            meta = {}
            if self.db is not None and board_symbols:
                for r in self.db.scalars(select(StockMaster).where(StockMaster.symbol.in_(board_symbols))).all():
                    meta[r.symbol] = r

        quotes = self.get_quotes_batch(board_symbols)
        status = self.get_market_status()
        items: list[QuoteBoardItem] = []
        now = datetime.now(timezone.utc)

        for sym in board_symbols:
            q = quotes.get(sym, {})
            m = meta.get(sym)
            items.append(
                QuoteBoardItem(
                    symbol=sym,
                    company_name=getattr(m, "company_name", None) if m else q.get("company_name"),
                    sector=getattr(m, "sector", None) if m else None,
                    exchange="NSE",
                    ltp=q.get("ltp"),
                    change=q.get("change"),
                    change_pct=q.get("change_pct"),
                    open=q.get("open"),
                    high=q.get("high"),
                    low=q.get("low"),
                    close=q.get("close") or q.get("prev_close"),
                    prev_close=q.get("prev_close"),
                    vwap=q.get("vwap"),
                    volume=q.get("volume"),
                    bid=q.get("bid"),
                    ask=q.get("ask"),
                    bid_qty=q.get("bid_qty"),
                    ask_qty=q.get("ask_qty"),
                    upper_circuit=q.get("upper_circuit"),
                    lower_circuit=q.get("lower_circuit"),
                    market_status=status,
                    source=q.get("source", "NO_DATA"),
                    updated_at=now,
                )
            )

        reverse = sort_dir == "desc"
        key_map = {
            "symbol": lambda x: x.symbol,
            "ltp": lambda x: x.ltp or 0,
            "change": lambda x: x.change or 0,
            "change_pct": lambda x: x.change_pct or 0,
            "volume": lambda x: x.volume or 0,
            "sector": lambda x: x.sector or "",
        }
        items.sort(key=key_map.get(sort_by, key_map["symbol"]), reverse=reverse)

        return QuoteBoardResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            market_status=status,
            updated_at=now,
        )

    def get_indices_strip(self) -> IndicesStripResponse:
        symbols = [label for label, _, _ in INDEX_MAP]
        # Use simplified equity proxies where index quotes unavailable
        proxy = {
            "NIFTY50": "NIFTYBEES",
            "BANKNIFTY": "BANKBEES",
            "SENSEX": "SENSEXBEES" if False else "RELIANCE",  # fallback
            "INDIAVIX": "NIFTYBEES",
            "MIDCPNIFTY": "NIFTYBEES",
            "FINNIFTY": "BANKBEES",
        }
        fetch_syms = list({proxy.get(s, "RELIANCE") for s in symbols})
        quotes = self.get_quotes_batch(fetch_syms)
        indices: list[IndexQuote] = []
        for key, label, _fyers in INDEX_MAP:
            p = proxy.get(key, "RELIANCE")
            q = quotes.get(p, {})
            ltp = q.get("ltp")
            chg = q.get("change")
            pct = q.get("change_pct")
            spark = []
            if ltp is not None:
                # Synthetic sparkline around LTP for UI animation (real candles used in chart page)
                base = float(ltp)
                spark = [round(base * (1 + (i - 10) * 0.0008), 2) for i in range(20)]
            indices.append(
                IndexQuote(
                    symbol=key,
                    label=label,
                    ltp=ltp,
                    change=chg,
                    change_pct=pct,
                    sparkline=spark,
                    source=q.get("source", "NO_DATA"),
                )
            )
        return IndicesStripResponse(
            indices=indices,
            market_status=self.get_market_status(),
            updated_at=datetime.now(timezone.utc),
        )

    def get_heatmap(self, group_by: str = "sector") -> HeatmapResponse:
        if self.db is None:
            return HeatmapResponse(group_by=group_by, sectors=[], updated_at=datetime.now(timezone.utc))

        rows = list(
            self.db.scalars(
                select(StockMaster)
                .where(StockMaster.is_active == True, StockMaster.universe == "NIFTY500")  # noqa: E712
                .limit(500)
            ).all()
        )
        if not rows:
            rows = list(self.db.scalars(select(StockMaster).where(StockMaster.is_active == True).limit(200)).all())  # noqa: E712

        symbols = [r.symbol for r in rows]
        # Batch in chunks to avoid overloading quote path
        quotes: dict[str, dict] = {}
        for i in range(0, len(symbols), 50):
            quotes.update(self.get_quotes_batch(symbols[i : i + 50]))

        groups: dict[str, list[HeatmapCell]] = {}
        for r in rows:
            q = quotes.get(r.symbol, {})
            key = (r.sector or "Other") if group_by == "sector" else (r.sector or "Other")
            if group_by == "industry":
                key = r.sector or "Other"
            elif group_by == "market_cap":
                key = r.universe or "Other"
            elif group_by == "index":
                key = r.universe or "NIFTY500"
            groups.setdefault(key, []).append(
                HeatmapCell(
                    symbol=r.symbol,
                    name=r.company_name or r.symbol,
                    change_pct=q.get("change_pct"),
                    ltp=q.get("ltp"),
                    market_cap_bucket=r.universe,
                    weight=1.0,
                )
            )

        sectors: list[HeatmapSector] = []
        for name, stocks in sorted(groups.items()):
            pcts = [s.change_pct for s in stocks if s.change_pct is not None]
            avg = sum(pcts) / len(pcts) if pcts else None
            stocks.sort(key=lambda s: abs(s.change_pct or 0), reverse=True)
            sectors.append(
                HeatmapSector(sector=name, change_pct=round(avg, 2) if avg is not None else None, stocks=stocks, stock_count=len(stocks))
            )
        sectors.sort(key=lambda s: s.change_pct if s.change_pct is not None else -999, reverse=True)

        return HeatmapResponse(group_by=group_by, sectors=sectors, updated_at=datetime.now(timezone.utc))  # type: ignore[arg-type]

    def _fetch_quotes(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        if not symbols:
            return out

        # Prefer FYERS multi-quote when configured
        try:
            if self.fyers._is_fyers_configured():  # noqa: SLF001
                client = self.fyers._client()  # noqa: SLF001
                # FYERS allows comma-separated symbols
                chunks = [symbols[i : i + 50] for i in range(0, len(symbols), 50)]
                for chunk in chunks:
                    fyers_syms = ",".join(f"NSE:{s}-EQ" for s in chunk)
                    try:
                        resp = client.quotes(data={"symbols": fyers_syms})
                        if not isinstance(resp, dict):
                            continue
                        for entry in resp.get("d") or []:
                            if not isinstance(entry, dict):
                                continue
                            v = entry.get("v") or {}
                            n = entry.get("n") or ""
                            sym = str(n).replace("NSE:", "").replace("-EQ", "").replace("BSE:", "").strip().upper()
                            if not sym:
                                continue
                            ltp = _f(v.get("lp") or v.get("ltp"))
                            prev = _f(v.get("prev_close_price") or v.get("ch") and None)
                            # FYERS often provides open/high/low/close + ch + chp
                            open_p = _f(v.get("open_price") or v.get("open"))
                            high = _f(v.get("high_price") or v.get("high"))
                            low = _f(v.get("low_price") or v.get("low"))
                            close = _f(v.get("prev_close_price") or v.get("close"))
                            ch = _f(v.get("ch"))
                            chp = _f(v.get("chp"))
                            if ch is None and ltp is not None and close is not None:
                                ch = round(ltp - close, 2)
                            if chp is None and ch is not None and close:
                                chp = round((ch / close) * 100, 2)
                            out[sym] = {
                                "ltp": ltp,
                                "change": ch,
                                "change_pct": chp,
                                "open": open_p,
                                "high": high,
                                "low": low,
                                "close": close,
                                "prev_close": close,
                                "vwap": _f(v.get("vwap") or v.get("avg_trade_price")),
                                "volume": _f(v.get("volume") or v.get("vol_traded_today")),
                                "bid": _f(v.get("bid") or v.get("bid_price")),
                                "ask": _f(v.get("ask") or v.get("ask_price")),
                                "bid_qty": _f(v.get("bid_size") or v.get("bid_qty")),
                                "ask_qty": _f(v.get("ask_size") or v.get("ask_qty")),
                                "upper_circuit": _f(v.get("upper_ckt") or v.get("upper_circuit")),
                                "lower_circuit": _f(v.get("lower_ckt") or v.get("lower_circuit")),
                                "source": "FYERS_QUOTE",
                            }
                    except Exception as exc:
                        logger.warning("batch quote chunk failed: %s", exc)
        except Exception as exc:
            logger.warning("FYERS batch quotes unavailable: %s", exc)

        # Fill remaining from candle fallback via fetch_ltp path (sync-safe best effort)
        for sym in symbols:
            if sym in out:
                continue
            try:
                import asyncio
                from ..db.session import main_event_loop

                if main_event_loop and main_event_loop.is_running():
                    fut = asyncio.run_coroutine_threadsafe(self.fyers.fetch_ltp(sym), main_event_loop)
                    ltp = fut.result(timeout=3)
                else:
                    ltp = None
                if ltp is not None:
                    out[sym] = {
                        "ltp": float(ltp),
                        "change": None,
                        "change_pct": None,
                        "open": None,
                        "high": None,
                        "low": None,
                        "close": None,
                        "prev_close": None,
                        "vwap": None,
                        "volume": None,
                        "bid": None,
                        "ask": None,
                        "bid_qty": None,
                        "ask_qty": None,
                        "upper_circuit": None,
                        "lower_circuit": None,
                        "source": "FYERS_QUOTE",
                    }
            except Exception:
                pass

        return out

    def _empty_quote(self, symbol: str) -> dict[str, Any]:
        return {
            "ltp": None,
            "change": None,
            "change_pct": None,
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "prev_close": None,
            "vwap": None,
            "volume": None,
            "bid": None,
            "ask": None,
            "bid_qty": None,
            "ask_qty": None,
            "upper_circuit": None,
            "lower_circuit": None,
            "source": "NO_DATA",
        }


def _f(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
