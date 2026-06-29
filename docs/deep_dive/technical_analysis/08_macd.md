# Technical Analysis: Moving Average Convergence Divergence (MACD)

## Business Purpose
MACD is a trend-following momentum indicator that shows the relationship between two moving averages of a security’s price. By subtracting the longer moving average (26-period EMA) from the shorter moving average (12-period EMA), MACD captures the immediate acceleration or deceleration of price. It is heavily utilized by institutional algorithms to detect momentum shifts before they are visible in pure price action.

## Formula
1. **MACD Line:** $EMA_{12} - EMA_{26}$
2. **Signal Line:** $EMA_9$ of the MACD Line
3. **MACD Histogram:** MACD Line - Signal Line

## Implementation in Repository
* **File:** `backend/app/services/technical_analysis_service.py`
* **Class:** `TechnicalAnalysisService`
* **Method:** `analyze_bulk_from_frame()`
* **Inputs:** Pandas DataFrame containing `close` prices.
* **Outputs:** `macd_series`, `macd_signal_series`

**Code:**
```python
def calc_macd(x):
    ema_12 = x.ewm(span=12, adjust=False).mean()
    ema_26 = x.ewm(span=26, adjust=False).mean()
    return ema_12 - ema_26

macd_series = grouped["close"].transform(calc_macd)
macd_signal_series = grouped["close"].transform(lambda x: calc_macd(x).ewm(span=9, adjust=False).mean())
```

## Worked Numerical Example
Assume the following calculated values for a stock closing at $150:
* $EMA_{12}$ = $148.50$
* $EMA_{26}$ = $145.00$

**Step 1:** Calculate MACD Line
MACD Line = 148.50 - 145.00 = **3.50**

**Step 2:** Calculate Signal Line
Assume the MACD Line over the past 9 days has been trending upward, and its 9-period EMA (Signal Line) calculates to **2.80**.

**Step 3:** Evaluate Momentum
Because the MACD Line (3.50) > Signal Line (2.80), momentum is currently accelerating upward. The Histogram value would be +0.70.

## Chart Interpretation & Signals

### Crossovers and Momentum
The relationship between the MACD Line and the Signal Line defines short-term momentum. 
* A **Bullish Crossover** occurs when the MACD Line crosses above the Signal Line. This indicates that short-term momentum is increasing faster than medium-term momentum.
* A **Bearish Crossover** occurs when the MACD Line drops below the Signal Line.

### Bullish Signals
The engine uses MACD as a core confirmation of momentum direction:
```python
macd_positive = bool(macd_value > macd_signal)
```
1. **Momentum Confirmation:** If `macd_value > macd_signal`, it is considered a bullish alignment. This condition awards 12 points to the technical score.
2. **Hard Filter:** MACD positivity is a mandatory component of the `core_momentum_filter_pass`. Without it, a buy signal cannot be generated.

### Bearish Signals
* If `macd_value < macd_signal`, momentum is decelerating. The engine strips the 12 points and triggers a failure in the `core_momentum_filter_pass`, downgrading any potential signal to `neutral` or `bearish`.

### Histogram Interpretation
While the engine does not explicitly output the Histogram value to the frontend, the condition `macd_value > macd_signal` is mathematically identical to stating "The MACD Histogram is > 0."

## Edge Cases
* **Zero Line Rejections:** Occasionally, a stock's MACD will drop exactly to the Signal Line and bounce (Zero Line Rejection). Because the logic uses strict greater-than (`>`), exactly equal values fail the check, protecting the system from ambiguous momentum states.
* **Warm-up Time:** MACD relies on an EMA 26, which in turn feeds an EMA 9. This stacked exponential smoothing means MACD is highly sensitive to the amount of historical data provided. The engine's strict 240-candle requirement guarantees MACD values match standard platforms.

## Production Usage
MACD acts as the ultimate tie-breaker for momentum. Even if price is above the moving averages (Trend=Bullish), if MACD is negative, the engine assumes the breakout lacks the institutional volume/momentum to sustain itself and blocks the trade.
