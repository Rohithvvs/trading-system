# Technical Analysis: Dependencies and Ecosystem

The Technical Analysis Engine (`TechnicalAnalysisService`) does not operate in isolation. It relies on a complex upstream pipeline for accurate data and serves as a pure computational engine for downstream consumers.

## Upstream Dependencies (Inputs)

### 1. Market Data Pipeline (`MarketDataService` & `FyersService`)
* **Role:** The engine calculates indicators based entirely on the OHLCV data it receives. If this data is missing, split-adjusted incorrectly, or delayed, every calculation (SMA, MACD, RSI) will be mathematically wrong.
* **Interaction:** The data pipeline is responsible for fetching, standardizing, and forward-filling (`ffill`) missing candles on non-trading days to ensure the Pandas DataFrames passed to the engine have a continuous, unbroken datetime index.

### 2. External APIs (Fyers / yfinance)
* **Role:** The ultimate source of truth for market data.
* **Interaction:** `FyersService` connects via websocket or REST to the broker. If Fyers is down or rate-limited, the system falls back to Yahoo Finance (`yfinance`). The Technical Engine is completely agnostic to the source; it simply requires a Pandas DataFrame.

### 3. Database (`candle_cache.db` / `candle_store.py`)
* **Role:** Calculating a 200-day moving average requires 240 days of history. Fetching 240 days of history for 500 stocks over a live API every minute would trigger severe rate limits.
* **Interaction:** The DB caches historical OHLCV data locally. The Scanner reads the bulk of the required history directly from the DB, minimizing API calls to just the most recent delta.

### 4. Scanner (`ScreenerService`)
* **Role:** Orchestration and Memory Management.
* **Interaction:** The `ScreenerService` is the direct caller of `TechnicalAnalysisService.analyze_bulk_from_frame()`. It handles the massive memory allocation required to build a 500-symbol MultiIndex Pandas DataFrame and feeds it to the engine, preventing the engine from having to manage API I/O or database connections.

---

## Downstream Dependencies (Consumers)

The Technical Analysis Engine is a pure mathematical function. It returns a dictionary of `TechnicalAnalysisResult` objects.

### 1. The Scanner (`ScreenerService`)
* **Role:** The primary consumer.
* **Interaction:** Uses the technical score to calculate a final weighted `screener_score`. If the engine emits a `bearish` signal, the Scanner immediately rejects the symbol. 

### 2. The Trading Engine / Live State Machine
* **Role:** Execution of trades.
* **Interaction:** While the current codebase structure heavily leverages the Screener as an intermediary, any live trading bot (e.g., `market_engine_service.py` or `live_state_machine.py`) relies on the Technical Engine's deterministic signals to decide exactly when to trigger a bracket order (target/stop-loss).

### 3. Analytics and Observability
* **Role:** Monitoring system health and backtesting.
* **Interaction:** The engine calls `_log_analysis_decision` which emits structured logs (including all indicator values and failure reasons). These logs are consumed by the observability layer (`scanner_logger`) to generate metrics like `forced_rebuilds`, `invalid_symbols`, and pass/fail ratios for dashboarding.

---

## Technical Infrastructure Dependencies

### 1. Redis
* **Usage in Engine:** The `TechnicalAnalysisService` itself is completely stateless and memory-bound. It does **not** interact directly with Redis. 
* **Usage in Pipeline:** Redis is used upstream by caching layers and rate-limiters (e.g., Fyers token management) to coordinate distributed execution, ensuring the engine isn't starved of data.

### 2. Configuration (`config` module)
* **Usage:** While the engine hardcodes standard indicator periods (e.g., EMA 20, SMA 50), broader system timeouts, retry limits, and API keys required to feed the engine are driven by the central configuration environment variables (`.env`).

### 3. Compute Resources (CPU/RAM)
* **Usage:** Because the engine relies on Pandas `groupby.transform`, it is highly CPU and Memory intensive. Scanning 500 symbols across 250 days of history creates a massive matrix. The engine depends on adequate system RAM (monitored via `get_rss_mb()`) to prevent `MemoryError` exceptions during bulk frame concatenation.
