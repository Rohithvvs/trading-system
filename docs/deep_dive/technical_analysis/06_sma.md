# Technical Analysis: Simple Moving Average (SMA)

## Business Purpose
The Simple Moving Average (SMA) smooths out price data by creating a constantly updated average price over a specific number of periods. Unlike the EMA, it treats all data points in the window equally. The SMA is the institutional standard for determining broad market trends. The 50-day and 200-day SMAs, in particular, are watched globally by mutual funds and hedge funds to dictate macro capital allocation.

## Formula
$SMA = \frac{P_1 + P_2 + \dots + P_N}{N}$

Where:
* $P$ is the closing price.
* $N$ is the number of periods.

## Implementation in Repository
* **File:** `backend/app/services/technical_analysis_service.py`
* **Class:** `TechnicalAnalysisService`
* **Method:** `analyze_bulk_from_frame()`
* **Inputs:** Pandas DataFrame containing `close` prices.
* **Outputs:** SMA values for 20, 30, 50, 100, and 200 periods.

**Code:**
```python
# Swing Mode Implementation
sma_20_series = grouped["close"].transform(lambda x: x.rolling(window=20).mean())
sma_30_series = grouped["close"].transform(lambda x: x.rolling(window=30).mean())
sma_50_series = grouped["close"].transform(lambda x: x.rolling(window=50).mean())
sma_100_series = grouped["close"].transform(lambda x: x.rolling(window=100).mean())
sma_200_series = grouped["close"].transform(lambda x: x.rolling(window=200).mean())

# Lookback for slope detection
sma_20_prev_df = sma_20_series.groupby(level="symbol").nth(-20)
```

## Worked Numerical Example (SMA 5)
Assume a 5-period SMA for simplicity, with closing prices: 10, 11, 12, 13, 14.
$SMA_5 = \frac{10 + 11 + 12 + 13 + 14}{5} = \frac{60}{5} = 12$

If the next day's price is 15, the oldest price (10) drops off:
$SMA_5 = \frac{11 + 12 + 13 + 14 + 15}{5} = \frac{65}{5} = 13$

## Chart Interpretation & Signals

### Bullish Signals
The engine uses SMAs to determine macro structure and intermediate trends:
1. **Higher Timeframe Trend:**
   ```python
   higher_timeframe_trend = "uptrend" if lc > sma_50 and sma_20 > sma_50 else "sideways" if lc > sma_50 else "downtrend"
   ```
   An "uptrend" awards 10 points. Price must be above the 50-day average, AND the 20-day average must be above the 50-day.
2. **SMA 20 Slope (Uptrend):**
   ```python
   sma_uptrend_20d = bool(sma_20 > sma_20_prev)
   ```
   The engine compares the current SMA 20 to the SMA 20 from 20 days ago. If it is higher, the moving average is sloping upwards (awards 8 points).
3. **Broad Scanner Eligibility (in `screener_service.py`):**
   ```python
   latest_close > sma_50 and sma_50 > sma_200
   ```
   This is the ultimate gatekeeper. The stock must be in a confirmed long-term uptrend to even be considered.

### Bearish Signals
* If `lc < sma_50`, the stock is classified as being in a "downtrend" and receives 0 structure points.
* A negative sloping SMA 20 implies stalling or negative intermediate momentum.

### False Signals
Because the SMA weights old data equally with new data, a massive price spike 19 days ago will still artificially inflate a 20-day SMA today, even if the stock has been dropping for a week. When that data point drops off on day 21, the SMA will drop sharply. This "drop-off effect" can create visual false signals on charts.

## Edge Cases
* **Missing History:** If a symbol has only 150 days of trading history, `sma_200` will be `NaN`. Consequently, the `sma_50 > sma_200` filter in the screener will evaluate to `False`, rejecting newly listed IPOs from the scan entirely.
* **Lookback Indexing:** The `sma_20_prev_df = sma_20_series.groupby(level="symbol").nth(-20)` specifically requires at least 20 periods to exist. The code guards against errors by checking `symbol in sma_20_prev_df.index`.

## Production Usage
SMAs are used primarily for the **Broad Trend Eligibility** gate in the Screener, ensuring the engine only buys stocks that are already structurally bullish. The technical engine uses it to add confirmation points (slope and stacking).

## Debugging Approach
If a symbol is mysteriously rejected despite looking good:
1. Check the logs for `SKIP broad_trend_failed`.
2. Look at the `sma50` and `sma200` values printed in that log line.
3. If `sma200` is 0.0, the system didn't fetch enough history from the cache (minimum 240 candles required). Verify `candle_cache.db` continuity.
