# Cache Interactions

## 1. Redis Usage
- **Direct Usage**: The Backtesting Engine (`BacktestService` and `BacktestAgent`) **does not use Redis directly**. There are no cache keys, TTLs, or invalidations within the backtest logic.
- **Why?**: The backtest requires raw historical data and outputs a specific summary. Caching the *input* (OHLCV) is done by PostgreSQL. Caching the *output* is handled by inserting rows into `backtest_history` in PostgreSQL.

## 2. Upstream Caching (PostgreSQL)
- The Backtester heavily relies on the `MarketDataService` which acts as a cache for the FYERS API. 
- If `MarketDataService` encounters a cache hit in the `daily_candles` table, it skips the network request.
- The `OrchestratorAgent` passes this cached data down to the `BacktestAgent`.

## 3. In-Memory State
- The `BacktestService` stores intermediate cache states inside the `frame` (Pandas DataFrame).
- Calculations like `EMAIndicator` are calculated once per run and held in memory (`frame["ema_fast"]`). 
- When the `run()` method finishes and returns the `BacktestResult`, the DataFrame is garbage collected. No state persists in memory between runs.
