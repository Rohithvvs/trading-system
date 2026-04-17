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
  analysis?: FullAnalysisResponse | null;
  disclaimer: string;
  data_source?: string;
  data_warning?: string | null;
  market_context?: Record<string, string | number | boolean>;
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
  sector: string;
};

export type MainAppView = "scanner" | "paper-trading";

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
  type: "MARKET" | "LIMIT" | "STOP";
  qty: number;
  price?: number | null;
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
  type: "MARKET" | "LIMIT" | "STOP";
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
