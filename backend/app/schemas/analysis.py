from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class AnalysisMode(str, Enum):
    intraday = "intraday"
    swing = "swing"
    both = "both"


class TimeframeConfig(BaseModel):
    intraday: str = "5m"
    swing: str = "1d"
    lookback_window: int = 90


class AnalysisRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=25)
    mode: AnalysisMode = AnalysisMode.both
    timeframe: TimeframeConfig = Field(default_factory=TimeframeConfig)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            symbol = value.strip().upper()
            if symbol:
                cleaned.append(symbol)
        if not cleaned:
            raise ValueError("At least one stock symbol is required.")
        return list(dict.fromkeys(cleaned))


class ScreenerRequest(BaseModel):
    mode: AnalysisMode = AnalysisMode.swing
    timeframe: TimeframeConfig = Field(default_factory=TimeframeConfig)
    symbols: list[str] = Field(default_factory=list, max_length=200)
    top_n: int = Field(default=20, ge=1, le=50)

    @field_validator("symbols")
    @classmethod
    def validate_optional_symbols(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            symbol = value.strip().upper()
            if symbol:
                cleaned.append(symbol)
        return list(dict.fromkeys(cleaned))


class OHLCVPoint(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class TechnicalAnalysisResult(BaseModel):
    mode: AnalysisMode
    signal: str
    score: float
    indicators: dict[str, float | str | bool]
    summary: str


class ArticleItem(BaseModel):
    title: str
    description: str
    source: str
    url: str
    published_at: datetime
    sentiment_score: float


class BacktestResult(BaseModel):
    mode: AnalysisMode
    strategy_name: str
    total_return: float
    cagr: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    trade_count: int
    verdict: str
    equity_curve: list[dict[str, float | str]]


class RecommendationReasoning(BaseModel):
    bullets: list[str]
    risk_factors: list[str]
    invalidation_signals: list[str]


class TradePlan(BaseModel):
    mode: AnalysisMode
    strategy_name: str
    setup_type: str
    timeframe: str
    bias: str
    entry_low: float
    entry_high: float
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float | None = None
    risk_reward_ratio: float
    notes: str


class FinalRecommendation(BaseModel):
    action: str
    confidence: float
    score: float
    reasoning: RecommendationReasoning
    trade_plans: list[TradePlan]
    summary: str


class StockAnalysisResult(BaseModel):
    symbol: str
    ohlcv: list[OHLCVPoint]
    technical: list[TechnicalAnalysisResult]
    news_articles: list[ArticleItem]
    news_summary: str
    news_sentiment_label: str
    news_sentiment_score: float
    backtests: list[BacktestResult]
    recommendation: FinalRecommendation
    disclaimer: str
    data_source: str = "unknown"
    data_quality: dict[str, str | int | bool | float] = Field(default_factory=dict)
    trade_readiness: str = "Review manually"
    confidence_breakdown: dict[str, float | str] = Field(default_factory=dict)


class RankingItem(BaseModel):
    rank: int
    symbol: str
    overall_score: float
    recommendation: str
    best_for_mode: str | None = None


class RankingsResponse(BaseModel):
    rankings: list[RankingItem]
    buy_rankings: list[RankingItem] = Field(default_factory=list)
    watch_rankings: list[RankingItem] = Field(default_factory=list)
    best_intraday_candidate: str | None
    best_swing_candidate: str | None
    disclaimer: str


class AnalysisResponse(BaseModel):
    items: list[StockAnalysisResult]
    rankings: RankingsResponse
    disclaimer: str


class FullAnalysisResponse(AnalysisResponse):
    generated_at: datetime


class ScreenerConditionResult(BaseModel):
    symbol: str
    close: float
    ema_20: float
    sma_30: float
    sma_50: float
    sma_100: float
    sma_200: float
    macd: float
    macd_signal: float
    supertrend: float
    volume: int
    previous_volume: int
    screener_score: float
    technical_signal: str
    technical_score: float
    conditions: dict[str, bool]
    matched: bool


class ScreenerResponse(BaseModel):
    scanned_symbols: int
    screener_name: str
    data_valid_symbols: list[str]
    eligible_symbols: list[str]
    shortlisted_symbols: list[str]
    buy_candidate_symbols: list[str]
    watch_candidate_symbols: list[str]
    matched_symbols: list[str]
    matches: list[ScreenerConditionResult]
    analysis: FullAnalysisResponse | None = None
    disclaimer: str
    data_source: str = "unknown"
    data_warning: str | None = None
    market_context: dict[str, str | float | bool] = Field(default_factory=dict)
