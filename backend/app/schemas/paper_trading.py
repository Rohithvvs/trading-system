from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .analysis import OHLCVPoint


class PaperAccountSummary(BaseModel):
    account_id: int
    account_name: str
    base_currency: str = "INR"
    starting_balance: float
    balance: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    total_invested: float
    reserved_cash: float
    available_cash: float
    open_positions_count: int
    open_orders_count: int
    max_risk_per_trade: float
    updated_at: datetime


class PaperPositionResponse(BaseModel):
    id: int
    symbol: str
    qty: int
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    invested_value: float
    stop_loss: float | None = None
    target: float | None = None
    lifecycle_state: str = "OPEN_POSITION"
    monitor_enabled: bool = True
    paused_reason: str | None = None
    risk_reward_ratio: float | None = None
    source_signal: str | None = None
    source_score: float | None = None
    source_confidence: float | None = None
    created_at: datetime
    updated_at: datetime


class PaperOrderResponse(BaseModel):
    id: int
    symbol: str
    side: Literal["BUY", "SELL"]
    type: Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT", "GTT"]
    qty: int
    price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    status: Literal["PENDING", "FILLED", "CANCELLED", "REJECTED"]
    lifecycle_state: Literal[
        "PENDING_ENTRY",
        "ENTRY_FILLED",
        "OPEN_POSITION",
        "EXIT_FILLED",
        "CANCELLED",
        "TOKEN_EXPIRED_PAUSED",
        "MARKET_CLOSED_WAITING",
        "ERROR_RETRYING",
    ] = "PENDING_ENTRY"
    requested_entry_price: float | None = None
    monitor_enabled: bool = True
    paused_reason: str | None = None
    notes: str | None = None
    source_signal: str | None = None
    source_score: float | None = None
    source_confidence: float | None = None
    created_at: datetime
    filled_at: datetime | None = None
    filled_price: float | None = None

    product_type: str | None = None


class PaperTradeHistoryItem(BaseModel):
    id: int
    symbol: str
    qty: int
    entry_price: float
    exit_price: float
    pnl: float
    pnl_percent: float
    notes: str | None = None
    source_signal: str | None = None
    source_score: float | None = None
    source_confidence: float | None = None
    opened_at: datetime
    closed_at: datetime
    holding_period_hours: float
    exit_reason: str | None = None


class PaperWorkspaceSnapshot(BaseModel):
    symbol: str
    current_price: float
    candles: list[OHLCVPoint]
    ema_20: float | None = None
    supertrend: float | None = None
    source_signal: str | None = None
    source_score: float | None = None
    source_confidence: float | None = None


class PaperQuoteResponse(BaseModel):
    symbol: str
    current_price: float
    source: Literal["FYERS_QUOTE", "CANDLE_FALLBACK", "NO_DATA"]
    updated_at: datetime


class PaperTradingDashboardResponse(BaseModel):
    account: PaperAccountSummary
    positions: list[PaperPositionResponse]
    open_orders: list[PaperOrderResponse]
    order_history: list[PaperOrderResponse]
    trades: list[PaperTradeHistoryItem]
    symbols: list[str]
    selected_workspace: PaperWorkspaceSnapshot | None = None


class MarketEngineStatusResponse(BaseModel):
    status: str
    market_hours_active: bool
    websocket_connected: bool
    token_status: str
    paused_reason: str | None = None
    last_heartbeat_at: datetime | None = None
    last_tick_at: datetime | None = None
    active_monitored_symbols_count: int = 0
    active_symbols: list[str] = Field(default_factory=list)
    trading_date: str | None = None


class PaperTradingAccountResetRequest(BaseModel):
    starting_balance: float = Field(default=1000000.0, ge=1000.0)


class PaperAccountCapitalUpdateRequest(BaseModel):
    amount: float = Field(default=1000000.0, ge=1000.0)


class TransactionItem(BaseModel):
    id: str
    timestamp: datetime
    symbol: str | None = None
    action: str
    amount: float
    balance_after: float
    qty: int | None = None
    price: float | None = None


class TransactionPageResponse(BaseModel):
    items: list[TransactionItem]
    page: int
    per_page: int
    total: int
    total_pages: int


class PaperOrderCreateRequest(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"] = "BUY"
    type: Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT", "GTT"] = "MARKET"
    product_type: Literal["MIS", "CNC", "NRML"] = "CNC"
    qty: int = Field(ge=1, le=100000)
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    target: float | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=1000)
    source_signal: str | None = Field(default=None, max_length=16)
    source_score: float | None = None
    source_confidence: float | None = None

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("Symbol is required.")
        return symbol


class PaperOrderUpdateRequest(BaseModel):
    qty: int | None = Field(default=None, ge=1, le=100000)
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    target: float | None = Field(default=None, gt=0)
    type: Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT", "GTT"] | None = None
    product_type: Literal["MIS", "CNC", "NRML"] | None = None


class PaperPositionUpdateRequest(BaseModel):
    stop_loss: float | None = Field(default=None, gt=0)
    target: float | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=1000)


class RecommendationPrefillRequest(BaseModel):
    symbol: str
    suggested_entry: float | None = None
    suggested_stop: float | None = None
    suggested_targets: list[float] = Field(default_factory=list)
    recommendation_meta: dict[str, float | str]


class RecommendationPrefillResponse(BaseModel):
    symbol: str
    side: Literal["BUY"] = "BUY"
    type: Literal["LIMIT"] = "LIMIT"
    qty: int = 1
    limit_price: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    note: str


class PaperOrderActionResponse(BaseModel):
    account: PaperAccountSummary
    order: PaperOrderResponse | None = None
    position: PaperPositionResponse | None = None
    trade: PaperTradeHistoryItem | None = None
    message: str


class NotificationItem(BaseModel):
    id: int
    message: str
    level: Literal["info", "success", "error"] = "info"
    is_read: bool
    created_at: datetime


class NotificationMarkReadRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


class AlertCreateRequest(BaseModel):
    symbol: str
    condition: Literal[">=", "<="]
    price: float


class AlertItem(BaseModel):
    id: int
    symbol: str
    condition: str
    target_price: float
    status: str
    created_at: datetime
    triggered_at: datetime | None = None
    triggered_price: float | None = None


class DailyPnlPoint(BaseModel):
    date: str
    pnl: float


class HoldingPeriodItem(BaseModel):
    symbol: str
    avg_holding_minutes: float
    total_trades: int
    win_rate_pct: float


class AnalyticsResponse(BaseModel):
    total_trades: int
    win_rate_pct: float
    profit_factor: float | None = None
    average_profit: float | None = None
    average_loss: float | None = None
    best_trade_symbol: str | None = None
    best_trade_amount: float | None = None
    worst_trade_symbol: str | None = None
    worst_trade_amount: float | None = None
    daily_pnl: list[DailyPnlPoint]
    cumulative_pnl: list[DailyPnlPoint]
    wins: int
    losses: int
    holding_periods: list[HoldingPeriodItem]
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    current_streak_type: str = "none"
    current_streak_count: int = 0
