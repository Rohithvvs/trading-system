# Technical Analysis: Relative Strength Index (RSI)

## Business Purpose
The Relative Strength Index (RSI) is a momentum oscillator that measures the speed and change of price movements. It bounds its output between 0 and 100. In trading, it is used to identify internal strength—when a stock is advancing, is the buying pressure accelerating (high RSI) or fading (diverging RSI)? It helps traders avoid buying at the extreme top of a move or shorting at the extreme bottom.

## Formula
$RSI = 100 - \frac{100}{1 + RS}$

Where:
* $RS$ (Relative Strength) = $\frac{\text{Average Gain}}{\text{Average Loss}}$
* Gains and Losses are typically smoothed using an Exponential Moving Average (EMA) or Wilder's Smoothing over a 14-period lookback.

## Implementation in Repository
* **File:** `backend/app/services/technical_analysis_service.py`
* **Class:** `TechnicalAnalysisService`
* **Method:** `analyze_bulk_from_frame()`
* **Inputs:** Pandas DataFrame containing `close` prices.
* **Outputs:** `rsi_14_series`

**Code:**
```python
def calc_rsi(x):
    delta = x.diff()
    gain = delta.where(delta > 0, 0.0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    return 100.0 - (100.0 / (1.0 + rs))

rsi_14_series = grouped["close"].transform(calc_rsi)
```

## Worked Numerical Example
Assume the following price changes over 14 periods result in:
* Average Gain (smoothed) = 1.50
* Average Loss (smoothed) = 0.50

$RS = \frac{1.50}{0.50} = 3.0$
$RSI = 100 - \frac{100}{1 + 3.0} = 100 - \frac{100}{4.0} = 100 - 25 = 75$

An RSI of 75 indicates strong upside momentum, as the average gains are 3 times larger than the average losses.

## Chart Interpretation & Signals

### Bullish Signals
The engine looks for RSI to be structurally supportive but not overextended.
1. **Supportive Base:** (`rsi_supportive = bool(rsi_14 >= 50)`). An RSI above 50 indicates that, on average, buyers are in control over the 14-period window. This is a mandatory component of the `core_momentum_filter_pass`. (Awards 8 points).
2. **The "Buy Zone":** (`rsi_in_buy_zone = bool(55 <= rsi_14 <= 68)`). This is the optimal window for momentum breakouts. Above 55 shows clear strength, but below 68 leaves room for the stock to run before becoming dangerously overbought. (Awards 6 points).

### Bearish Signals / Overbought / Oversold
* **Overbought (RSI > 70):** Traditional TA considers > 70 overbought. The engine penalizes entries here by withholding the 6 "Buy Zone" points, acting as a natural speed bump against chasing vertical parabolic moves.
* **Oversold (RSI < 30):** The engine is designed as a trend-following breakout system, *not* a mean-reversion dip-buying system. Therefore, an oversold RSI is treated as a bearish lack of momentum (`rsi_supportive` evaluates to `False`, failing hard filters) rather than a buy signal.

## Common Mistakes
1. **Shorting because RSI is > 70:** In a strong bull market, RSI can stay overbought for weeks. The engine avoids this mistake; it simply stops initiating *new* buys when RSI > 68, rather than trying to short.
2. **Calculating RSI on too little data:** Because Wilder's smoothing uses an EMA equivalent (`alpha=1/14`), calculating RSI on exactly 14 candles yields inaccurate results. The engine requires 240 warmup candles, ensuring mathematical perfection.

## Real Trading Examples
* **Example 1 (Optimal Entry):** Stock breaks out of a 3-week base. The close is above EMA 20, and RSI rises from 48 to 61. The engine scores this highly, as momentum is confirmed but not exhausted.
* **Example 2 (Exhaustion):** Stock has gone up 5 days in a row. RSI hits 78. The Scanner might pick it up based on broad trend, but the Technical Analysis Engine denies the `rsi_in_buy_zone` points, and it likely fails to reach the 72-point threshold for a hard buy, preventing the user from buying the top.

## Edge Cases
* **Division by Zero:** If a stock goes up for 14 straight days, the Average Loss will be 0. Mathematically, $RS = \text{Gain} / 0$, causing a `ZeroDivisionError` or returning `inf`. Pandas handles `inf` gracefully in the formula `100.0 / (1.0 + inf) = 0`, correctly returning an RSI of 100.0.

## Production Usage
RSI is a crucial "Hard Filter." For a signal to be `bullish`, `core_momentum_filter_pass` must be `True`, which strictly requires `RSI >= 50`. No matter how good the price structure looks, if RSI is 49, the engine will not issue a buy signal.
