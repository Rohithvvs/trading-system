# Technical Analysis: Failure Scenarios

Despite robust vectorized logic, the Technical Analysis Engine can fail or produce degraded outputs. This document outlines potential failure scenarios, their symptoms, and the recovery process.

## 1. Incorrect Signals
* **Symptoms:** The system issues a `bullish` signal and initiates a trade on a stock that is clearly in a downtrend when viewed on a chart.
* **Root Cause:** Usually stems from corrupted or split-unadjusted data in the local database (`candle_cache.db`). If a 10-for-1 stock split occurs and the historical data is not adjusted, the engine sees a massive 90% "drop" in price, completely destroying all moving averages and MACD calculations for the next 200 days.
* **Recovery:** 
  1. Identify the symbol.
  2. Clear the specific symbol from `candle_cache.db`.
  3. Force a fresh pull from the upstream API (which usually provides split-adjusted history).
* **Prevention:** Rely on upstream data providers that guarantee split-adjusted continuous contracts.

## 2. Missing Signals
* **Symptoms:** A perfect setup occurs, but the engine outputs a `bearish` or `neutral` score, or rejects the symbol entirely.
* **Root Cause:** 
  1. **Strict Hard Filters:** A required condition missed by a fraction. For example, `volume = 49,999` (fails the 50k filter).
  2. **Insufficient History:** The symbol was newly added to the universe and doesn't have 240 days of history, causing `sma_200` to be `NaN` and failing the broad trend filter.
* **Recovery:** For insufficient history, the `MarketDataService` will attempt to backfill incrementally. If the stock literally hasn't existed for 240 days, it is mathematically impossible to calculate an SMA 200, and the system is working exactly as intended by ignoring it.

## 3. Calculation Errors (`NaN` or `inf` Propagation)
* **Symptoms:** The engine throws a traceback or outputs `NaN` for all scores.
* **Root Cause:** 
  1. Division by zero in custom indicators (e.g., RSI when average loss is 0, or VWAP when volume is 0).
  2. Attempting to run `.transform()` on an empty DataFrame.
* **Recovery:** The current implementation uses pandas functions that gracefully handle `inf` (converting to `NaN`) and explicitly checks for `pd.isna()` during the scoring loop, defaulting those values to `0.0`. If a new indicator is added without these protections, it must be patched to handle zero-division.

## 4. Performance Degradation (OOM Kills)
* **Symptoms:** The scanner run takes 5 minutes instead of 5 seconds, or the Docker container restarts silently (Out Of Memory kill).
* **Root Cause:**
  * **Memory Exhaustion:** Converting thousands of `OHLCVPoint` Pydantic objects into lists and then into a massive DataFrame creates a huge memory footprint. 
  * **Python Loop Overhead:** If vectorized Pandas logic is accidentally replaced with a standard `for` loop over the DataFrame, CPU usage spikes 100x.
* **Recovery:** The codebase currently uses `TechnicalAnalysisService.analyze_bulk_from_frame` to ingest a pre-built MultiIndex DataFrame, saving ~280MB of redundant memory allocation. Ensure all future indicator additions use `.transform()`.
* **Telemetry:** Check the `MEMORY_AUDIT` logs. If `rss_mb` spikes from 150MB to 1.5GB during `after_indicator_calculations`, a memory leak or inefficient allocation has been introduced.

## 5. Production Incidents (The "Empty Universe" Bug)
* **Symptoms:** The scanner runs, but returns 0 matched symbols every single time.
* **Root Cause:** 
  1. The upstream API token expired (`FyersAuthExpiredError`), causing the `MarketDataService` to return empty sets for every symbol.
  2. The `candles_fetched` log shows `0`.
* **Recovery:** 
  1. Rotate or refresh the API authentication token.
  2. Manually trigger a scanner run to verify data flows.
  3. The Technical Analysis Engine itself does not need restarting; it is purely reactive to the data it is fed.

## General Recovery Philosophy
The Technical Analysis Engine is designed to be **stateless**. If it enters a failure mode, you never need to "restart the engine." You simply need to correct the data it is receiving. Fixing the database cache or API connection will immediately resolve 99% of engine-related bugs on the very next run.
