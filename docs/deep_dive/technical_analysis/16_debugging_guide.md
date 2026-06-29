# Technical Analysis: Debugging Guide

When the Technical Analysis Engine behaves incorrectly (e.g., rejecting a perfect setup or approving a terrible one), follow this deterministic debugging workflow.

## The Debugging Workflow

### Step 1: Check the Scanner Logs
The engine logs its exact decision matrix for every symbol. 
* **Target Log:** `backend/app/logs/scanner.log` (or `console` if running interactively).
* **Search for:** The specific symbol ticker (e.g., `grep "symbol=NSE:HDFCBANK-EQ" scanner.log`).
* **Look for this line:**
  `TECHNICAL | Swing decision | symbol=... | signal=bearish | score=45.0 | hard_filters_pass=False | failed_hard_filters=core_momentum_filter_pass ...`
* **Interpretation:** This line tells you *exactly* why it failed. If `failed_hard_filters=basic_liquidity_filter_pass`, the problem is volume, not the moving averages. 

### Step 2: Enable Determinism Debugging
If the log line doesn't provide enough detail on the raw indicator values, enable the determinism debug mode to dump the full JSON payload.
* **Action:** Set environment variable `SCANNER_DETERMINISM_DEBUG=1`.
* **Output:** The engine will log a massive JSON object labeled `SCANNER_DETERMINISM` containing the exact `screener_score`, `data_origin`, and calculated indicators.

### Step 3: Verify the Database Cache
If the indicators look mathematically wrong (e.g., SMA 200 is 0.0), the data feeding the engine is corrupted.
* **Target DB:** `backend/app/services/candle_cache.db` (SQLite).
* **Target Table:** `daily_candles` (or equivalent table schema defined in `candle_store.py`).
* **Query:** 
  ```sql
  SELECT COUNT(*) FROM daily_candles WHERE symbol = 'NSE:HDFCBANK-EQ';
  ```
* **Interpretation:** If the count is < 240, the engine physically cannot calculate the required long-term indicators. Force a backfill or check why the Fyers API is failing to return history.

### Step 4: Verify the Upstream API Logs
If the cache is empty, the API must be failing.
* **Target Log:** `backend/app/fyersRequests.log` and `backend/app/fyersApi.log`.
* **Interpretation:** Look for `FyersRateLimitError` or `FyersAuthExpiredError`. If the token is dead, no data flows, and the engine evaluates nothing.

### Step 5: Inspect the Core Code
If the data is perfect but the calculation is still wrong, inspect the engine logic.
* **Target File:** `backend/app/services/technical_analysis_service.py`
* **Target Method (Math):** `analyze_bulk_from_frame()`
  * *Check the `lambda` transforms. Was `adjust=False` removed from an `ewm` call?*
* **Target Method (Scoring):** The scoring loop inside `analyze_bulk_from_frame()` where points are assigned.
  * *Check the conditional logic. Did a recent PR accidentally change a `>` to a `<`?*
* **Target File (Final Filtering):** `backend/app/services/screener_service.py`
  * *Target Method:* `_weighted_score()` and `_passes_broad_trend()`. The engine might have scored it 90, but the screener killed it because `sma_50 < sma_200`.

## Summary Checklist
1. `scanner.log` (Why did it fail?)
2. `candle_cache.db` (Is the data there?)
3. `fyersRequests.log` (Is the API working?)
4. `technical_analysis_service.py` (Is the math right?)
