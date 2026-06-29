# Recommendation Engine: Performance

The Recommendation Engine is built to handle the entire NIFTY500 universe within seconds. This requires aggressive optimization.

## 1. Concurrency (I/O Bound)
- **`asyncio.gather`**: The `OrchestratorAgent` uses Python's asynchronous event loop to concurrently fetch data from external APIs.
- When 50 stocks are shortlisted, it fires off 50 concurrent requests to `BacktestAgent`, `NewsAnalysisAgent`, and `FundamentalAnalysisAgent`. This reduces network wait time from `O(N)` to `O(1)` (bound by the slowest single request).

## 2. Vectorization (CPU Bound)
- **Pandas DataFrames**: The `TechnicalAnalysisService` processes the entire universe simultaneously using `analyze_bulk_from_frame()`.
- Instead of looping through 500 stocks and calculating the 200-day moving average individually, it creates a single massive DataFrame with a MultiIndex `(timestamp, symbol)`.
- It uses `.groupby(level="symbol").transform(lambda x: ...)` to compute EMAs, RSIs, and MACDs in highly optimized C-backed routines.

## 3. Memory Management
- **Pre-allocation & Frames**: Previous iterations converted objects back and forth to dictionaries. The current version accepts a pre-built MultiIndex DataFrame, saving ~280 MB of redundant memory allocations.
- Memory audits (`get_rss_mb()`) are logged during the bulk technical pass to monitor leakage.

## 4. Caching
- **SQLite Local Cache**: Historical OHLCV data (which rarely changes during the day) is heavily cached in a local `candle_cache.db`. 
- Fetching 10 years of history for 500 stocks via the Fyers network API would take minutes and trip rate limits. Fetching from local SQLite takes milliseconds.

## 5. Scaling
- The engine is currently vertically scaled (single server, utilizing multiple CPU threads via `asyncio.to_thread` for heavy CPU blocking tasks).
- To scale horizontally, the system would need a distributed task queue (like Celery/Redis) where the `Orchestrator` fans out `StockAnalysisResult` generation to worker nodes.
