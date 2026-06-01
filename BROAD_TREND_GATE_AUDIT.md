# Broad Trend Gate Audit

## Overview
This audit evaluates the failure of the "Broad Trend Gate" to pass any candidates out of 700 valid symbols during a recent scanner execution.

**Input Count**: 700 valid symbols  
**Output Count**: 0 symbols matched  

---

## Rule Execution Breakdown

The audit traced the exact evaluation of every sub-rule inside the Broad Trend Gate. The pass/fail counts out of 700 symbols are as follows:

- **Rule 1: Close > SMA50**
  - **Pass**: 0
  - **Fail**: 700

- **Rule 2: SMA50 > SMA200**
  - **Pass**: 0
  - **Fail**: 700

- **Rule 3: RSI >= 50**
  - **Pass**: 0
  - **Fail**: 700

- **Rule 4: Close > EMA20**
  - **Pass**: 170
  - **Fail**: 530

- **Rule 5: Supertrend Positive**
  - **Pass**: 196
  - **Fail**: 504

- **Rule 6: MACD > Signal**
  - **Pass**: 345
  - **Fail**: 355

- **Rule 7: Volume > 50k & Price 100-500k**
  - **Pass**: 291
  - **Fail**: 409

- **Rule 8: Technical Score >= 48**
  - **Pass**: 96
  - **Fail**: 604

---

## Diagnostics & Identification

**1. Which rule eliminates the most symbols?**  
`Close > SMA50`, `SMA50 > SMA200`, and `RSI >= 50` are eliminating 100% of the universe (700 out of 700 fail).

**2. Whether threshold is realistic?**  
The thresholds themselves (e.g. price above 50-day average) are realistic standard practices in trend following.

**3. Whether threshold changed recently?**  
The thresholds have remained the same.

**4. Whether bug exists in indicator calculation?**  
**YES. A critical vectorization bug exists in `TechnicalAnalysisService.analyze_bulk`.**  
When multiple symbols are analyzed concurrently, their histories are unstacked into a unified Pandas DataFrame (`close_unstack = frame["close"].unstack(level="symbol")`). If *any* symbol is missing data on a particular trading day (due to being a newer listing, a trading halt, etc.), Pandas aligns the index and fills those gaps with `NaN`s for other symbols. 
Since `pandas.rolling(window=50).mean()` strictly requires consecutive non-NaN values, the presence of these `NaN` gaps forces the rolling `SMA50` and `SMA200` to evaluate to `NaN` for all 700 symbols. 
When the rules evaluate `latest_close > NaN` or `NaN > NaN`, they evaluate to `False` across the board, completely breaking the screener. The same `NaN` propagation breaks RSI calculations.

**5. Whether market conditions alone explain result?**  
No. While market conditions might be weak, it is mathematically impossible for exactly 0 symbols out of 700 to have `Close > SMA50` purely by chance. The indicator calculation bug guarantees that 0 symbols will ever pass.

---

## Final Conclusion
**TREND_GATE_REGRESSION_DETECTED**
