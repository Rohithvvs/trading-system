# Recommendation Engine: WATCH Logic

The `WATCH` recommendation indicates that a stock is interesting and forming a setup, but is not yet actionable for capital deployment.

## Every Rule to Achieve WATCH
A recommendation becomes `WATCH` under two specific scenarios:

### Scenario 1: Standard Scoring Threshold
The weighted `Final Score` calculated by the `RecommendationService` falls between **55.0 and 71.99**.
- The stock has some positive momentum or fundamentals but lacks full confirmation.

### Scenario 2: Downgraded BUY
The `Final Score` was >= 72.0 (initial BUY), but the `OrchestratorAgent` downgraded it during `_enforce_strict_buy_gate()`.
This happens when:
- The `TradePlan` Risk-Reward ratio was `< 1.25`.
- The `Technical Score` was `< 75.0`.
- The data source was fallback/mocked or lacked minimum candle depth.

In Scenario 2, the system automatically appends a risk factor to the AI Reasoning:
> *"Strict BUY gate blocked this setup because live-data quality, backtest strength, or risk-reward confirmation was not strong enough."*
And modifies the summary:
> *"[Summary] BUY was downgraded to WATCH by the strict confirmation gate."*

## Examples

**Example A (Forming Setup):**
- Technical Score: 60 (Neutral/Slightly Bullish)
- Final Weighted Score: 58
- **Result:** WATCH. The chart is improving but not ready.

**Example B (Poor Risk/Reward):**
- Technical Score: 85 (Strong Bullish)
- Final Weighted Score: 76 (Initial BUY)
- R/R Ratio: 0.9 (Stop loss is further than Target 1)
- **Result:** Downgraded to WATCH. The setup is good, but the entry timing or volatility makes the risk unacceptable.
