# Recommendation Engine: Input Sources

The Recommendation Engine operates by ingesting diverse data sets from multiple internal agents and external APIs. This document details every input source, who produces it, and who consumes it.

## 1. Technical Analysis Output
- **Producer:** `TechnicalAnalysisAgent` (via `TechnicalAnalysisService`)
- **Consumer:** `RecommendationAgent`, `OrchestratorAgent` (Strict Gating)
- **Content:** `TechnicalAnalysisResult`
  - `score` (0-100): The raw technical score based on EMA, RSI, MACD, Volume, and Structure.
  - `signal`: "bullish", "bearish", or "neutral".
  - `mode`: `AnalysisMode.swing` or `AnalysisMode.intraday`.
  - `indicators`: Dictionary of calculated metrics (e.g., `close_above_ema20`).

## 2. Fundamental Analysis Output
- **Producer:** `FundamentalAnalysisAgent` (using `yfinance` API)
- **Consumer:** `RecommendationAgent`
- **Content:** `FundamentalAnalysisResult`
  - `fundamental_score` (-1.0 to 1.0): A normalized score based on financial health.
  - `revenue_growth_pct`, `profit_margin_pct`, `debt_to_equity`, `pe_ratio`.

## 3. News Sentiment Output
- **Producer:** `NewsAnalysisAgent` (fetches headlines) -> `LLMService.analyze_sentiment()` (AI evaluation).
- **Consumer:** `RecommendationAgent`
- **Content:**
  - `sentiment_score` (-1.0 to 1.0): Floating point representation of sentiment.
  - `sentiment_label`: String classification ("bullish", "bearish", "neutral").

## 4. Historical Backtesting Output
- **Producer:** `BacktestAgent` (via `BacktestService`)
- **Consumer:** `RecommendationAgent`, `OrchestratorAgent` (Strict Gating)
- **Content:** `BacktestResult`
  - `total_return`: Percentage return of the strategy over the lookback window.
  - `win_rate`: Percentage of profitable trades.
  - `verdict`: "favorable", "mixed", or "insufficient".
  - `trade_count`: Total number of trades taken in the backtest.

## 5. Market Data (OHLCV Candles)
- **Producer:** `FyersService` / `MarketDataFeed` (or SQLite `candle_cache.db`).
- **Consumer:** `TechnicalAnalysisService`, `BacktestService`, `RecommendationService` (for volume and ATR calculations).
- **Content:** `list[OHLCVPoint]` (Open, High, Low, Close, Volume, Timestamp).

## 6. AI/LLM Reasoning
- **Producer:** `LLMService` (using Groq OpenAI proxy).
- **Consumer:** `RecommendationService`
- **Content:** JSON dict containing:
  - `bullets`: 3 concise points on the setup.
  - `risk_factors`: 2 key risks.
  - `invalidation_signals`: 2 signals that invalidate the trade.
  - `summary`: Short advisory statement.

## 7. Configuration & Risk Settings
- **Producer:** Environment variables via `settings.py`.
- **Consumer:** `LLMService` (API Keys, Models), `OrchestratorAgent` (Scanner tuning).
