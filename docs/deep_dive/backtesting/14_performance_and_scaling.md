# Performance and Scaling

The Backtesting Engine executes mathematical simulations over large datasets. Performance and memory optimization are critical to ensure it doesn't bottleneck the broader orchestrator flow.

## 1. Large Datasets & Memory Usage
- **The Problem**: A single year of daily OHLCV data is ~250 candles. For a 10-stock shortlist, that's 2,500 rows. If intraday (5-min candles), it becomes 100,000+ rows. Loading this naïvely in Python dictionaries consumes massive RAM.
- **The Solution**: The `BacktestService` immediately converts the `list[OHLCVPoint]` into a Pandas `DataFrame`. DataFrames are backed by C-arrays (NumPy), making them extremely memory efficient.
- **Memory Example**: 100,000 rows in a native Python list of Pydantic models might consume 50MB. In a Pandas DataFrame, it consumes ~3-5MB.

## 2. CPU Optimization (Vectorization vs. Iteration)
- **Vectorized Indicators**: 
  Instead of looping to calculate EMA and RSI, the engine uses the `ta` library:
  `frame["ema_fast"] = EMAIndicator(close=frame["close"], window=fast_window).ema_indicator()`
  This pushes the math down to C-level NumPy arrays, computing indicators for the entire history in milliseconds.
- **Iterative Trade Simulation**: 
  While indicators are vectorized, the actual trade state-machine (Entry, Hold, Exit) uses `frame.iterrows()`. This is inherently slower than vectorization. However, since the Backtest Engine only runs on the *shortlisted* top 10 candidates (not the full 500-stock universe), the `iterrows()` loop over 250 candles takes < 0.05 seconds per stock. This is a deliberate and acceptable trade-off for code readability and complex state management.

## 3. Parallel Execution & Async Processing
- **Caller Concurrency**: The `BacktestService.run()` method is purely synchronous (CPU-bound). It contains no `await` statements.
- **How it Scales**: To prevent blocking the main asyncio event loop, `OrchestratorAgent` offloads the backtest execution to a separate thread:
  ```python
  asyncio.to_thread(run_backtest)
  ```
- **Batch Processing**: Furthermore, the Orchestrator runs the Backtest, News, and Fundamental agents concurrently for *all* shortlisted symbols using `asyncio.gather()`. 
  If 10 stocks are shortlisted, 10 backtest threads are spun up simultaneously.

## 4. Scaling
- **Vertical Scaling**: The engine scales perfectly with CPU cores since it uses `to_thread`. More cores = more symbols can be backtested concurrently.
- **Limits**: The primary limit is the `AnyIO` thread limit (configured in FastAPI lifespan). If you increase the shortlist size from 10 to 100, you will queue threads and latency will increase linearly.
