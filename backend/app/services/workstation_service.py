from __future__ import annotations

import csv
import json
import time as time_module
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..config.settings import ROOT_DIR
from ..core.response_cache import cache_get, cache_set, cached_async
from ..models.fyers_token import FyersToken
from ..models.workstation import RiskSettings, SavedScan, ScanHistorySnapshot, WorkstationAlert
from ..schemas.workstation import (
    AlertCreate,
    AlertItem,
    ApiHealthResponse,
    MarketIndexItem,
    MarketOverviewResponse,
    RiskSettingsRequest,
    RiskSettingsResponse,
    SavedScanCreate,
    SavedScanItem,
    ScanComparisonResponse,
    ScanHistoryItem,
    UniverseGroup,
)
from ..services.fyers_service import FyersService
from ..utils import get_logger

logger = get_logger("app.workstation")

_FALLBACK_INDICES: dict[str, str] = {
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "BANK NIFTY",
    "^BSESN": "SENSEX",
    "^INDIAVIX": "India VIX",
}

_NSE_SYMBOL_TO_FALLBACK = {
    "NSE:NIFTY50-INDEX": "^NSEI",
    "NSE:NIFTYBANK-INDEX": "^NSEBANK",
    "BSE:SENSEX-INDEX": "^BSESN",
    "NSE:INDIAVIX-INDEX": "^INDIAVIX",
}


async def _fetch_index_from_yfinance(symbol: str) -> dict | None:
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        data = ticker.history(period="2d")
        if data.empty:
            return None
        last = data.iloc[-1]
        prev = data.iloc[-2] if len(data) > 1 else last
        ltp = round(float(last["Close"]), 2)
        prev_close = round(float(prev["Close"]), 2)
        change_pct = round(((ltp - prev_close) / prev_close) * 100, 2) if prev_close else None
        return {"ltp": ltp, "change_pct": change_pct, "source": "YAHOO_FALLBACK"}
    except Exception as exc:
        logger.warning("YF_FALLBACK_FAILED | symbol=%s | error=%s", symbol, str(exc))
        return None


class WorkstationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_universes(self) -> list[UniverseGroup]:
        groups: dict[str, list[str]] = {"NIFTY500": list(settings.nifty500_symbols)}
        csv_path = Path(settings.nifty500_csv_path)
        if not csv_path.is_absolute():
            csv_path = ROOT_DIR / csv_path
        if csv_path.exists():
            with csv_path.open(newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    symbol = (row.get("Symbol") or "").strip().upper()
                    series = (row.get("Series") or "").strip().upper()
                    industry = (row.get("Industry") or "Other").strip() or "Other"
                    if not symbol:
                        continue
                    combined = f"{symbol}-{series}" if series else symbol
                    groups.setdefault(industry, []).append(combined)
        return [
            UniverseGroup(name=name, symbols=list(dict.fromkeys(symbols)), count=len(list(dict.fromkeys(symbols))))
            for name, symbols in sorted(groups.items(), key=lambda item: (item[0] != "NIFTY500", item[0]))
        ]

    async def save_scan(self, payload: SavedScanCreate) -> SavedScanItem:
        existing = await self.db.scalar(select(SavedScan).where(SavedScan.name == payload.name))
        row = existing or SavedScan(name=payload.name)
        row.mode = payload.mode
        row.timeframe = payload.timeframe
        row.lookback_window = payload.lookback_window
        row.top_n = payload.top_n
        row.universe = payload.universe
        row.symbols_json = json.dumps(payload.symbols)
        row.filters_json = json.dumps(payload.filters)
        row.is_active = True
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return self._scan_item(row)

    async def list_saved_scans(self) -> list[SavedScanItem]:
        rows = (await self.db.scalars(select(SavedScan).where(SavedScan.is_active).order_by(SavedScan.updated_at.desc()))).all()
        return [self._scan_item(row) for row in rows]

    async def delete_saved_scan(self, scan_id: int) -> None:
        row = await self.db.scalar(select(SavedScan).where(SavedScan.id == scan_id))
        if row:
            row.is_active = False
            await self.db.commit()

    async def record_scan_history(
        self,
        payload: dict,
        *,
        scan_name: str = "Manual Scan",
        mode: str = "swing",
        timeframe: str = "1d",
        lookback_window: int = 180,
        top_n: int = 20,
        universe: str = "NIFTY500",
    ) -> ScanHistorySnapshot:
        row = ScanHistorySnapshot(
            scan_name=scan_name,
            screener_name=payload.get("screener_name") or "Nifty 500 Swing Scanner",
            mode=mode,
            timeframe=timeframe,
            lookback_window=lookback_window,
            top_n=top_n,
            universe=universe,
            scanned_symbols=int(payload.get("scanned_symbols") or 0),
            shortlisted_count=len(payload.get("shortlisted_symbols") or []),
            buy_count=len(payload.get("buy_candidate_symbols") or []),
            watch_count=len(payload.get("watch_candidate_symbols") or []),
            data_source=payload.get("data_source"),
            payload_json=json.dumps(payload),
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        await self._evaluate_scan_entry_alerts(row)
        return row

    async def list_scan_history(self, limit: int = 20) -> list[ScanHistoryItem]:
        rows = (await self.db.scalars(select(ScanHistorySnapshot).order_by(ScanHistorySnapshot.created_at.desc()).limit(limit))).all()
        return [self._history_item(row) for row in rows]

    async def compare_scan(self, current_id: int) -> ScanComparisonResponse:
        current = await self.db.get(ScanHistorySnapshot, current_id)
        if not current:
            raise ValueError("Scan history item not found.")
        previous = await self.db.scalar(
            select(ScanHistorySnapshot)
            .where(ScanHistorySnapshot.id != current.id)
            .order_by(ScanHistorySnapshot.created_at.desc())
            .limit(1)
        )
        current_set = set(self._history_symbols(current))
        previous_set = set(self._history_symbols(previous)) if previous else set()
        return ScanComparisonResponse(
            current_id=current.id,
            previous_id=previous.id if previous else None,
            new_symbols=sorted(current_set - previous_set),
            removed_symbols=sorted(previous_set - current_set),
            stayed_symbols=sorted(current_set & previous_set),
        )

    async def market_overview(self) -> MarketOverviewResponse:
        cache_key = "workstation_market_overview"
        cached = cache_get(cache_key)
        if cached is not None:
            logger.info("MARKET_OVERVIEW_CACHE_HIT | key=%s", cache_key)
            return MarketOverviewResponse(**cached)

        logger.info("MARKET_OVERVIEW_CACHE_MISS | key=%s | fetching live", cache_key)
        fyers = FyersService.shared()

        indices_defs = [
            ("NSE:NIFTY50-INDEX", "NIFTY 50"),
            ("NSE:NIFTYBANK-INDEX", "BANK NIFTY"),
            ("BSE:SENSEX-INDEX", "SENSEX"),
        ]

        indices = []
        for sym, label in indices_defs:
            item = await self._market_item(fyers, sym, label)
            if item.price is None:
                fallback_sym = _NSE_SYMBOL_TO_FALLBACK.get(sym)
                if fallback_sym:
                    fb = await _fetch_index_from_yfinance(fallback_sym)
                    if fb:
                        item.price = fb["ltp"]
                        item.change_pct = fb["change_pct"]
                        logger.info("MARKET_OVERVIEW_FALLBACK | symbol=%s | source=YAHOO | ltp=%s", sym, fb["ltp"])
            indices.append(item)

        vix = await self._market_item(fyers, "NSE:INDIAVIX-INDEX", "India VIX")
        if vix.price is None:
            fb = await _fetch_index_from_yfinance("^INDIAVIX")
            if fb:
                vix.price = fb["ltp"]
                vix.change_pct = fb["change_pct"]

        movers = await self._movers_from_latest_scan()
        gainers = [m for m in movers if m.change_pct is not None and m.change_pct > 0][:5]
        losers = [m for m in movers if m.change_pct is not None and m.change_pct < 0][-5:][::-1]

        response = MarketOverviewResponse(
            indices=indices,
            vix=vix,
            top_gainers=gainers,
            top_losers=losers,
            updated_at=datetime.now(timezone.utc),
        )
        cache_set(cache_key, response.model_dump(mode="json"), ttl_seconds=120.0)
        logger.info("MARKET_OVERVIEW_CACHED | key=%s | ttl=120s", cache_key)
        return response

    async def create_alert(self, payload: AlertCreate) -> AlertItem:
        if payload.alert_type == "PRICE" and not (payload.symbol and payload.condition and payload.target_price):
            raise ValueError("Price alerts require symbol, condition and target_price.")
        if payload.alert_type == "SCAN_ENTRY" and not payload.scan_name:
            raise ValueError("Scan-entry alerts require scan_name.")
        row = WorkstationAlert(
            alert_type=payload.alert_type,
            name=payload.name,
            symbol=payload.symbol.strip().upper() if payload.symbol else None,
            condition=payload.condition,
            target_price=payload.target_price,
            scan_name=payload.scan_name,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return self._alert_item(row)

    async def list_alerts(self) -> list[AlertItem]:
        rows = (await self.db.scalars(select(WorkstationAlert).order_by(WorkstationAlert.created_at.desc()))).all()
        return [self._alert_item(row) for row in rows]

    async def delete_alert(self, alert_id: int) -> None:
        row = await self.db.get(WorkstationAlert, alert_id)
        if row:
            self.db.delete(row)
            await self.db.commit()

    async def get_risk_settings(self) -> RiskSettingsResponse:
        row = await self._risk_row()
        return self._risk_response(row)

    async def update_risk_settings(self, payload: RiskSettingsRequest) -> RiskSettingsResponse:
        row = await self._risk_row()
        row.profile = payload.profile
        row.default_position_size_pct = payload.default_position_size_pct
        row.max_risk_per_trade_pct = payload.max_risk_per_trade_pct
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return self._risk_response(row)

    async def api_health(self) -> ApiHealthResponse:
        fyers = FyersService()
        token = await self.db.scalar(select(FyersToken).where(FyersToken.id == 1))
        services = [
            {
                "name": "FYERS",
                "status": "ok" if fyers.is_fyers_sdk_available() and token and token.access_token else "warning",
                "detail": "SDK and access token available." if token and token.access_token else "Access token missing or SDK unavailable.",
            },
            {
                "name": "News",
                "status": "ok" if settings.news_api_key else "warning",
                "detail": "News API key configured." if settings.news_api_key else "News API key not configured.",
            },
            {
                "name": "LLM",
                "status": "ok" if settings.llm_api_key else "warning",
                "detail": f"{settings.llm_provider} model {settings.llm_model}" if settings.llm_api_key else "LLM key not configured.",
            },
            {
                "name": "Database",
                "status": "ok",
                "detail": "PostgreSQL",
            },
        ]
        return ApiHealthResponse(services=services, database_size_mb=0.0, updated_at=datetime.now(timezone.utc))

    def _scan_item(self, row: SavedScan) -> SavedScanItem:
        return SavedScanItem(
            id=row.id,
            name=row.name,
            mode=row.mode,
            timeframe=row.timeframe,
            lookback_window=row.lookback_window,
            top_n=row.top_n,
            universe=row.universe,
            symbols=json.loads(row.symbols_json or "[]"),
            filters=json.loads(row.filters_json or "{}"),
            is_active=bool(row.is_active),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _history_item(self, row: ScanHistorySnapshot) -> ScanHistoryItem:
        payload = json.loads(row.payload_json)
        return ScanHistoryItem(
            id=row.id,
            scan_name=row.scan_name,
            screener_name=row.screener_name,
            mode=row.mode,
            timeframe=row.timeframe,
            lookback_window=row.lookback_window,
            top_n=row.top_n,
            universe=row.universe,
            scanned_symbols=row.scanned_symbols,
            shortlisted_count=row.shortlisted_count,
            buy_count=row.buy_count,
            watch_count=row.watch_count,
            data_source=row.data_source,
            buy_symbols=payload.get("buy_candidate_symbols") or [],
            watch_symbols=payload.get("watch_candidate_symbols") or [],
            shortlisted_symbols=payload.get("shortlisted_symbols") or [],
            created_at=row.created_at,
        )

    def _history_symbols(self, row: ScanHistorySnapshot | None) -> list[str]:
        if not row:
            return []
        payload = json.loads(row.payload_json)
        return list(payload.get("shortlisted_symbols") or [])

    async def _market_item(self, fyers: FyersService, symbol: str, label: str) -> MarketIndexItem:
        start_t = time_module.time()
        quote = await fyers.fetch_quote(symbol)
        elapsed = int((time_module.time() - start_t) * 1000)
        price = None
        change_pct = None
        source = "unknown"
        if quote:
            price = round(float(quote.get("ltp", 0)), 2) if quote.get("ltp") else None
            change_pct = round(float(quote.get("change_pct", 0)), 2) if quote.get("change_pct") else None
            source = quote.get("source", "unknown")
            logger.info("MARKET_ITEM_FETCHED | symbol=%s | label=%s | ltp=%s | source=%s | duration_ms=%s", symbol, label, price, source, elapsed)
        else:
            logger.warning("MARKET_ITEM_FAILED | symbol=%s | label=%s | duration_ms=%s | quote=None", symbol, label, elapsed)
        return MarketIndexItem(symbol=symbol, label=label, price=price, change_pct=change_pct, source=source)

    async def _movers_from_latest_scan(self) -> list[MarketIndexItem]:
        row = await self.db.scalar(select(ScanHistorySnapshot).order_by(ScanHistorySnapshot.created_at.desc()).limit(1))
        if not row:
            logger.info("MOVERS_NO_SCAN_HISTORY | no snapshots found")
            return []
        payload = json.loads(row.payload_json)
        stocks = payload.get("all_analyzed_stocks") or payload.get("matches") or []
        if not stocks:
            logger.info("MOVERS_EMPTY | scan snapshot has no stock data")
            return []
        has_change = any(item.get("change_pct") is not None for item in stocks)
        if has_change:
            sorted_rows = sorted(stocks, key=lambda item: float(item.get("change_pct") or 0), reverse=True)
            result = [
                MarketIndexItem(
                    symbol=item.get("symbol", ""),
                    label=item.get("symbol", ""),
                    price=float(item.get("close", 0)) if item.get("close") else None,
                    change_pct=float(item.get("change_pct", 0)) if item.get("change_pct") else None,
                    source="scan_data",
                )
                for item in sorted_rows
            ]
            logger.info("MOVERS_FOUND | count=%s | source=scan_data", len(result))
            return result
        sorted_rows = sorted(stocks, key=lambda item: float(item.get("screener_score") or 0), reverse=True)
        result = [
            MarketIndexItem(
                symbol=item.get("symbol", ""),
                label=item.get("symbol", ""),
                price=float(item.get("close", 0)) if item.get("close") else None,
                change_pct=None,
                source="latest_scan_score",
            )
            for item in sorted_rows
        ]
        logger.info("MOVERS_FOUND | count=%s | source=latest_scan_score (no change_pct)", len(result))
        return result

    async def _evaluate_scan_entry_alerts(self, row: ScanHistorySnapshot) -> None:
        current = set(self._history_symbols(row))
        previous = await self.db.scalar(
            select(ScanHistorySnapshot)
            .where(ScanHistorySnapshot.id != row.id)
            .order_by(ScanHistorySnapshot.created_at.desc())
            .limit(1)
        )
        previous_symbols = set(self._history_symbols(previous))
        new_symbols = sorted(current - previous_symbols)
        if not new_symbols:
            return
        alerts = await self.db.scalars(select(WorkstationAlert).where(WorkstationAlert.alert_type == "SCAN_ENTRY", WorkstationAlert.status == "ACTIVE")).all()
        for alert in alerts:
            alert.last_triggered_at = datetime.now(timezone.utc)
            alert.last_message = f"New scan entries: {', '.join(new_symbols[:8])}"
        await self.db.commit()

    async def _risk_row(self) -> RiskSettings:
        row = await self.db.get(RiskSettings, 1)
        if row:
            return row
        row = RiskSettings(id=1)
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    def _risk_response(self, row: RiskSettings) -> RiskSettingsResponse:
        return RiskSettingsResponse(
            id=row.id,
            profile=row.profile,
            default_position_size_pct=row.default_position_size_pct,
            max_risk_per_trade_pct=row.max_risk_per_trade_pct,
            updated_at=row.updated_at,
        )

    def _alert_item(self, row: WorkstationAlert) -> AlertItem:
        return AlertItem(
            id=row.id,
            alert_type=row.alert_type,
            name=row.name,
            symbol=row.symbol,
            condition=row.condition,
            target_price=row.target_price,
            scan_name=row.scan_name,
            status=row.status,
            last_triggered_at=row.last_triggered_at,
            last_message=row.last_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
