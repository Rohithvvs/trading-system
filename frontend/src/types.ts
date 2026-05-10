export type AnalysisMode = "intraday" | "swing" | "both";

export type ThemeMode = "dark" | "light";

export type DetailTab = "overview" | "technicals" | "trade-plan" | "news" | "backtest" | "chart";

export type SignalFilter = "ALL" | "BUY" | "WATCH" | "REJECT";

export type SortKey = "rank" | "score" | "confidence" | "riskReward";

export type TimeframeConfig = {
  intraday: string;
  swing: string;
  lookback_window: number;
};

export type OHLCVPoint = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type TechnicalAnalysisResult = {
  mode: AnalysisMode;
  signal: string;
  score: number;
  indicators: Record<string, string | number | boolean>;
  summary: string;
};

export type ArticleItem = {
  title: string;
  description: string;
  source: string;
  url: string;
  published_at: string;
  sentiment_score: number;
};

export type BacktestEquityPoint = {
  label: string;
  equity: number;
};

export type BacktestResult = {
  mode: AnalysisMode;
  strategy_name: string;
  total_return: number;
  cagr: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  trade_count: number;
  verdict: string;
  equity_curve: BacktestEquityPoint[];
  // Extended
  trades?: { entry_date: string; exit_date: string; entry_price: number; exit_price: number; pnl_percent: number }[];
  monthly_returns?: { month: string; return: number }[];
  sharpe_ratio?: number;
  best_trade?: { entry_date: string; exit_date: string; entry_price: number; exit_price: number; pnl_percent: number } | null;
  worst_trade?: { entry_date: string; exit_date: string; entry_price: number; exit_price: number; pnl_percent: number } | null;
};

export type RecommendationReasoning = {
  bullets: string[];
  risk_factors: string[];
  invalidation_signals: string[];
};

export type TradePlan = {
  mode: AnalysisMode;
  strategy_name: string;
  setup_type: string;
  timeframe: string;
  bias: string;
  entry_low: number;
  entry_high: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
  target_3?: number | null;
  risk_reward_ratio: number;
  notes: string;
  partial_exit?: string | null;
  suggested_holding_days?: number | null;
  trailing_stop_atr_multiplier?: number | null;
};

export type FinalRecommendation = {
  action: string;
  confidence: number;
  score: number;
  reasoning: RecommendationReasoning;
  trade_plans: TradePlan[];
  summary: string;
};

export type StockAnalysisResult = {
  symbol: string;
  ohlcv: OHLCVPoint[];
  technical: TechnicalAnalysisResult[];
  news_articles: ArticleItem[];
  news_summary: string;
  news_sentiment_label: string;
  news_sentiment_score: number;
  backtests: BacktestResult[];
  recommendation: FinalRecommendation;
  disclaimer: string;
  data_source?: string;
  data_quality?: Record<string, string | number | boolean>;
  trade_readiness?: string;
  confidence_breakdown?: Record<string, string | number>;
  year52_high?: number | null;
  year52_low?: number | null;
  sector?: string | null;
  industry?: string | null;
  market_cap?: number | null;
  corporate_events?: Record<string, string> | null;
  social_sentiment_score?: number | null;
};

export type RankingItem = {
  rank: number;
  symbol: string;
  overall_score: number;
  recommendation: string;
  best_for_mode?: string | null;
};

export type RankingsResponse = {
  rankings: RankingItem[];
  buy_rankings: RankingItem[];
  watch_rankings: RankingItem[];
  best_intraday_candidate?: string | null;
  best_swing_candidate?: string | null;
  disclaimer: string;
};

export type FullAnalysisResponse = {
  items: StockAnalysisResult[];
  rankings: RankingsResponse;
  disclaimer: string;
  generated_at: string;
};

export type ScreenerConditionResult = {
  symbol: string;
  close: number;
  ema_20: number;
  sma_30: number;
  sma_50: number;
  sma_100: number;
  sma_200: number;
  macd: number;
  macd_signal: number;
  supertrend: number;
  volume: number;
  previous_volume: number;
  screener_score: number;
  technical_signal: string;
  technical_score: number;
  conditions: Record<string, boolean>;
  matched: boolean;
};

