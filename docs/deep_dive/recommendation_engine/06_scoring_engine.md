# Recommendation Engine: Scoring Engine

The Scoring Engine is the heart of the system. It mathematically quantifies the attractiveness of a setup. It operates in two major tiers: **Technical Scoring** and **Final Recommendation Scoring**.

## 1. Technical Scoring (`TechnicalAnalysisService`)

The technical score is calculated on a 0 to 100 scale. It aggregates trend, momentum, volume, and price structure.

**Swing Mode Calculations (Out of 100 max):**
- **Trend Alignment:**
  - Close above EMA20: `+18` points
  - EMA20 above EMA50: `+12` points
  - Supertrend is Positive: `+16` points
  - SMA 20-Day is in an Uptrend: `+8` points
  - Higher Timeframe Trend (SMA50): `+10` if uptrend, `+4` if sideways, `0` if downtrend
- **Momentum:**
  - MACD is positive (MACD > Signal): `+12` points
  - RSI is supportive (>= 50): `+8` points
  - RSI in Buy Zone (55 to 68): `+6` points
- **Volume & Liquidity:**
  - Volume > 50,000: `+5` points
  - Volume > Previous Day: `+4` points
  - Price > ₹100: `+4` points
  - Price < ₹5,000,000: `+2` points
- **Structure / Candles:**
  - Structure Score (Higher highs/lows): Up to `+12` points (3 points per confirmation)
  - Hammer or Gravestone Doji present: `+4` points

*The total is capped at 100.0.*
- Score >= 72 = **Bullish**
- Score >= 52 = **Neutral**
- Score < 52 = **Bearish**

## 2. Fundamental Scoring (`FundamentalAnalysisAgent`)

Calculates a score between `-1.0` and `1.0`.
- **Revenue Growth:** `(growth_pct / 20.0)` bounded [-1.0, 1.0].
- **Profit Margin:** `(margin_pct / 15.0)` bounded [-1.0, 1.0].
- **Debt to Equity:** `1.0` if <= 50. `-1.0` if >= 200. Linear penalty in between.
- **P/E Ratio:** `1.0` if < 10. `0.5` if 10-25. `-1.0` if > 50.
*Final Score = Average of the available factors.*

## 3. Backtest Scoring (`RecommendationService._backtest_component`)

Normalizes historical returns to a point system.
- If verdict is `insufficient` or trades < 5: `0.0` points.
- Otherwise, `raw_backtest = min(max(total_return * 4, -20), 100)`.

## 4. Final Recommendation Scoring (`RecommendationService`)

The final score aggregates the standardized raw scores using dynamic weights.

### Normalization:
- `raw_tech` = 0 to 100
- `raw_backtest` = -20 to 100
- `raw_news` = -100 to 100
- `raw_fund` = -100 to 100

### Formula:
```text
Final Score = (raw_tech * tech_wt) + (raw_backtest * backtest_wt) + (raw_news * news_wt) + (raw_fund * fund_wt)
```
*The result is strictly clamped between `0.0` and `100.0`.*

### Worked Example:
- Technical Score: `85` (Bullish)
- Backtest Return: `10%` -> `raw_backtest = 40`
- News Sentiment: `0.5` -> `raw_news = 50`
- Fundamental Score: `0.8` -> `raw_fund = 80`

Assuming Standard Regime Weights (Tech: 50%, Backtest: 25%, Fund: 25%, News: 0%):
`Final Score = (85 * 0.50) + (40 * 0.25) + (50 * 0.0) + (80 * 0.25)`
`Final Score = 42.5 + 10.0 + 0 + 20.0 = 72.5`

Since `72.5 >= 72`, the resulting recommendation is **BUY**.
