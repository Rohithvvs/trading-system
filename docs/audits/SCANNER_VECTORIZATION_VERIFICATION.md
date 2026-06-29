# Scanner Vectorization Verification

## Objective
Verify the hypothesis that `TechnicalAnalysisService.analyze_bulk` is producing `NaN`-contaminated `SMA50`, `SMA200`, and distorted `RSI` values due to DataFrame unstacking alignment over the whole universe.

## Verification Data
The following data compares individual, strictly-isolated symbol calculations against the vectorized `analyze_bulk()` execution over the full `NIFTY 500` dataset containing 710 valid symbols. 

### 1. RELIANCE-EQ
* **Latest Close**: `1321.2`
* **Individual SMA50**: `1381.35`  |  **Bulk SMA50**: `NaN`
* **Individual SMA200**: `1393.78` |  **Bulk SMA200**: `NaN`
* **Individual RSI**: `30.38`      |  **Bulk RSI**: `37.87` (Distorted)

### 2. INFY-EQ
* **Latest Close**: `1160.9`
* **Individual SMA50**: `1213.40`  |  **Bulk SMA50**: `NaN`
* **Individual SMA200**: `1422.95` |  **Bulk SMA200**: `NaN`
* **Individual RSI**: `44.80`      |  **Bulk RSI**: `52.51` (Distorted)

### 3. TCS-EQ
* **Latest Close**: `2258.9`
* **Individual SMA50**: `2352.60`  |  **Bulk SMA50**: `NaN`
* **Individual SMA200**: `2644.16` |  **Bulk SMA200**: `NaN`
* **Individual RSI**: `27.80`      |  **Bulk RSI**: `29.09` (Distorted)

### 4. SBIN-EQ
* **Latest Close**: `964.4`
* **Individual SMA50**: `1030.29`  |  **Bulk SMA50**: `NaN`
* **Individual SMA200**: `994.13`  |  **Bulk SMA200**: `NaN`
* **Individual RSI**: `37.26`      |  **Bulk RSI**: `NaN`

### 5. HDFCBANK-EQ
* **Latest Close**: `744.55`
* **Individual SMA50**: `778.93`   |  **Bulk SMA50**: `NaN`
* **Individual SMA200**: `898.69`  |  **Bulk SMA200**: `NaN`
* **Individual RSI**: `37.81`      |  **Bulk RSI**: `92.68` (Highly Distorted)

---

## Diagnostics

**1. Is NaN introduced during unstack()?**
**YES.** Across the full universe, symbols have slightly different historical timelines (due to listing dates, data provider halts, or missing days). `pandas.unstack(level="symbol")` aligns all symbols onto a common `DatetimeIndex`. This introduced **331 `NaN` values** into `RELIANCE-EQ`'s unstacked `close` series alone (out of 863 total index rows).

**2. Is NaN introduced during rolling()?**
**YES.** `pandas.rolling(window=50).mean()` strictly requires 50 *consecutive* non-NaN values. Because the unstacked `close` series contains randomly distributed `NaN` values injected by misaligned timelines, the `.rolling()` function is unable to find a clean 50-row window and therefore cascades `NaN` throughout the entire output series.

**3. Is NaN introduced during merge/alignment?**
**YES.** As proven above, the merge/alignment across 700+ symbols is the fundamental root cause.

**4. Is NaN introduced during scoring?**
**NO.** The `NaN` values are mathematically present in the indicators *before* scoring occurs. The scoring rules simply evaluate `latest_close > NaN`, which Python/Pandas correctly evaluates to `False`. This erroneously eliminates 100% of symbols during the Broad Trend Gate.

---

## Final Conclusion
**ROOT_CAUSE_CONFIRMED**
