from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..config.settings import ROOT_DIR
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


class WorkstationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_universes(self) -> list[UniverseGroup]:
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

    def save_scan(self, payload: SavedScanCreate) -> SavedScanItem:
        existing = self.db.scalar(select(SavedScan).where(SavedScan.name == payload.name))
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
        self.db.commit()
        self.db.refresh(row)
        return self._scan_item(row)

    def list_saved_scans(self) -> list[SavedScanItem]:
        rows = self.db.scalars(select(SavedScan).where(SavedScan.is_active == True).order_by(SavedScan.updated_at.desc())).all()
        return [self._scan_item(row) for row in rows]

    def delete_saved_scan(self, scan_id: int) -> None:
        row = self.db.get(SavedScan, scan_id)
        if row:
            row.is_active = False
            self.db.commit()

    def record_scan_history(
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
        self.db.commit()
        self.db.refresh(row)
        self._evaluate_scan_entry_alerts(row)
        return row

    def list_scan_history(self, limit: int = 20) -> list[ScanHistoryItem]:
        rows = self.db.scalars(select(ScanHistorySnapshot).order_by(ScanHistorySnapshot.created_at.desc()).limit(limit)).all()
        return [self._history_item(row) for row in rows]

    def compare_scan(self, current_id: int) -> ScanComparisonResponse:
        current = self.db.get(ScanHistorySnapshot, current_id)
        if not current:
            raise ValueError("Scan history item not found.")
        previous = self.db.scalar(
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

    def market_overview(self) -> MarketOverviewResponse:
        fyers = FyersService()
        indices = [
            self._market_item(fyers, "NSE:NIFTY50-INDEX", "NIFTY 50"),
            self._market_item(fyers, "NSE:NIFTYBANK-INDEX", "BANK NIFTY"),
            self._market_item(fyers, "BSE:SENSEX-INDEX", "SENSEX"),
        ]
        vix = self._market_item(fyers, "NSE:INDIAVIX-INDEX", "India VIX")
        movers = self._movers_from_latest_scan()
        return MarketOverviewResponse(
            indices=indices,
            vix=vix,
            top_gainers=movers[:5],
            top_losers=movers[-5:][::-1],
            updated_at=datetime.now(timezone.utc),
        )

    def create_alert(self, payload: AlertCreate) -> AlertItem:
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
        self.db.commit()
        self.db.refresh(row)
        return self._alert_item(row)

    def list_alerts(self) -> list[AlertItem]:
        rows = self.db.scalars(select(WorkstationAlert).order_by(WorkstationAlert.created_at.desc())).all()
        return [self._alert_item(row) for row in rows]

    def delete_alert(self, alert_id: int) -> None:
        row = self.db.get(WorkstationAlert, alert_id)
        if row:
            self.db.delete(row)
            self.db.commit()

    def get_risk_settings(self) -> RiskSettingsResponse:
        row = self._risk_row()
        return self._risk_response(row)

    def update_risk_settings(self, payload: RiskSettingsRequest) -> RiskSettingsResponse:
        row = self._risk_row()
        row.profile = payload.profile
        row.default_position_size_pct = payload.default_position_size_pct
        row.max_risk_per_trade_pct = payload.max_risk_per_trade_pct
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._risk_response(row)

    def api_health(self) -> ApiHealthResponse:
        fyers = FyersService()
        token = self.db.scalar(select(FyersToken).where(FyersToken.id == 1))
        db_path = settings.database_url.replace("sqlite:///./", "")
        db_file = ROOT_DIR / db_path
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
                "status": "ok" if db_file.exists() else "warning",
                "detail": str(db_file),
            },
        ]
        size_mb = round(db_file.stat().st_size / (1024 * 1024), 2) if db_file.exists() else 0.0
        return ApiHealthResponse(services=services, database_size_mb=size_mb, updated_at=datetime.now(timezone.utc))

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

    def _market_item(self, fyers: FyersService, symbol: str, label: str) -> MarketIndexItem:
        price = fyers.fetch_ltp(symbol)
        return MarketIndexItem(symbol=symbol, label=label, price=round(price, 2) if price else None, change_pct=None, source=fyers.get_ltp_source(symbol))

    def _movers_from_latest_scan(self) -> list[MarketIndexItem]:
        row = self.db.scalar(select(ScanHistorySnapshot).order_by(ScanHistorySnapshot.created_at.desc()).limit(1))
        if not row:
            return []
        payload = json.loads(row.payload_json)
        stocks = payload.get("all_analyzed_stocks") or payload.get("matches") or []
        sorted_rows = sorted(stocks, key=lambda item: float(item.get("screener_score") or 0), reverse=True)
        return [
            MarketIndexItem(
                symbol=item.get("symbol", ""),
                label=item.get("symbol", ""),
                price=item.get("close"),
                change_pct=float(item.get("screener_score") or 0),
                source="latest_scan_score",
            )
            for item in sorted_rows
        ]

    def _evaluate_scan_entry_alerts(self, row: ScanHistorySnapshot) -> None:
        current = set(self._history_symbols(row))
        previous = self.db.scalar(
            select(ScanHistorySnapshot)
            .where(ScanHistorySnapshot.id != row.id)
            .order_by(ScanHistorySnapshot.created_at.desc())
            .limit(1)
        )
        previous_symbols = set(self._history_symbols(previous))
        new_symbols = sorted(current - previous_symbols)
        if not new_symbols:
            return
        alerts = self.db.scalars(select(WorkstationAlert).where(WorkstationAlert.alert_type == "SCAN_ENTRY", WorkstationAlert.status == "ACTIVE")).all()
        for alert in alerts:
            alert.last_triggered_at = datetime.utcnow()
            alert.last_message = f"New scan entries: {', '.join(new_symbols[:8])}"
        self.db.commit()

    def _risk_row(self) -> RiskSettings:
        row = self.db.get(RiskSettings, 1)
        if row:
            return row
        row = RiskSettings(id=1)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def _risk_response(self, row: RiskSettings) -> RiskSettingsResponse:
        return RiskSettingsResponse(
            id=row.id,
            profile=row.profile,  # type: ignore[arg-type]
            default_position_size_pct=row.default_position_size_pct,
            max_risk_per_trade_pct=row.max_risk_per_trade_pct,
            updated_at=row.updated_at,
        )

    def _alert_item(self, row: WorkstationAlert) -> AlertItem:
        return AlertItem(
            id=row.id,
            alert_type=row.alert_type,  # type: ignore[arg-type]
            name=row.name,
            symbol=row.symbol,
            condition=row.condition,  # type: ignore[arg-type]
            target_price=row.target_price,
            scan_name=row.scan_name,
            status=row.status,
            last_triggered_at=row.last_triggered_at,
            last_message=row.last_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
