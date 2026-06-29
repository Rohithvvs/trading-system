# Technical Analysis: Exponential Moving Average (EMA)

## Business Purpose
The Exponential Moving Average (EMA) is designed to track price trends while applying more weight to recent price data compared to older data. In trading, the most recent price action is often the most relevant indicator of immediate market psychology. By reacting faster to price changes than a Simple Moving Average (SMA), the EMA allows the system to identify trend shifts earlier, enabling more precise entries (buying the dip) and exits (cutting losses quickly).

## Formula
$EMA_{today} = (Value_{today} \times \alpha) + (EMA_{yesterday} \times (1 - \alpha))$

Where:
* $Value_{today}$ is the current closing price.
* $\alpha$ (smoothing factor) = $\frac{2}{N + 1}$
* $N$ is the number of periods (e.g., 20 or 50).

## Implementation in Repository
* **File:** `backend/app/services/technical_analysis_service.py`
* **Class:** `TechnicalAnalysisService`
* **Method:** `analyze_bulk_from_frame()`
* **Inputs:** Pandas DataFrame containing `close` prices.
* **Outputs:** EMA values for 9 (intraday only), 20, and 50 periods.

**Code:**
```python
# Swing Mode Implementation
ema_20_series = grouped["close"].transform(lambda x: x.ewm(span=20, adjust=False).mean())
ema_50_series = grouped["close"].transform(lambda x: x.ewm(span=50, adjust=False, min_periods=50).mean())
```
*Note: `adjust=False` is critical. It forces Pandas to use the recursive formula exactly as defined above, matching the output of standard financial charts like TradingView.*

## Worked Numerical Example (EMA 20)
Assume a 20-period EMA.
$\alpha = \frac{2}{20 + 1} = 0.0952$

Let's assume the $EMA_{yesterday}$ was 100.00, and today's closing price is 105.00.
$EMA_{today} = (105.00 \times 0.0952) + (100.00 \times (1 - 0.0952))$
$EMA_{today} = 9.996 + 90.48$
$EMA_{today} = 100.476$

Because of the smoothing factor, a $5 jump in price only pulled the EMA up by ~$0.48, smoothing out the noise while still reacting.

## Chart Interpretation & Signals

### Bullish Signals
The engine interprets the EMA bullishly under two specific conditions:
1. **Price above EMA 20:** (`close_above_ema20 = bool(lc > ema_20)`). This indicates short-term momentum is in the buyer's control. (Awards 18 points).
2. **EMA 20 above EMA 50:** (`ema20_above_ema50 = bool(ema50_available and ema_20 > ema_50)`). This is a "Golden Cross" equivalent for EMAs, indicating the short-term trend is rising faster than the medium-term trend. (Awards 12 points).

### Bearish Signals
* Price closing below the EMA 20 indicates immediate weakness and often invalidates a short-term bullish setup.
* EMA 20 crossing below the EMA 50 indicates a shifting trend structure toward the downside.

### False Signals (Whipsaws)
In a sideways or ranging market, price will frequently cross above and below the EMA 20 without a true trend emerging. This generates false signals. The engine mitigates this by requiring confirmation from other indicators (like MACD, Supertrend, and Volume) before issuing a final bullish signal.

## Edge Cases
* **Insufficient Data (EMA 50):** The system enforces `min_periods=50` for the EMA 50. If a newly listed stock has only 40 days of history, `ema_50` evaluates to `NaN`. The code handles this via the `ema50_available` boolean, ensuring the system doesn't crash but simply withholds the points for the EMA 20 > EMA 50 condition.
* **Warm-up Period:** The recursive nature of EMA means the first calculation depends on a simple average. It takes time for the math to "settle." The engine requires at least 240 candles of history to ensure the EMA 50 is perfectly accurate by the time it reaches the current day.

## Production Usage
The EMA is a "core trend filter." In swing mode, closing above the EMA 20 is heavily weighted (18 points). 

## Debugging Approach
If the EMA values in the engine do not match TradingView:
1. **Check the DataFrame tail:** Ensure the `close` prices exactly match the charting platform.
2. **Check history length:** If the engine fetched exactly 50 candles, the EMA 50 will be wildly inaccurate compared to TradingView (which uses thousands of historical candles). The engine requires 240+ candles for stability.
3. **Verify `adjust=False`:** If this is accidentally changed to `True` in the code, the math will diverge significantly from standard financial models.
