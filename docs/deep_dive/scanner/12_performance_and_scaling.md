# Performance and Scaling

Scanning hundreds of stocks mathematically requires specific architectural choices to prevent memory exhaustion and CPU bottlenecks.

## 1. Bulk Vectorization (The Core Innovation)
Originally, scanners often loop through symbols sequentially:
```python
for symbol in symbols:
    candles = fetch(symbol)
    indicators = calculate_indicators(candles)
```
This is slow and requires converting database rows to Python objects (Pydantic models) back and forth.

**The Solution**: `TechnicalAnalysisService.analyze_bulk_from_frame`.
- Data is loaded directly from PostgreSQL into a single large Pandas DataFrame with a `MultiIndex` of `(timestamp, symbol)`.
- Indicators are calculated simultaneously for all symbols using Pandas `.groupby(level="symbol").transform()`.
- **Result**: CPU usage is optimized. Math that took minutes now takes milliseconds.

## 2. Memory Usage Optimization
- **Data Structures**: The system intentionally avoids creating lists of `OHLCVPoint` Pydantic models for the entire dataset (which consumes ~280MB for 500 stocks). Instead, it keeps data in raw Pandas DataFrames.
- **Garbage Collection**: Intermediate DataFrames (like `frame_parts`) are explicitly deleted (`del frame_parts`) to free memory immediately after concatenation.
- **Memory Audits**: `get_rss_mb()` logs resident set size memory throughout the execution to monitor for leaks.

## 3. Caching and I/O Scaling
- **Database Cache**: `MarketDataService` stores historical candles in Postgres.
- **Incremental Fetching**: The scanner never asks FYERS for 1 year of data if it already has it. It queries `get_latest_candle_time()` and only fetches the missing delta.
- **Asyncio**: Data fetching uses `asyncio.gather` with a semaphore (`asyncio.Semaphore(3)`) to limit concurrent network requests to the FYERS API, preventing HTTP 429 Rate Limit errors while maintaining high throughput.

## 4. Concurrency Model
- **AnyIO Thread Limiter**: Configured in `main.py` lifespan: `limiter.total_tokens = 100`. This allows the asynchronous event loop to offload synchronous tasks (like heavy Pandas CPU operations or sync DB calls) to a deep thread pool without blocking the main API thread.
- **Agent Concurrency**: In `OrchestratorAgent`, downstream agents (News, Fundamental, Backtest) are launched concurrently using `asyncio.gather(asyncio.to_thread(...))`.

## 5. Potential Bottlenecks
- **Agent Cluster**: The LLM calls in `RecommendationAgent` are the slowest part of the pipeline. This is mitigated by drastically reducing the number of candidates passed to it (The Funnel model). Only the top N (e.g., 10) stocks are analyzed deeply.
- **Database Connection Pool**: If `asyncio.gather` is configured with a high semaphore limit during database cache checks, it could exhaust the Postgres connection pool.
