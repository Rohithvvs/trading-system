from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnalysisMode(str, Enum):
    intraday = "intraday"
    swing = "swing"
    both = "both"


class TimeframeConfig(BaseModel):
    intraday: str = "5m"
    swing: str = "1d"
    lookback_window: int = Field(default=260, ge=1, le=2000)


class AnalysisRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=25)
    mode: AnalysisMode = AnalysisMode.swing
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


class FundamentalAnalysisResult(BaseModel):
    revenue_growth_pct: float | None = None
    profit_margin_pct: float | None = None
    debt_to_equity: float | None = None
    pe_ratio: float | None = None
    fundamental_score: float
    summary: str



class ArticleItem(BaseModel):
    title: str
    description: str = ""
    source: str = "unknown"
    url: str = ""
    published_at: datetime | None = None
    sentiment_score: float = 0.0


class BacktestResult(BaseModel):
    mode: AnalysisMode
    strategy_name: str
    total_return: float
    cagr: float | None = None
    max_drawdown: float
    win_rate: float
    profit_factor: float
    trade_count: int
    verdict: str
    equity_curve: list[dict[str, float | str]]
    # Extended metrics
    trades: list[dict] = Field(default_factory=list)
    monthly_returns: list[dict] = Field(default_factory=list)
    sharpe_ratio: float = 0.0
    best_trade: dict | None = None
    worst_trade: dict | None = None
    # Realism Foundation metrics
    gross_total_return: float | None = None
    gross_cagr: float | None = None
    gross_max_drawdown: float | None = None
    gross_win_rate: float | None = None
    gross_profit_factor: float | None = None
    gross_sharpe_ratio: float | None = None
    cost_scenario: str | None = None
    total_transaction_costs: float | None = None
    total_slippage: float | None = None
    position_sizing_pct: float | None = None
    cagr_warning: str | None = None
    # FEAT-008 — Realistic Trade Execution Model metadata
    feat008_enabled: bool | None = None
    feat008_execution_model: str | None = None
    feat008_slippage_bps: float | None = None
    feat008_brokerage_bps: float | None = None
    feat008_statutory_bps: float | None = None
    feat008_total_cost_bps_per_side: float | None = None
    feat008_trades_simulated: int | None = None
    feat008_trades_skipped: int | None = None
    feat008_win_rate: float | None = None
    feat008_profit_factor: float | None = None
    feat008_legacy_win_rate: float | None = None
    feat008_legacy_profit_factor: float | None = None
    feat008_score_used: str | None = None
    feat008_explanation: str | None = None


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
    # Execution guidance
    partial_exit: str | None = None
    suggested_holding_days: int | None = None
    trailing_stop_atr_multiplier: float | None = None


class FinalRecommendation(BaseModel):
    action: str
    confidence: float
    score: float
    reasoning: RecommendationReasoning
    trade_plans: list[TradePlan]
    summary: str
    # FEAT-004 — Market Regime Overlay (optional logging/metadata fields)
    # Defaults to None; populated when FEAT-004 runs. Contains the full
    # feat004 log payload (regime, benchmark trend inputs, score adjustment,
    # abstained reason, sector metadata, explanation, etc.).
    feat004: dict | None = None
    # FEAT-007 — Sector Relative Strength Overlay (optional logging fields)
    # All default to None; populated only when FEAT-007 is wired and enabled.
    feat007_enabled: bool | None = None
    feat007_stage: str | None = None
    sector_regime_state: str | None = None
    sector_rs_value: float | None = None
    sector_index_symbol: str | None = None
    sector_roc20: float | None = None
    benchmark_roc20: float | None = None
    feat007_score_adjustment: float | None = None
    feat007_pre_adjustment_score: float | None = None
    feat007_post_adjustment_score: float | None = None
    feat007_watch_downgrade_applied: bool | None = None
    feat007_abstained_reason: str | None = None
    feat007_explanation: str | None = None


