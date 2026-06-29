# Technical Analysis: Edge Cases

The Technical Analysis Engine processes vast amounts of numerical data. Edge cases in financial data can easily cause divide-by-zero errors, NaN propagation, or false signals. 

---

### 1. Missing Candles (Gaps in Data)
* **What happened:** The API failed to return data for a specific Tuesday, resulting in a gap between Monday and Wednesday.
* **Expected behavior:** The moving averages should bridge the gap without crashing or severely distorting the trend line.
* **Actual implementation:** The `ScreenerService` utilizes Pandas `ffill()` (forward fill) to bridge calendar gaps. `df = df.reindex(full_index)` and `df = df.ffill()` carry the previous day's close forward.
* **Recovery:** The engine proceeds calculation seamlessly, treating the missing day as a 0% price movement day.
* **Developer debugging steps:** Check `candle_cache.db`. If a symbol looks distorted, query the SQLite database to see if `ffill` created a massive flatline of identical candles over a 2-week period.

### 2. Insufficient History (Indicator Warm-up Period)
* **What happened:** A newly listed IPO only has 40 days of trading history. 
* **Expected behavior:** The system should gracefully calculate short-term indicators (EMA 20) but omit long-term ones (SMA 200).
* **Actual implementation:** The engine enforces a minimum warmup via `get_required_candle_count()`. Pandas `rolling(window=200)` will return `NaN` for the first 199 rows. The engine checks `pd.isna(sma_200)` and defaults the value to `0.0`.
* **Recovery:** If `sma_200` is 0.0, the Screener's `sma_50 > sma_200` check evaluates to False, gracefully rejecting the symbol without a stack trace.
* **Developer debugging steps:** Check the `candles_fetched` field in the log. If it's less than 240, the engine lacks history.

### 3. Missing Volume
* **What happened:** An index or a highly illiquid stock returns `0` for volume across multiple days.
* **Expected behavior:** The system should reject the stock as untradable and prevent VWAP divide-by-zero errors.
* **Actual implementation:** `_passes_data_quality` explicitly checks: `if sum(1 for candle in recent if candle.volume > 0) < 25: return False`. For VWAP, if the rolling volume sum is 0, pandas handles the `0/0` division by returning `NaN`.
* **Recovery:** Symbol is rejected (`data_quality_failed`).
* **Developer debugging steps:** Look for `data_quality_failed` in `scanner_logger`.

### 4. Sideways Market
* **What happened:** A stock bounces between $100 and $105 for 3 months.
* **Expected behavior:** The system should remain neutral and not trigger false breakouts.
* **Actual implementation:** Moving averages flatten, causing EMA 20 and EMA 50 to crisscross repeatedly (whipsaw). The system mitigates this by requiring `macd_positive`, `rsi_in_buy_zone`, and `volume_lift`. In a true sideways market, volume is dead, preventing the setup from hitting the 72-point `bullish` threshold.
* **Recovery:** Wait for volatility to return.
* **Developer debugging steps:** Inspect the `screener_score`. Sideways markets usually result in scores between 40-55.

### 5. Gap Up / Gap Down
* **What happened:** Earnings report causes the stock to open 15% higher than yesterday's close.
* **Expected behavior:** Indicators should reflect the sudden jump without breaking.
* **Actual implementation:** True Range calculation `max(high-low, abs(high-prev_close), abs(low-prev_close))` accurately captures the gap size. RSI jumps violently.
* **Recovery:** The engine correctly models the volatility. However, if RSI spikes > 68, the system denies the "Buy Zone" points, acting as a natural speed bump to prevent buying an over-extended gap.
* **Developer debugging steps:** Check ATR and RSI values in the `indicators` dictionary output.

### 6. Market Crash / Extreme Volatility
* **What happened:** A black swan event causes a 20% intraday drop.
* **Expected behavior:** The system should immediately flip bearish and protect capital.
* **Actual implementation:** The `close_above_ema20` check fails. `supertrend` flips negative instantly due to the massive ATR expansion.
* **Recovery:** `hard_filters_pass` becomes False. Signal becomes `bearish`.
* **Developer debugging steps:** Check `supertrend_positive` boolean in logs.

### 7. Holiday Sessions
* **What happened:** A special 1-hour trading session on a holiday weekend.
* **Expected behavior:** The system should process it as a normal day, though volume will be extremely low.
* **Actual implementation:** Processed normally.
* **Recovery:** The `basic_liquidity_filter_pass` may fail if the abbreviated session volume doesn't cross the 50,000 threshold, rejecting trades for that day.
* **Developer debugging steps:** Check volume metrics on the specific date.

### 8. Duplicate Data
* **What happened:** API returns two candles for the exact same timestamp.
* **Expected behavior:** System must deduplicate to prevent mathematical errors in rolling windows.
* **Actual implementation:** When `ScreenerService` loads the DataFrame, it groups/reindexes by the unique `timestamp`, effectively squashing duplicates.
* **Recovery:** Data is cleaned before reaching `TechnicalAnalysisService`.
* **Developer debugging steps:** Check `MarketDataService.upsert_candles` logic for unique constraints.

### 9. Incorrect Timestamps / Timezone Mismatch
* **What happened:** API returns naive UTC while the DB expects timezone-aware IST.
* **Expected behavior:** Timestamps must align perfectly or the `ffill` logic will create thousands of blank days.
* **Actual implementation:** The data ingestion layer aggressively strips timezones: `if dt.tzinfo is not None: dt = dt.replace(tzinfo=None)`.
* **Recovery:** All data in the engine operates in a naive, timezone-agnostic state, preventing mismatch errors.
* **Developer debugging steps:** Check if `len(combined_frame)` is absurdly large (e.g., millions of rows for 500 stocks), indicating a timezone alignment bug inflating the `ffill` date range.

### 10. Invalid OHLC Values
* **What happened:** API glitch returns a negative price or High < Low.
* **Expected behavior:** Block the symbol entirely.
* **Actual implementation:** `_passes_data_quality` checks: `if any(candle.close <= 0 or candle.high <= 0 or candle.low <= 0 for candle in recent): return False`.
* **Recovery:** Rejects the symbol (`data_quality_failed=True`).
* **Developer debugging steps:** Find the specific symbol in the DB and inspect the raw values for negatives or zeros.
