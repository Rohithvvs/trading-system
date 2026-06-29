# Recommendation Engine: Complete Execution Flow

Every recommendation in the system is generated through a highly orchestrated, multi-stage pipeline. Here is the step-by-step breakdown from market data arrival to the final UI output.

## Step 1: Triggering the Flow
The pipeline usually starts via a scheduled scan or user request to the `OrchestratorAgent.run_screener()` or `run_full()`.

## Step 2: Universe Selection & Scanning (The Funnel)
1. **Universe Load:** `OrchestratorAgent` loads the target universe (e.g., NIFTY500) via `UniverseService`.
2. **Screening:** `ScreenerService` pulls OHLCV data and filters out stocks with bad data quality or invalid broad trends.
3. **Shortlisting:** `OrchestratorAgent` takes the top `N` matched symbols based on the screener score.

## Step 3: Concurrent Data Fetching
To maximize speed, `OrchestratorAgent.run_full()` asynchronously pre-fetches all required OHLCV data for all shortlisted symbols using `FyersService.fetch_ohlcv()`. 

## Step 4: Technical Analysis
1. **Bulk Processing:** The pre-fetched OHLCV data is passed into `TechnicalAnalysisAgent.run_bulk()`.
2. **Vectorization:** `TechnicalAnalysisService.analyze_bulk_from_frame()` converts the data into a Pandas DataFrame and calculates indicators (EMA, SMA, MACD, RSI, VWAP) in a single vectorized pass.
3. **Technical Scoring:** It outputs a `TechnicalAnalysisResult` with a `score` (0-100) and a `signal` (bullish/bearish/neutral).

## Step 5: Concurrent Micro-Agent Analysis
For each shortlisted symbol, the `OrchestratorAgent` fires off the remaining agents concurrently:
- **`BacktestAgent`**: Runs historical simulations (`BacktestService`) for the specific setup (e.g., SMA + RSI + MACD), returning a `BacktestResult` (CAGR, Win Rate, Verdict).
- **`NewsAnalysisAgent`**: Fetches headlines and calls `LLMService.analyze_sentiment()` to get a sentiment score (-1.0 to 1.0).
- **`FundamentalAnalysisAgent`**: Fetches data from `yfinance` to score revenue growth, margins, D/E, and PE ratio.

## Step 6: Synthesis (`RecommendationAgent`)
The `OrchestratorAgent` aggregates all these results and passes them to `RecommendationAgent.run()`.
1. **AI Reasoning Generation:** `RecommendationAgent` packs the scores and signals into a prompt context and calls `LLMService.build_reasoning()`. The LLM (Groq) generates human-readable bullets, risk factors, and invalidation signals.
2. **Service Delegation:** It then delegates to `RecommendationService.build()`.

## Step 7: Scoring & Weighting (`RecommendationService`)
1. **Weight Calculation:** `RecommendationService.calculate_dynamic_weights()` determines how much weight to give Technicals vs Fundamentals vs News vs Backtesting based on current volume and news catalysts.
2. **Final Score Calculation:** The raw component scores are normalized to 100, multiplied by their dynamic weights, and summed to a final `score` (0-100).
3. **Label Assignment:** 
   - `BUY`: Score >= 72
   - `WATCH`: Score >= 55
   - `REJECT`: Score < 55
4. **Trade Plan Generation:** `_build_trade_plans()` calculates Entry, Stop Loss, and Targets based on recent average true range (ATR/ranges).

## Step 8: Strict Buy Gating (`OrchestratorAgent`)
The `FinalRecommendation` is returned to `OrchestratorAgent`, which applies a critical safety check (`_enforce_strict_buy_gate`). 
If a stock was marked `BUY`, but it lacks strong live data (e.g. mocked data), strong technicals (score < 75), or a minimum Risk-Reward ratio (>= 1.25), the `OrchestratorAgent` forcefully **downgrades** it to `WATCH`.

## Step 9: Database Persistence
The final `StockAnalysisResult` is saved to PostgreSQL:
- `AnalysisHistory` records the final score, recommendation, and AI reasoning.
- `BacktestHistory` records the backtest performance.

## Step 10: Ranking & Output
`RankingAgent` sorts all processed `StockAnalysisResult` items descending by final score. The final JSON payload is sent to the Frontend, displaying the categorized recommendations.
