# Technical Analysis: Volume Analysis

## Business Purpose
Price action without volume is just noise. In financial markets, volume represents conviction. If a stock breaks out of a resistance level on low volume, it is highly likely to be a "false breakout" driven by retail traders or low liquidity. Conversely, a breakout on massive volume indicates institutional accumulation. The Technical Analysis Engine heavily factors volume into its final scoring to differentiate between true momentum and algorithmic manipulation.

## Implementation in Repository

Volume analysis occurs simultaneously in both the `ScreenerService` and the `TechnicalAnalysisService`.

### 1. Volume Spikes (Day-over-Day)
The engine checks if today's volume is greater than yesterday's volume. A price increase accompanied by a volume increase is the hallmark of a healthy trend.
```python
# In TechnicalAnalysisService._build_conditions
"volume_above_previous_day": latest.volume > previous.volume
```
**Scoring Impact:** Grants 3 to 4 points to the technical score depending on the exact mode.

### 2. Relative Volume Lift (Multiplier)
Rather than just checking a boolean condition, the engine calculates the percentage increase in volume day-over-day and converts it directly into points, rewarding massive volume spikes.
```python
# In ScreenerService._weighted_score
volume_lift = ((latest.volume - previous.volume) / previous.volume) * 100 if previous.volume else 0
score += min(max(volume_lift, 0), 8)
```
**Interpretation:** A 50% increase in volume day-over-day adds 0.5 points. However, a 400% increase adds 4.0 points. This score is capped at 8 points to prevent extreme outliers (e.g., 5000% volume due to an IPO block trade) from bypassing other technical filters.

### 3. Absolute Liquidity Filter (Volume > 50k)
Algorithms cannot easily exit positions in illiquid stocks without destroying the price (slippage). The engine hard-codes a minimum liquidity requirement.
```python
volume_above_50000 = bool(latest["volume"] > 50000)
```
**Scoring Impact:** Awards 3 to 5 points. More importantly, it is a component of the `basic_liquidity_filter_pass` hard filter.

### 4. Volume Trend (Intraday Mode)
In intraday mode, the engine compares a short-term volume moving average against a longer-term one to classify the volume trend as "expanding" or "stable".
```python
avg_vol_short = volume_unstack.tail(5).mean()
avg_vol_long = volume_unstack.tail(20).mean()
vol_trend = "expanding" if float(avg_vol_short[symbol]) > float(avg_vol_long[symbol]) else "stable"
score += 15 if vol_trend == "expanding" else 5
```

### 5. Volume Weighted Average Price (VWAP - Intraday)
VWAP is the institutional benchmark for intraday execution. It calculates the average price a security traded at throughout the day, based on both volume and price.
```python
typical_price = (high_unstack + low_unstack + close_unstack) / 3
vwap_unstack = (typical_price * volume_unstack).rolling(window=14).sum() / volume_unstack.rolling(window=14).sum()
close_above_vwap = bool(lc > vwap)
```
**Scoring Impact:** A close above VWAP awards a massive 20 points in intraday mode, signaling strong buyer control.

## Avoiding False Breakouts
A common scenario is a "Gap Up" on earnings where price shoots up 10% in the first minute but volume dries up for the rest of the day. The stock slowly bleeds out, trapping retail buyers. By requiring `volume_above_previous_day` and calculating `volume_lift`, the engine demands sustained participation, vastly reducing the win rate of false breakout setups.

## Production Usage
Volume acts as both a hard filter (`basic_liquidity_filter_pass`) and an accelerator (`volume_lift`). A technically perfect chart (MACD positive, RSI 60, Price > EMA 20) will still fail the screening process if the daily volume is under 50,000 shares, as the risk of slippage is too high for automated execution.
