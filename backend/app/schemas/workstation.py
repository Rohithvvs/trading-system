from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SavedScanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    mode: str = "swing"
    timeframe: str = "1d"
    lookback_window: int = Field(default=180, ge=30, le=730)
    top_n: int = Field(default=20, ge=1, le=50)
    universe: str = "NIFTY500"
    symbols: list[str] = Field(default_factory=list)
    filters: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class SavedScanItem(SavedScanCreate):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ScanHistoryItem(BaseModel):
    id: int
    scan_name: str
    screener_name: str
    mode: str
    timeframe: str
    lookback_window: int
    top_n: int
    universe: str
    scanned_symbols: int
    shortlisted_count: int
    buy_count: int
    watch_count: int
    data_source: str | None
    buy_symbols: list[str]
    watch_symbols: list[str]
    shortlisted_symbols: list[str]
    created_at: datetime


class ScanComparisonResponse(BaseModel):
    current_id: int
    previous_id: int | None
    new_symbols: list[str]
    removed_symbols: list[str]
    stayed_symbols: list[str]


class UniverseGroup(BaseModel):
    name: str
    symbols: list[str]
    count: int


class MarketIndexItem(BaseModel):
    symbol: str
    label: str
    price: float | None = None
    change_pct: float | None = None
    source: str


class MarketOverviewResponse(BaseModel):
    indices: list[MarketIndexItem]
    vix: MarketIndexItem
    top_gainers: list[MarketIndexItem]
    top_losers: list[MarketIndexItem]
    updated_at: datetime


class AlertCreate(BaseModel):
    alert_type: Literal["PRICE", "SCAN_ENTRY"]
    name: str = Field(min_length=2, max_length=120)
    symbol: str | None = None
    condition: Literal[">=", "<="] | None = None
    target_price: float | None = Field(default=None, gt=0)
    scan_name: str | None = None


class AlertItem(AlertCreate):
    id: int
    status: str
    last_triggered_at: datetime | None = None
    last_message: str | None = None
    created_at: datetime
    updated_at: datetime


class RiskSettingsRequest(BaseModel):
    profile: Literal["conservative", "moderate", "aggressive"] = "moderate"
    default_position_size_pct: float = Field(default=10.0, ge=1.0, le=100.0)
    max_risk_per_trade_pct: float = Field(default=2.0, ge=0.1, le=10.0)


class RiskSettingsResponse(RiskSettingsRequest):
    id: int
    updated_at: datetime


class ApiHealthItem(BaseModel):
    name: str
    status: Literal["ok", "warning", "error"]
    detail: str


class ApiHealthResponse(BaseModel):
    services: list[ApiHealthItem]
    database_size_mb: float
    updated_at: datetime
