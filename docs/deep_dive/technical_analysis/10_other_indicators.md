# Technical Analysis: Additional Indicators

Beyond the standard trend (EMA/SMA) and momentum (RSI/MACD) indicators, the Technical Analysis Engine implements several structural and custom indicators to qualify price action.

---

## 1. Supertrend

### Business Purpose
Supertrend is a volatility-adjusted trailing stop-loss indicator. It uses Average True Range (ATR) to calculate an upper and lower band. When price crosses the band, the trend "flips." It is exceptional at keeping traders in a winning position during a strong trend while filtering out minor volatility spikes.

### Implementation
* **Method:** `_calculate_supertrend(frame, period=10, multiplier=3.0)`
* **Logic:** 
  1. Calculates True Range (TR) using the max of `(High - Low)`, `abs(High - PrevClose)`, and `abs(Low - PrevClose)`.
  2. Calculates ATR using a 10-period EMA of TR.
  3. Calculates Upper and Lower bands `(High + Low) / 2 ± (3 * ATR)`.
  4. Iterates sequentially (cannot be perfectly vectorized in Pandas) to pull the bands tighter to the price and flip the boolean `direction_up` when price closes across the band.

### Usage in Engine
```python
supertrend_positive = bool(supertrend_point.direction_up and lc >= supertrend_point.value)
```
If the Supertrend is positive, it awards 16 points and acts as a core requirement for the `core_trend_filter_pass`.

---

## 2. Support and Resistance (Rolling Limits)

### Business Purpose
Identifying recent pivot points to determine risk-to-reward. If a stock is trading immediately below resistance, buying it is mathematically disadvantageous. 

### Implementation
The engine calculates a rolling 20-period minimum for Support and maximum for Resistance.
```python
support_series = grouped["low"].transform(lambda x: x.rolling(window=20).min())
resistance_series = grouped["high"].transform(lambda x: x.rolling(window=20).max())
```

### Usage in Engine
Currently, these values are returned in the `indicators` dictionary to the frontend/downstream systems for UI rendering or position sizing, but they are not directly used in the point-based scoring algorithm in the current codebase.

---

## 3. Market Structure (Higher-Highs / Higher-Lows)

### Business Purpose
An uptrend is formally defined as a series of Higher Highs (HH) and Higher Lows (HL). The engine does not rely solely on moving averages; it inspects the actual bar-by-bar price action over a 5-day window to confirm structural uptrends.

### Implementation
```python
prev_1 = {"high": float(sym_candles[-2].high), "low": float(sym_candles[-2].low)}
prev_2 = {"high": float(sym_candles[-3].high), "low": float(sym_candles[-3].low)}
# ... up to prev_5

hh_hl_2d = bool(prev_1["high"] > prev_2["high"] and prev_1["low"] > prev_2["low"])
hh_hl_3d = bool(prev_1["high"] > prev_3["high"] and prev_1["low"] > prev_3["low"])
hh_hl_4d = bool(prev_1["high"] > prev_4["high"] and prev_1["low"] > prev_4["low"])
latest_confirms_5d_structure = bool(latest["high"] > prev_1["high"] and prev_1["low"] > prev_5["low"])
```

### Usage in Engine
Each confirmed structural timeframe adds to a `structure_score` which is capped at 12 points. `structure_supportive = bool(structure_score >= 2)` acts as a secondary confirmation check.

---

## 4. Candlestick Patterns

### Business Purpose
Candlesticks represent raw human emotion. A "Hammer" indicates that sellers pushed the price down, but buyers overwhelmed them and closed the price near the high, signaling aggressive institutional buying at support.

### Implementation: Hammer
```python
def _is_hammer(self, candle: pd.Series) -> bool:
    body = abs(candle["close"] - candle["open"])
    range_size = candle["high"] - candle["low"]
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]
    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    if range_size == 0: return False
    return bool(lower_wick >= body * 2 and upper_wick <= body and body / range_size < 0.4)
```
* **Logic:** The lower wick must be at least twice the size of the body. The upper wick must be smaller than the body. The body must be small relative to the entire daily range.

### Implementation: Gravestone Doji
```python
def _is_gravestone_doji(self, candle: pd.Series) -> bool:
    body = abs(candle["close"] - candle["open"])
    range_size = candle["high"] - candle["low"]
    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]
    if range_size == 0: return False
    return bool(body / range_size < 0.1 and upper_wick > range_size * 0.6 and lower_wick < range_size * 0.15)
```
* **Logic:** Opens and closes at nearly the exact same price at the very bottom of the range. The massive upper wick signifies that buyers tried to push the price up, but sellers completely destroyed them. (Note: Despite being traditionally bearish, in the context of this specific breakout engine, the `hammer_or_gravestone` boolean is grouped as an extreme volatility identifier awarding 4 points, though it rarely triggers in conjunction with bullish trend filters).

### Usage in Engine
```python
hammer = self._is_hammer(pd.Series(latest))
gravestone_doji = self._is_gravestone_doji(pd.Series(latest))
hammer_or_gravestone = bool(hammer or gravestone_doji)
score += 4 if hammer_or_gravestone else 0
```