export type ScreenerStageSummary = {
  stage_name: string;
  source_universe_size: number;
  unique_symbols_scanned: number;
  duplicate_symbols_skipped: number;
  matched_symbols: number;
  shortlisted_symbols: number;
  buy_candidate_symbols: string[];
  watch_candidate_symbols: string[];
  stopped_here: boolean;
};

export type ScreenerResponse = {
  scanned_symbols: number;
  screener_name: string;
  data_valid_symbols: string[];
  eligible_symbols: string[];
  shortlisted_symbols: string[];
  buy_candidate_symbols: string[];
  watch_candidate_symbols: string[];
  matched_symbols: string[];
  matches: ScreenerConditionResult[];
  all_analyzed_stocks?: ScreenerConditionResult[];
  analysis?: FullAnalysisResponse | null;
  disclaimer: string;
  data_source?: string;
  data_warning?: string | null;
  market_context?: Record<string, string | number | boolean>;
  scan_stages?: ScreenerStageSummary[];
  stopped_at_stage?: string | null;
  duplicate_symbols_skipped?: number;
};

export type CandidateRow = {
  rank: number | null;
  symbol: string;
  signal: "BUY" | "WATCH" | "REJECT";
  score: number;
  confidence: number | null;
  entryLow: number | null;
  entryHigh: number | null;
  stopLoss: number | null;
  target1: number | null;
  target2: number | null;
  riskReward: number | null;
  trend: string;
  momentum: string;
  volume: string;
  newsSentiment: string;
  lastUpdated: string | null;
  tradeReadiness: string;
  recommendationSummary: string;
  analysisItem?: StockAnalysisResult;
  screenerMatch?: ScreenerConditionResult;
};

export type DashboardFilters = {
  signal: SignalFilter;
  search: string;
  scoreRange: [number, number];
  sortBy: SortKey;
  onlyHighConfidence: boolean;
};

export type MainAppView = "home" | "scanner" | "paper-trading";

export type ScanHistoryItem = {
  id: string;
  generated_at: string;
  screener_name: string;
  scanned_symbols: number;
  shortlisted_count: number;
  buy_symbols: string[];
  watch_symbols: string[];
  data_source?: string;
  data_warning?: string | null;
};

export type PaperAccountSummary = {
  account_id: number;
  account_name: string;
  base_currency: string;
  starting_balance: number;
  balance: number;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_invested: number;
  reserved_cash: number;
  available_cash: number;
  open_positions_count: number;
  open_orders_count: number;
  max_risk_per_trade: number;
  updated_at: string;
};

export type PaperPosition = {
  id: number;
  symbol: string;
  qty: number;
  avg_entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
  invested_value: number;
  stop_loss?: number | null;
  target?: number | null;
  risk_reward_ratio?: number | null;
  source_signal?: string | null;
  source_score?: number | null;
  source_confidence?: number | null;
  created_at: string;
  updated_at: string;
};

export type PaperOrder = {
  id: number;
  symbol: string;
  side: "BUY" | "SELL";
  type: "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT" | "GTT";
  product_type?: "MIS" | "CNC" | "NRML";
  qty: number;
  price?: number | null;
  stop_price?: number | null;
  stop_loss?: number | null;
  target?: number | null;
  status: "PENDING" | "FILLED" | "CANCELLED" | "REJECTED";
  notes?: string | null;
  source_signal?: string | null;
  source_score?: number | null;
  source_confidence?: number | null;
  created_at: string;
  filled_at?: string | null;
  filled_price?: number | null;
};

export type PaperTradeHistoryItem = {
  id: number;
  symbol: string;
  qty: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  pnl_percent: number;
  notes?: string | null;
  source_signal?: string | null;
  source_score?: number | null;
  source_confidence?: number | null;
  opened_at: string;
  closed_at: string;
  holding_period_hours: number;
  exit_reason?: string | null;
};

export type TransactionItem = {
  id: string;
  timestamp: string;
  symbol?: string | null;
  action: string;
  amount: number;
  balance_after?: number | null;
  qty?: number | null;
  price?: number | null;
};

