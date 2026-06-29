# Technical Analysis: Learning Notes for Developers

Welcome to the Technical Analysis Engine. If you are a new engineer joining the team, this document is designed to accelerate your onboarding.

## Most Important Concepts
1. **The Engine is a Pure Function:** The `TechnicalAnalysisService` takes a DataFrame and returns a dictionary of signals. It does not hit APIs. It does not query databases. If you give it the exact same DataFrame, it will always output the exact same score. 
2. **Hard Filters vs. Soft Scoring:** A stock needs to pass the hard filters (e.g., `volume > 50k`, `MACD > Signal`) before any points matter. A score of 95 is meaningless if `core_momentum_filter_pass` is False; the stock will be rejected.
3. **Vectorization is Mandatory:** We process hundreds of symbols with hundreds of data points each. If you write a `for` loop that iterates row-by-row over a DataFrame to calculate an indicator, the system will lag. Use `groupby().transform()` and Pandas native `ewm()` / `rolling()`.

## Common Misconceptions
* **"Why isn't the system buying this stock? The RSI is 30, it's cheap!"**
  * *Correction:* This is a momentum breakout system, not a mean-reversion system. We don't buy dips. An RSI of 30 means the stock is dying. We want RSI > 55.
* **"The API returned 14 candles, so RSI 14 should calculate fine."**
  * *Correction:* RSI uses an exponential smoothing average. The 14th candle's calculation depends on the 13th, which depends on the 12th. To get mathematical accuracy that matches TradingView, you need at least 200+ warmup candles.
* **"We should cache the EMA 200 in the database to save time."**
  * *Correction:* Caching indicators makes parameter tuning a nightmare. We cache the *raw price data* (OHLCV). Pandas calculates the EMA 200 in 15 milliseconds in-memory. Don't touch the DB schema to add indicators.

## Architecture Decisions
* **MultiIndex DataFrames:** We used to use Pydantic `OHLCVPoint` lists. This caused massive memory bloat (OOM errors) because Python objects are heavy. We migrated to a single `MultiIndex` DataFrame. This decision saved ~280MB of RAM per scan run and drastically sped up execution.
* **Separation of Screener and TA Engine:** The Screener handles the "messy" real world (API limits, missing data, forward-filling gaps). The TA Engine handles the pure math. Do not pollute the TA Engine with API calls.
* **Deterministic Logging:** Financial algorithms are notoriously hard to debug. The `_log_analysis_decision` method explicitly prints exactly which filters failed. This was an architectural decision to prioritize observability over log brevity.

## Suggested Learning Order
1. **`app.schemas.technical_analysis`:** Learn the data contracts (`OHLCVPoint`, `TechnicalAnalysisResult`).
2. **`04_indicator_pipeline.md` (Docs):** Understand how Pandas `groupby` works conceptually.
3. **`backend/app/services/technical_analysis_service.py`:** Read `analyze_bulk_from_frame()`. Trace how the `df_indicators` dataframe is built.
4. **`backend/app/services/screener_service.py`:** Read `screen_symbols_swing()`. See how the data is fetched from the DB, filled, and passed to the TA Engine.
5. **`16_debugging_guide.md` (Docs):** Learn how to trace a failed signal through the logs.

## Interview Questions (To test your understanding)
1. **Q:** What is the difference between `analyze_bulk` and `analyze_bulk_from_frame`?
   * **A:** `analyze_bulk` uses standard loops and objects (legacy). `analyze_bulk_from_frame` uses a pre-built MultiIndex Pandas DataFrame, drastically reducing memory allocations.
2. **Q:** Why do we use `adjust=False` in the Pandas `ewm()` function?
   * **A:** It forces Pandas to use the strict recursive formulation of the exponential moving average, which is necessary to match the output of standard charting platforms like TradingView.
3. **Q:** A stock has a technical score of 85, but the system logs `signal = bearish`. How is this possible?
   * **A:** One of the three hard filters (`core_trend`, `core_momentum`, `basic_liquidity`) failed. The score is irrelevant if a hard filter is violated.
4. **Q:** How does the system handle a holiday where no trading occurred?
   * **A:** The `ScreenerService` reindexes the DataFrame against a continuous business-day calendar and uses `.ffill()` (forward fill) to copy the previous day's data into the holiday, ensuring moving averages don't break due to missing index dates.
