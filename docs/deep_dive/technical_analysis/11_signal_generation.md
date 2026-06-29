# Technical Analysis: Signal Generation

## Business Purpose
Signal generation is the process of synthesizing dozens of calculated indicators into a single, unambiguous directive: Should the system initiate a trade on this symbol? 

In this repository, signal generation happens in a two-stage process:
1. **Technical Stage (`TechnicalAnalysisService`)**: Calculates a score (0-100) and assigns a `bullish`, `neutral`, or `bearish` tag.
2. **Screener Stage (`ScreenerService`)**: Takes the technical score, combines it with broad market context (volume lift, long-term trend), and emits a final `matched` boolean (True = Buy, False = Reject).

## The Technical Stage (`TechnicalAnalysisService`)

### Hard Filters
Before any points matter, a symbol must pass three binary "Hard Filters". If any of these are False, the setup is considered structurally flawed and will be downgraded, regardless of its score.
```python
core_trend_filter_pass = bool(close_above_ema20 and supertrend_positive)
core_momentum_filter_pass = bool(macd_positive and rsi_supportive)
basic_liquidity_filter_pass = bool(volume_supportive)

hard_filters_pass = bool(core_trend_filter_pass and core_momentum_filter_pass and basic_liquidity_filter_pass)
```

### The Scoring Matrix
If a symbol possesses the trait, it receives the designated points:
* **Trend (max 54 pts):**
  * Close > EMA 20: **18 pts**
  * Supertrend Positive: **16 pts**
  * EMA 20 > EMA 50: **12 pts**
  * SMA 20 Uptrend: **8 pts**
* **Momentum (max 26 pts):**
  * MACD Positive: **12 pts**
  * RSI > 50 (Supportive): **8 pts**
  * RSI between 55-68 (Buy Zone): **6 pts**
* **Structure & Context (max 20 pts):**
  * Higher Timeframe Uptrend (Price > SMA50 AND SMA20 > SMA50): **10 pts**
  * Market Structure (HH/HL across 5 days): **up to 12 pts** (capped)
  * Candlestick pattern (Hammer/Doji): **4 pts**
* **Liquidity (max 15 pts):**
  * Volume > 50k: **5 pts**
  * Volume > Previous Day: **4 pts**
  * Price > 100: **4 pts**
  * Price < 500,000: **2 pts**

*Note: The theoretical maximum sum is over 100, but the final score is hard-capped:* `score = round(min(score, 100.0), 2)`

### Technical Signal Thresholds
```python
signal = "bullish" if hard_filters_pass and score >= 72 else "neutral" if hard_filters_pass and score >= 52 else "bearish"
```
* **BULLISH (Score >= 72 + Hard Filters Pass):** The ideal technical setup. Momentum is aligned with the trend on high volume.
* **NEUTRAL (Score >= 52 + Hard Filters Pass):** The stock is technically sound and meets the bare minimum requirements, but lacks the explosive alignment required for a high-confidence breakout.
* **BEARISH (Score < 52 OR Hard Filters Fail):** A flawed setup. Even if the score is 90, if `macd_positive` is False, the `hard_filters_pass` becomes False, and the stock is classified as `bearish`.

## The Screener Stage (`ScreenerService`)

The ScreenerService consumes the technical signal and applies the ultimate trading logic. It calculates a secondary `screener_score` combining the technical score (weighted at 50%) with dynamic variables like `volume_lift`.

### Final Trading Output
The Screener Service does not output "BUY", "SELL", or "WATCH". It outputs a `ScreenerConditionResult` object containing a `matched` boolean.

```python
matched = broad_eligibility and screener_score >= 52
```

* **MATCHED = True (Equivalent to a BUY signal):** 
  * The stock passed the broad eligibility (`close > sma_50` and `sma_50 > sma_200` and `volume > 100k`).
  * The Technical Engine output a `bullish` or `neutral` signal with a score of at least 52.
  * The final calculated `screener_score` remains >= 52.
* **MATCHED = False (Equivalent to REJECT / NO-TRADE):**
  * Fails broad eligibility.
  * Or `screener_score` drops below 52.

### Examples

**Example 1: The Perfect Setup (MATCHED = True)**
* Price is 150. EMA 20 is 145. (18 pts)
* Supertrend is positive. (16 pts)
* RSI is 62. (14 pts)
* MACD is positive. (12 pts)
* Volume is 200k, double yesterday's volume. (13 pts)
* All hard filters pass.
* **Technical Output:** Score = 73, Signal = `bullish`.
* **Screener Output:** Passes broad trend. `screener_score` calculates to 75. `matched` = True.

**Example 2: The Momentum Failure (MATCHED = False)**
* Price is 150. EMA 20 is 145. (18 pts)
* Supertrend is positive. (16 pts)
* RSI is 48. (0 pts)
* MACD is negative. (0 pts)
* **Technical Output:** Fails `core_momentum_filter_pass`. Hard filters fail. Signal downgraded to `bearish`. Score = 55.
* **Screener Output:** Because the hard filters failed, `broad_eligibility` becomes False. `matched` = False.