export type TransactionPageResponse = {
  items: TransactionItem[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
};

export type NotificationItem = {
  id: number;
  message: string;
  level: "info" | "success" | "error";
  is_read: boolean;
  created_at: string;
};

export type AlertItem = {
  id: number;
  symbol: string;
  condition: ">=" | "<=";
  target_price: number;
  status: string;
  created_at: string;
  triggered_at?: string | null;
  triggered_price?: number | null;
};

export type DailyPnlPoint = {
  date: string;
  pnl: number;
};

export type HoldingPeriodRow = {
  symbol: string;
  avg_holding_minutes: number;
  total_trades: number;
  win_rate_pct: number;
};

export type AnalyticsResponse = {
  total_trades: number;
  win_rate_pct: number;
  profit_factor?: number | null;
  average_profit?: number | null;
  average_loss?: number | null;
  best_trade_symbol?: string | null;
  best_trade_amount?: number | null;
  worst_trade_symbol?: string | null;
  worst_trade_amount?: number | null;
  daily_pnl: DailyPnlPoint[];
  cumulative_pnl: DailyPnlPoint[];
  wins: number;
  losses: number;
  holding_periods: HoldingPeriodRow[];
};

export type PaperWorkspaceSnapshot = {
  symbol: string;
  current_price: number;
  candles: OHLCVPoint[];
  ema_20?: number | null;
  supertrend?: number | null;
  source_signal?: string | null;
  source_score?: number | null;
  source_confidence?: number | null;
};

export type TechnicalExtras = {
  atr?: number | null;
  atr_pct?: number | null;
  atr_class?: "low" | "medium" | "high" | string | null;
  bollinger_status?: string | null;
  multi_timeframe?: { daily?: string | null; weekly?: string | null } | null;
};

export type BacktestExtras = {
  total_return?: number;
  cagr?: number;
  max_drawdown?: number;
  win_rate?: number;
  profit_factor?: number;
  trade_count?: number;
  equity_curve?: BacktestEquityPoint[];
  monthly_returns?: { month: string; return: number }[];
  sharpe_ratio?: number;
  best_trade?: { entry_date: string; exit_date: string; entry_price: number; exit_price: number; pnl_percent: number } | null;
  worst_trade?: { entry_date: string; exit_date: string; entry_price: number; exit_price: number; pnl_percent: number } | null;
};

export type SymbolDetail = {
  symbol: string;
  year52_high?: number | null;
  year52_low?: number | null;
  sector?: string | null;
  industry?: string | null;
  market_cap?: number | null;
  technical_extras?: TechnicalExtras | null;
  backtest_extras?: BacktestExtras | null;
  news_extras?: { corporate_events?: Record<string, unknown> | null; social_sentiment?: number | null } | null;
  ohlcv?: OHLCVPoint[] | null;
};

export type PaperQuoteResponse = {
  symbol: string;
  current_price: number;
  source: "FYERS_QUOTE" | "CANDLE_FALLBACK";
  updated_at: string;
};

export type PaperTradingDashboardResponse = {
  account: PaperAccountSummary;
  positions: PaperPosition[];
  open_orders: PaperOrder[];
  order_history: PaperOrder[];
  trades: PaperTradeHistoryItem[];
  symbols: string[];
  selected_workspace?: PaperWorkspaceSnapshot | null;
};

export type PaperOrderTicketState = {
  symbol: string;
  side: "BUY" | "SELL";
  type: "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT" | "GTT";
  productType?: "MIS" | "CNC" | "NRML";
  qty: number;
  limitPrice?: number | null;
  stopPrice?: number | null;
  stopLoss?: number | null;
  target?: number | null;
  notes?: string;
  sourceSignal?: string | null;
  sourceScore?: number | null;
  sourceConfidence?: number | null;
};

export type RecommendationPrefillRequest = {
  symbol: string;
  suggested_entry?: number | null;
  suggested_stop?: number | null;
  suggested_targets: number[];
  recommendation_meta: Record<string, string | number>;
};

export type RecommendationPrefillResponse = {
  symbol: string;
  side: "BUY";
  type: "LIMIT";
  qty: number;
  limit_price?: number | null;
  stop_loss?: number | null;
  target?: number | null;
  note: string;
};

export type PaperOrderActionResponse = {
  account: PaperAccountSummary;
  order?: PaperOrder | null;
  position?: PaperPosition | null;
  trade?: PaperTradeHistoryItem | null;
  message: string;
};