class SectorOverlayResult(BaseModel):
    mapped_sector: str | None = None
    sector_close: float | None = None
    sector_ema20: float | None = None
    sector_roc20: float | None = None
    nifty50_roc20: float | None = None
    sector_rs_20: float | None = None
    sector_filter_status: str | None = None  # UNMAPPED, INSUFFICIENT_HISTORY, STRENGTH, WEAK
    feat007_abstained_reason: str | None = None
    downgrade_triggered: bool = False
    downgrade_reason: str | None = None
    original_action: str | None = None
    challenger_action: str | None = None


class MarketRegimeResult(BaseModel):
    market_state: str  # FAVORABLE, CAUTIOUS, HIGHRISK, DEFENSIVE
    trend_state: str   # BULLISH, BEARISH, UNKNOWN
    breadth_state: str # HEALTHY, MIXED, WEAK, UNKNOWN
    volatility_state: str # NORMAL, ELEVATED, HIGH, EXTREME, UNKNOWN
    data_quality_flags: dict[str, bool] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    new_entry_allowed: bool
    risk_multiplier: float
    manual_review_flag: bool


class StockAnalysisResult(BaseModel):
    symbol: str
    ohlcv: list[OHLCVPoint]
    technical: list[TechnicalAnalysisResult]
    news_articles: list[ArticleItem]
    news_summary: str
    news_sentiment_label: str
    news_sentiment_score: float
    fundamental: FundamentalAnalysisResult | None = None
    backtests: list[BacktestResult]
    recommendation: FinalRecommendation
    challenger_recommendation: FinalRecommendation | None = None
    sector_overlay: SectorOverlayResult | None = None
    market_regime: MarketRegimeResult | None = None
    disclaimer: str
    data_source: str = "unknown"
    data_quality: dict[str, str | int | bool | float] = Field(default_factory=dict)
    trade_readiness: str = "Review manually"
    confidence_breakdown: dict[str, float | str] = Field(default_factory=dict)
    # Overview/company metadata (optional)
    year52_high: float | None = None
    year52_low: float | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    corporate_events: dict | None = None
    social_sentiment_score: float | None = None


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
    ema_50: float = 0.0
    ema50_available: bool = False
    ema20_above_ema50: bool = False
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
    candles_fetched: int = 0
    conditions: dict[str, bool]
    matched: bool


class ScreenerStageSummary(BaseModel):
    stage_name: str
    source_universe_size: int
    unique_symbols_scanned: int
    duplicate_symbols_skipped: int
    matched_symbols: int
    shortlisted_symbols: int
    buy_candidate_symbols: list[str] = Field(default_factory=list)
    watch_candidate_symbols: list[str] = Field(default_factory=list)
    stopped_here: bool = False


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
    all_analyzed_stocks: list[ScreenerConditionResult] = Field(default_factory=list)
    analysis: FullAnalysisResponse | None = None
    disclaimer: str
    data_source: str = "unknown"
    data_warning: str | None = None
    scanned_at: str | None = None
    last_scan_completed_at: str | None = None
    market_context: dict[str, str | float | bool] = Field(default_factory=dict)
    scan_stages: list[ScreenerStageSummary] = Field(default_factory=list)
    stopped_at_stage: str | None = None
    duplicate_symbols_skipped: int = 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ShadowExecutionContext(BaseModel):
    """Immutable production snapshot for experimental evaluation (FR-007)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    candles: list[OHLCVPoint]
    technical_results: list[TechnicalAnalysisResult]
    sentiment_score: float
    fundamental_result: FundamentalAnalysisResult | None = None
    backtests: list[BacktestResult] = Field(default_factory=list)
    production_recommendation: FinalRecommendation
    production_challenger_recommendation: FinalRecommendation | None = None
    scan_date: datetime = Field(default_factory=_utc_now)


class ShadowExecutionResult(BaseModel):
    """Immutable shadow run output DTO."""

    model_config = ConfigDict(frozen=True)

    ruleset_name: str
    score: float
    action: str
    reasoning: list[str] = Field(default_factory=list)
    executed_at: datetime = Field(default_factory=_utc_now)


class ShadowComparisonLog(BaseModel):
    """Immutable production-vs-shadow comparison record (persistence later)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    scan_date: datetime
    ruleset_name: str
    production_action: str
    production_score: float
    shadow_action: str
    shadow_score: float
    score_delta: float
    is_mismatch: bool

