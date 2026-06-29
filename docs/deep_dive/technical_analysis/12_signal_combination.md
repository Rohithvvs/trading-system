# Technical Analysis: Signal Combination

## Business Purpose
No single technical indicator is foolproof. An RSI of 70 in a strong uptrend is bullish, but in a downtrend, it often marks a local top right before a crash. Signal combination is the mathematical process of requiring multiple independent indicators to agree before initiating a trade. This drastically reduces the win rate of false signals (whipsaws) and ensures capital is only deployed when probabilities are highly skewed in the system's favor.

## Conflict Resolution & Confirmation Logic

The engine resolves conflicts through a hierarchy of **Hard Filters** and **Additive Scoring**.

### 1. The Hard Filters (The Veto Power)
The engine groups indicators into specific themes. If a theme fails, the entire setup is vetoed, resolving conflicts immediately by defaulting to a "No Trade" (bearish) state.

* **Core Trend:** Requires *both* Price > EMA 20 AND Supertrend to be positive. If Price > EMA 20 but Supertrend is negative, the trend is considered conflicting and the filter fails.
* **Core Momentum:** Requires *both* MACD to be positive (MACD > Signal) AND RSI to be >= 50. If MACD is positive but RSI is 45, momentum is unconfirmed and the filter fails.
* **Basic Liquidity:** Requires Daily Volume > 50,000, Price > 100, and Price < 500,000.

**Conflict Example:** 
A stock reports blowout earnings. Price jumps 10% above the EMA 20 (Trend = Bullish). However, the MACD hasn't crossed over yet (Momentum = Bearish).
* **Resolution:** The `core_momentum_filter_pass` evaluates to False. `hard_filters_pass` becomes False. The signal defaults to `bearish`. The engine requires patience; it will not buy until momentum confirms the trend.

### 2. Weighted Scoring (The Confidence Interval)
Once the hard filters pass, the engine uses an additive weighted scoring model to resolve minor conflicts and rank the quality of the setup.

```python
score = 0.0
score += 18 if close_above_ema20 else 0
score += 12 if ema20_above_ema50 else 0
score += 16 if supertrend_positive else 0
score += 12 if macd_positive else 0
score += 8 if rsi_supportive else 0
score += 6 if rsi_in_buy_zone else 0
# ... [capped at 100]
```

**Conflict Example:**
A stock passes all hard filters. The EMA 20 is pointing up, but the EMA 20 has not yet crossed above the EMA 50 (a slightly lagging indicator). 
* **Resolution:** This is a minor conflict. The stock receives the 18 points for closing above the EMA 20, but is denied the 12 points for the EMA cross. The setup can still pass the 72-point `bullish` threshold if volume and structure are exceptional, compensating for the lagging EMA cross.

## Signal Priority (Screener Logic)

The `TechnicalAnalysisService` produces a score, but the `ScreenerService` has ultimate authority over signal combination through its own `_weighted_score` and `broad_eligibility` checks.

```python
def _weighted_score(self, candles: list[OHLCVPoint], technical, conditions: dict[str, bool]) -> float:
    # ...
    score += technical.score * 0.5  # Technical engine makes up 50% of final score
    score += 12 if conditions["broad_trend_eligibility"] else 0
    score += min(max(volume_lift, 0), 8) # Dynamic volume weighting
    return round(min(score, 100.0), 2)
```

### The Hierarchy of Priority
1. **Broad Market Eligibility:** (Screener) If Price < SMA 50 or SMA 50 < SMA 200, the stock is dead on arrival. Nothing else matters.
2. **Hard Technical Filters:** (Engine) Trend, Momentum, and Liquidity must align.
3. **Additive Technical Score:** (Engine) Defines the baseline setup quality.
4. **Volume Accelerator:** (Screener) Massive volume spikes can boost a mediocre `neutral` technical setup (e.g., score of 60) into a viable trade if the volume lift pushes the final screener score high enough.

## Final Output Generation
The final output is governed by the `matched` boolean in the `ScreenerConditionResult`. 
```python
matched = broad_eligibility and screener_score >= 52
```
If `matched` is True, the combination logic has determined that all major conflicts are resolved, momentum confirms trend, volume confirms price action, and the mathematical probability of a profitable breakout is high. The stock is added to the finalized shortlist.
