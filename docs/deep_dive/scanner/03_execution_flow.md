# Execution Flow

This document details the complete execution flow of the Scanner Engine, from initialization to the persistence of the final shortlisted stocks.

## Complete Execution Flow

### 1. Trigger
**Current Component**: `APScheduler` or Explicit API Call.
**Action**: The orchestrator is invoked (e.g., `run_screener` on `OrchestratorAgent`).
**Input**: `ScreenerRequest` (includes mode: swing/intraday, lookback window, optional custom symbols).
**Output**: Initiates the orchestration flow.

### 2. Universe Selection & Deduping
**Current Component**: `OrchestratorAgent`
**Next Component**: `ScreenerService`
**Purpose**: Determine which stocks to scan. It prioritizes universes (NIFTY500, NIFTY100, FNO) and removes duplicate symbols.
**Input**: Configured universe lists.
**Output**: A list of unique symbols (e.g., `['RELIANCE', 'TCS', ...]`).

### 3. Data Acquisition
**Current Component**: `ScreenerService` & `MarketDataService`
**Next Component**: `FyersService`
**Purpose**: Fetch required OHLCV (Open, High, Low, Close, Volume) data for all symbols.
**Action**: 
1. Checks DB cache continuity via `MarketDataService.validate_candle_continuity`.
2. Fetches missing incremental data from FYERS.
3. Upserts new candles to PostgreSQL.
4. Loads the full merged history into a Pandas DataFrame.
5. Fills missing gaps using Forward Fill (`ffill`).
**Time Spent**: Heavy I/O. Typically takes several seconds depending on the universe size and cache state.
**Input**: List of symbols.
**Output**: A combined, multi-indexed Pandas DataFrame containing clean historical data for all valid symbols.

### 4. Bulk Vectorized Technical Analysis
**Current Component**: `ScreenerService`
**Next Component**: `TechnicalAnalysisService`
**Purpose**: Compute technical indicators (EMA, SMA, RSI, MACD, Supertrend, etc.) across the entire universe simultaneously using Pandas.
**Action**: `analyze_bulk_from_frame` is called. It uses `groupby` and `transform` to calculate indicators in an extremely memory-efficient and fast manner.
**Time Spent**: Very fast (CPU bound). Fractions of a second for hundreds of stocks.
**Input**: Multi-indexed Pandas DataFrame.
**Output**: Dictionary mapping `symbol` -> `TechnicalAnalysisResult`.

### 5. Symbol Scoring & Shortlisting
**Current Component**: `ScreenerService`
**Next Component**: `OrchestratorAgent`
**Purpose**: Apply hard filters and compute a weighted score for each symbol.
**Action**: Loops sequentially through each symbol using only the trailing (last 30) candles. Checks data quality (`_passes_data_quality`), trend eligibility (`_passes_broad_trend`), and computes `_weighted_score`. Matches must pass broad eligibility and score >= 52.
**Input**: Precomputed indicators and raw OHLCV tail.
**Output**: List of `ScreenerConditionResult` objects. The top N (e.g., top 10) matched symbols become the **Shortlist**.

### 6. Deep Agent Analysis (On Shortlist Only)
**Current Component**: `OrchestratorAgent`
**Next Component**: Agent Cluster (`NewsAnalysisAgent`, `FundamentalAnalysisAgent`, `BacktestAgent`, `TechnicalAnalysisAgent`)
**Purpose**: Perform heavy, time-consuming analysis on the high-probability shortlist.
**Action**: 
1. Concurrently fires off the Backtest agent, News agent (fetches external news + sentiment), and Fundamental agent.
2. Passes all outputs to the `RecommendationAgent`.
**Time Spent**: Several seconds (Network I/O for News/Fundamental APIs, CPU for backtesting).
**Input**: Shortlisted symbols.
**Output**: Final recommendations (`BUY`, `WATCH`, `REJECT`).

### 7. Final Ranking & Persistence
**Current Component**: `RecommendationAgent` & `RankingAgent`
**Next Component**: `LatestScanService`
**Purpose**: Rank the candidates and save them to the database.
**Action**: `LatestScanService.persist_successful_scan` is called. It creates a `ScanSnapshot` and individual `ScanSnapshotRecord` rows.
**Input**: Complete `ScreenerResponse`.
**Output**: DB persistence. The execution completes and returns the final `ScreenerResponse`.
