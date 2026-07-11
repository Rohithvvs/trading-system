"""Pydantic schemas for retail trading platform APIs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ─── Watchlists ───────────────────────────────────────────────────────────────

class WatchlistItemCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    exchange: str = Field(default="NSE", max_length=16)
    notes: str | None = Field(default=None, max_length=255)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        return v.strip().upper().replace("NSE:", "").replace("BSE:", "")


class WatchlistItemResponse(BaseModel):
    id: int
    symbol: str
    exchange: str
    sort_order: int
    notes: str | None = None
    company_name: str | None = None
    sector: str | None = None
    ltp: float | None = None
    change: float | None = None
    change_pct: float | None = None
    volume: float | None = None
    created_at: datetime


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    symbols: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return v.strip()


class WatchlistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_pinned: bool | None = None
    is_favorite: bool | None = None
    sort_by: Literal["alphabet", "change_pct", "volume", "sector", "custom"] | None = None
    sort_order: int | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class WatchlistReorderRequest(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class WatchlistItemsReorderRequest(BaseModel):
    ordered_item_ids: list[int] = Field(min_length=1)


class WatchlistImportRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    symbols: list[str] = Field(min_length=1)


class WatchlistResponse(BaseModel):
    id: int
    name: str
    sort_order: int
    is_pinned: bool
    is_favorite: bool
    sort_by: str
    item_count: int
    items: list[WatchlistItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WatchlistExportResponse(BaseModel):
    name: str
    symbols: list[str]
    exported_at: datetime


# ─── Quotes / Quote Board ─────────────────────────────────────────────────────

class QuoteBoardItem(BaseModel):
    symbol: str
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str = "NSE"
    ltp: float | None = None
    change: float | None = None
    change_pct: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    prev_close: float | None = None
    vwap: float | None = None
    volume: float | None = None
    bid: float | None = None
    ask: float | None = None
    bid_qty: float | None = None
    ask_qty: float | None = None
    upper_circuit: float | None = None
    lower_circuit: float | None = None
    market_status: str = "UNKNOWN"
    source: str = "NO_DATA"
    updated_at: datetime | None = None


class QuoteBoardResponse(BaseModel):
    items: list[QuoteBoardItem]
    total: int
    page: int
    page_size: int
    market_status: str
    updated_at: datetime


class IndexQuote(BaseModel):
    symbol: str
    label: str
    ltp: float | None = None
    change: float | None = None
    change_pct: float | None = None
    sparkline: list[float] = Field(default_factory=list)
    source: str = "NO_DATA"


class IndicesStripResponse(BaseModel):
    indices: list[IndexQuote]
    market_status: str
    updated_at: datetime


class HeatmapCell(BaseModel):
    symbol: str
    name: str
    change_pct: float | None = None
    ltp: float | None = None
    market_cap_bucket: str | None = None
    weight: float = 1.0


class HeatmapSector(BaseModel):
    sector: str
    change_pct: float | None = None
    stocks: list[HeatmapCell]
    stock_count: int


class HeatmapResponse(BaseModel):
    group_by: Literal["sector", "industry", "market_cap", "index"]
    sectors: list[HeatmapSector]
    updated_at: datetime


# ─── Symbol Search ────────────────────────────────────────────────────────────

class SymbolSearchResult(BaseModel):
    symbol: str
    company_name: str | None = None
    exchange: str = "NSE"
    sector: str | None = None
    industry: str | None = None
    isin: str | None = None
    series: str | None = None
    instrument_type: str = "EQ"
    universe: str | None = None
    is_favorite: bool = False


class SymbolSearchResponse(BaseModel):
    results: list[SymbolSearchResult]
    recent: list[SymbolSearchResult] = Field(default_factory=list)
    trending: list[SymbolSearchResult] = Field(default_factory=list)
    favorites: list[SymbolSearchResult] = Field(default_factory=list)
    query: str
    total: int


# ─── Chart ────────────────────────────────────────────────────────────────────

class ChartCandle(BaseModel):
    time: int  # unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


class IndicatorPoint(BaseModel):
    time: int
    value: float


class MacdPoint(BaseModel):
    time: int
    macd: float
    signal: float
    histogram: float


class ChartDataResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: list[ChartCandle]
    indicators: dict[str, Any] = Field(default_factory=dict)
    source: str
    updated_at: datetime


class ChartLayoutCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    symbol: str
    timeframe: str = "1D"
    chart_type: str = "candlestick"
    theme: str = "dark"
    indicators: list[dict[str, Any]] = Field(default_factory=list)
    drawings: list[dict[str, Any]] = Field(default_factory=list)
    is_default: bool = False


class ChartLayoutUpdate(BaseModel):
    name: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    chart_type: str | None = None
    theme: str | None = None
    indicators: list[dict[str, Any]] | None = None
    drawings: list[dict[str, Any]] | None = None
    is_default: bool | None = None


class ChartLayoutResponse(BaseModel):
    id: int
    name: str
    symbol: str
    timeframe: str
    chart_type: str
    theme: str
    indicators: list[dict[str, Any]]
    drawings: list[dict[str, Any]]
    is_default: bool
    created_at: datetime
    updated_at: datetime


# ─── Notifications ────────────────────────────────────────────────────────────

NotificationCategory = Literal[
    "price_alert",
    "scanner_alert",
    "order_update",
    "broker",
    "margin_call",
    "corporate_action",
    "news",
    "system",
]


class NotificationCreate(BaseModel):
    category: NotificationCategory
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    level: Literal["info", "success", "warning", "error"] = "info"
    symbol: str | None = None
    payload: dict[str, Any] | None = None


class NotificationResponse(BaseModel):
    id: int
    category: str
    title: str
    body: str
    level: str
    symbol: str | None = None
    payload: dict[str, Any] | None = None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_count: int
    page: int
    page_size: int


class NotificationMarkRequest(BaseModel):
    ids: list[int] | None = None  # None = all
    mark_read: bool = True


# ─── Order Ticket Preview ─────────────────────────────────────────────────────

class OrderPreviewRequest(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"] = "BUY"
    type: Literal["MARKET", "LIMIT", "SL", "SL-M", "STOP", "STOP_LIMIT", "BRACKET", "COVER"] = "MARKET"
    product_type: Literal["CNC", "MIS", "NRML"] = "CNC"
    validity: Literal["DAY", "IOC", "GTT"] = "DAY"
    qty: int = Field(ge=1, le=100000)
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    target: float | None = Field(default=None, gt=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        return v.strip().upper().replace("NSE:", "").replace("BSE:", "")


class OrderChargeBreakdown(BaseModel):
    brokerage: float
    stt: float
    exchange_txn: float
    sebi_fees: float
    gst: float
    stamp_duty: float
    total_charges: float


class OrderPreviewResponse(BaseModel):
    symbol: str
    side: str
    type: str
    product_type: str
    validity: str
    qty: int
    estimated_price: float
    order_value: float
    charges: OrderChargeBreakdown
    taxes_total: float
    margin_required: float
    funds_required: float
    available_funds: float
    expected_pnl: float | None = None
    risk_reward: float | None = None
    risk_checks: list[dict[str, Any]] = Field(default_factory=list)
    can_place: bool
    reject_reasons: list[str] = Field(default_factory=list)
    circuit_status: str | None = None
    freeze_qty: int | None = None


# ─── Risk Limits ──────────────────────────────────────────────────────────────

class RiskLimitsResponse(BaseModel):
    max_daily_loss: float
    max_trade_loss: float
    max_position_size: float
    max_exposure: float
    max_sector_exposure_pct: float
    max_leverage: float
    max_open_positions: int
    enabled: bool
    daily_pnl: float = 0.0
    current_exposure: float = 0.0
    open_positions: int = 0


class RiskLimitsUpdate(BaseModel):
    max_daily_loss: float | None = Field(default=None, gt=0)
    max_trade_loss: float | None = Field(default=None, gt=0)
    max_position_size: float | None = Field(default=None, gt=0)
    max_exposure: float | None = Field(default=None, gt=0)
    max_sector_exposure_pct: float | None = Field(default=None, gt=0, le=100)
    max_leverage: float | None = Field(default=None, gt=0)
    max_open_positions: int | None = Field(default=None, ge=1)
    enabled: bool | None = None


# ─── Holdings / Portfolio summary ─────────────────────────────────────────────

class HoldingItem(BaseModel):
    symbol: str
    qty: int
    avg_price: float
    ltp: float
    invested: float
    current_value: float
    pnl: float
    pnl_pct: float
    day_pnl: float
    day_pnl_pct: float
    sector: str | None = None
    product_type: str = "CNC"


class HoldingsResponse(BaseModel):
    holdings: list[HoldingItem]
    total_invested: float
    total_current_value: float
    total_pnl: float
    total_pnl_pct: float
    todays_pnl: float
    allocation: list[dict[str, Any]]
    sector_exposure: list[dict[str, Any]]


class PositionItem(BaseModel):
    id: int
    symbol: str
    qty: int
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    invested_value: float
    product_type: str
    position_type: Literal["OPEN", "CLOSED", "INTRADAY", "CARRY_FORWARD"]
    stop_loss: float | None = None
    target: float | None = None
    risk_reward: float | None = None
    created_at: datetime
    updated_at: datetime


class PositionsResponse(BaseModel):
    open: list[PositionItem]
    closed: list[PositionItem]
    intraday: list[PositionItem]
    carry_forward: list[PositionItem]
    total_mtm: float
    total_risk: float


class OrderListItem(BaseModel):
    id: int
    symbol: str
    side: str
    type: str
    product_type: str | None = None
    qty: int
    price: float | None = None
    stop_price: float | None = None
    status: str
    lifecycle_state: str
    filled_price: float | None = None
    created_at: datetime
    filled_at: datetime | None = None
    notes: str | None = None


class OrdersPageResponse(BaseModel):
    items: list[OrderListItem]
    total: int
    page: int
    page_size: int
    pending: int
    executed: int
    rejected: int
    cancelled: int
