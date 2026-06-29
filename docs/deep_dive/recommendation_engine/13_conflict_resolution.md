# Recommendation Engine: Conflict Resolution

Conflict resolution defines how the engine decides when different analytical modules fundamentally disagree.

## Suppose:
- **Technical Analysis:** says BUY (Score 85)
- **News:** says NEGATIVE (Score -0.90)
- **Backtesting:** says GOOD (CAGR 20%)
- **Volume:** says LOW (Current < Avg)

## How does the system decide?

### 1. Regime Detection (The primary resolver)
The `RecommendationService.calculate_dynamic_weights` method looks for active catalysts.
- Is `abs(sentiment_score) >= 0.75`? Yes (|-0.90| >= 0.75).
- Because a Catalyst is active, the engine enters the **Catalyst Regime**.

### 2. Weight Shifting
In the Catalyst Regime, the weights shift aggressively:
- Technicals drop from 50% to 20%.
- Backtesting drops from 25% to 20%.
- News increases from 0% to 30%.
- Fundamentals increase to 30%.

### 3. Score Recalculation
- Tech (85 * 0.2) = 17
- Backtest (Max Return * 0.2) = ~15
- News (-90 * 0.3) = -27
- Fund (Assume Neutral 0 * 0.3) = 0
- **Final Score = 5**

### Result: REJECT
Even though the chart looked perfect and the backtest was highly profitable, the severe negative news acted as a catalyst. The weighting engine amplified the negative news and suppressed the lagging technicals, correctly identifying that the historical patterns are about to be invalidated by breaking macro events.

## What if News was Neutral but Volume was LOW?
If News was neutral and volume was low, the Catalyst Regime is **NOT** triggered.
Standard weights apply: Tech 50%, Backtest 25%, Fund 25%.
The engine would likely output a `BUY` or `WATCH` (based on final score), because low volume alone does not trigger a regime shift (only high volume spikes > 3x average trigger the Volume Catalyst). However, low volume might impact the Technical Score itself (losing points in the Liquidity metric), potentially keeping the score below 75, triggering a downgrade to `WATCH` in the strict buy gate.
