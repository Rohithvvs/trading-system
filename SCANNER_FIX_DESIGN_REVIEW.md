# Scanner Fix Design Review

## Executive Summary
This design review evaluates three proposed methodologies to resolve the `NaN` propagation bug caused by timeline misalignment during `pandas.unstack()` operations in `TechnicalAnalysisService.analyze_bulk`.

---

## Option A: Forward Fill (`.ffill()`) before `rolling()`
This approach attempts to resolve `NaN` sequences by forward-filling the last known price before computing rolling averages and differences.

* **Mathematical Correctness**: Low. It fundamentally breaks the temporal definition of "N-periods" for any symbol with missing days.
* **Trading-Signal Integrity**: Compromised. Indicators will deviate from industry-standard charting platforms.
* **SMA Correctness**: Distorted. If a symbol was unlisted for 10 days out of the last 50, those 10 days are padded with the last known price. A 50-day SMA would effectively become a 40-day SMA.
* **RSI Correctness**: Distorted. A synthetic day with no price change (`diff == 0.0`) is registered as 0 gain and 0 loss. Due to the exponential moving average (EWM) nature of RSI, this artificial "flat" day mathematically drags the RSI closer to 50, dampening momentum signals.
* **Performance Impact**: Extremely fast (native matrix operations).
* **Memory Impact**: High, as a full dense matrix is allocated.
* **Scalability to 755 symbols**: Highly scalable in terms of execution speed.
* **Production Risk**: **HIGH**. 
* **Synthetic Price Risk Assessment**: **YES, `.ffill()` creates synthetic price history.** It forces the engine to assume an asset traded at an unchanged price on days it did not actually trade. This triggers artificial decay in oscillators and shortens the true lookback window of moving averages, leading to potentially false BUY/WATCH recommendations based on artificially smoothed data.

---

## Option B: GroupBy Symbol Indicator Calculations
This approach abandons the dense matrix `unstack()` methodology entirely, instead grouping the flat DataFrame by symbol and applying rolling operations within isolated symbol bounds.

* **Mathematical Correctness**: 100% accurate.
* **Trading-Signal Integrity**: Perfectly preserved. Output strictly matches individual single-symbol execution.
* **SMA Correctness**: 100% correct. A 50-day window maps exactly to 50 actual trading days for that specific symbol.
* **RSI Correctness**: 100% correct. Momentum is tracked across true trading periods.
* **Performance Impact**: Slightly slower than pure 2D array vectorization, but Pandas `groupby().transform()` or `groupby().rolling()` is implemented in highly optimized C-extensions. For 188,750 rows (755 symbols × 250 candles), execution will easily complete in < 0.25 seconds.
* **Memory Impact**: Minimal. Avoids the memory overhead of a dense unstacked matrix padded with NaNs.
* **Scalability to 755 symbols**: Excellent.
* **Production Risk**: **LOWEST**. Safest production implementation.

---

## Option C: Hybrid Batched Vectorization
This approach attempts to process symbols in smaller batches (e.g., 50 at a time) using unstacking.

* **Mathematical Correctness**: Variable/Flawed.
* **Trading-Signal Integrity**: Compromised.
* **SMA/RSI Correctness**: If *any* symbol in the batch has a timeline deviation, the whole batch gets `NaN`-injected or synthetically padded. 
* **Performance Impact**: Medium. Overhead from batch management negates vectorization benefits.
* **Memory Impact**: Medium.
* **Scalability to 755 symbols**: Fair.
* **Production Risk**: **HIGH**. It retains the exact same mathematical vulnerability as the current implementation, just localized to smaller blast radii.

---

## Recommendation & Verdict

**Option B (`groupby(symbol)`)** is the only implementation that provides cryptographic-level mathematical safety for trading signal generation. Option A introduces severe synthetic data artifacts that violate the physical meaning of N-day technical indicators. Option C fails to solve the root problem.

### Final verdict:
**APPROVED_FOR_IMPLEMENTATION**  
(Proceed exclusively with Option B: `groupby(symbol)` calculations to preserve mathematical integrity).
