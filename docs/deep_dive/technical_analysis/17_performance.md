# Technical Analysis: Performance & Scalability

The Technical Analysis Engine is designed to process the entire NSE universe (500+ symbols), over 250+ days of history, calculating dozens of indicators, and generating signals—all within a few seconds. Achieving this requires strict adherence to vectorized operations and careful memory management.

## 1. Vectorization (Pandas GroupBy)
The most significant optimization in the engine is the elimination of Python `for` loops during mathematical calculations. 
* **Bad Approach:** Looping through 500 symbols, and for each symbol, looping through 250 candles to calculate an SMA. This incurs massive Python interpreter overhead.
* **Engine Implementation:** The engine leverages Pandas `groupby(level="symbol")` combined with `.transform()`. This pushes the heavy matrix multiplication down to the C/Cython level, allowing the CPU to execute SIMD (Single Instruction, Multiple Data) operations across the entire dataset simultaneously.
```python
# Calculates SMA 50 for all 500 symbols across all 250 days in a few milliseconds.
sma_50_series = grouped["close"].transform(lambda x: x.rolling(window=50).mean())
```

## 2. Batch Processing & Data Structures
Historically, creating thousands of Pydantic `OHLCVPoint` objects and passing them around caused severe memory bloat.
* **Optimization:** The `ScreenerService` now bypasses intermediate object creation. It loads historical data directly from the SQLite database into Pandas DataFrames. It concatenates these frames into a single, unified `MultiIndex` DataFrame (indexed by timestamp and symbol).
* **Result:** `TechnicalAnalysisService.analyze_bulk_from_frame()` receives this single continuous block of memory, eliminating ~280MB of redundant overhead.

## 3. Memory Usage (RAM)
* **Telemetry:** The engine actively monitors its own memory footprint using `get_rss_mb()` (Resident Set Size).
* **Expected Profile:** Memory spikes significantly during the `concat` and `transform` phases, often jumping by 100-200MB as intermediate frames (like `df_indicators`) are built. 
* **Garbage Collection:** The engine aggressively deletes intermediate structures once the tail calculations are finished (`del combined_frame`, `del symbol_frames`) to return memory to the OS and prevent OOM (Out Of Memory) kills in constrained Docker environments.

## 4. CPU Usage
Because Pandas transforms are synchronous and heavily optimized, they will peg a single CPU core to 100% for a fraction of a second. The engine isolates this intensive workload from the asynchronous I/O layer.

## 5. Async Execution (I/O vs Math)
The architecture clearly separates Async I/O from Synchronous CPU math.
* **I/O Bound:** `ScreenerService` uses `asyncio.gather` and `ThreadPoolExecutor` to fetch missing Fyers data and query SQLite concurrently. It waits for network requests without blocking the event loop.
* **CPU Bound:** Once the DataFrame is built, it is passed to `TechnicalAnalysisService`, which executes synchronously. Because the Pandas vectorization is so fast (usually < 100ms for the entire universe), there is no need to offload it to a separate ProcessPool, which would incur serialization (Pickle) overhead.

## 6. Indicator Optimization
Not all indicators are easily vectorized. 
* **Supertrend:** Because Supertrend is path-dependent (the upper band's position depends on whether the trend flipped on the *previous* candle), it cannot be solved with a simple `rolling()` or `ewm()` function. 
* **Optimization:** The engine vectorizes the *components* of Supertrend (True Range and ATR), and only runs the slow, sequential `for` loop on the final band-flipping logic, minimizing the non-vectorized penalty.

## 7. Scalability
* **Current Scale:** 500 symbols, 250 candles = 125,000 data points. Easily processed in < 1 second.
* **Future Scale:** If the universe expands to 5,000 symbols (e.g., US Markets), the MultiIndex DataFrame approach will scale linearly in memory. If memory becomes a constraint (e.g., > 2GB RAM required), the `ScreenerService` can simply chunk the universe into batches of 1,000 symbols and feed them to the `analyze_bulk_from_frame` sequentially, trading a slight increase in execution time for strict memory bounds.
