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
    type: Literal["MARKET", "LIMIT", "STOP"]
    qty: int
    price: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    status: Literal["PENDING", "FILLED", "CANCELLED", "REJECTED"]
    notes: str | None = None
    source_signal: str | None = None
    source_score: float | None = None
    source_confidence: float | None = None
    created_at: datetime
    filled_at: datetime | None = None
    filled_price: float | None = None


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
    source: Literal["FYERS_QUOTE", "CANDLE_FALLBACK"]
    updated_at: datetime


class PaperTradingDashboardResponse(BaseModel):
    account: PaperAccountSummary
    positions: list[PaperPositionResponse]
    open_orders: list[PaperOrderResponse]
    order_history: list[PaperOrderResponse]
    trades: list[PaperTradeHistoryItem]
    symbols: list[str]
    selected_workspace: PaperWorkspaceSnapshot | None = None


class PaperTradingAccountResetRequest(BaseModel):
    starting_balance: float = Field(default=100000.0, ge=1000.0)


class PaperOrderCreateRequest(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"] = "BUY"
    type: Literal["MARKET", "LIMIT", "STOP"] = "MARKET"
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
