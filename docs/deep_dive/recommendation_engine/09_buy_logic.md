# Recommendation Engine: BUY Logic

This document strictly defines how and why a `BUY` recommendation is issued. A `BUY` is the most privileged state in the system and requires passing multiple severe gates.

## 1. Initial Threshold
First, the weighted `Final Score` calculated by the `RecommendationService` must be **>= 72.0**.
This typically means the asset has strong technical alignment, solid fundamentals, and positive historical backtests.

## 2. The Strict Buy Gate
Once `RecommendationService` outputs "BUY", the `OrchestratorAgent` intercepts the result and runs `_enforce_strict_buy_gate()`. To survive this gate, ALL of the following conditions must be met:

### Condition A: Strong Technicals
The raw technical score (`TechnicalAnalysisResult.score`) must be **>= 75.0**.
*Reason:* The overall weighted score could be > 72 due to perfect fundamentals and news, but if the chart itself is not in a strong technical setup, entering the trade is premature.

### Condition B: Strong Execution (Risk-Reward)
The generated `TradePlan` must have a Risk-Reward ratio of **>= 1.25**.
*Reason:* The system will not recommend risking capital on a setup where the potential upside target is too close to the entry compared to the stop loss.

### Condition C: Strong Live Data
- `mock_warning` must be `False`.
- `minimum_swing_candles_met` must be `True` (e.g., >= 220 candles).
- `data_source` must exactly equal `"FYERS_PRIMARY"`.
*Reason:* A BUY recommendation signifies capital deployment. The engine refuses to authorize capital deployment on fallback data, mocked data, or charts missing enough history to calculate 200-day moving averages.

## Worked Example
- **Technical Score:** 80
- **Fundamental Score:** 0.8
- **Backtest Return:** 15%
- **Final Weighted Score:** 78 (Qualifies for BUY)
- **R/R Ratio:** 2.1 (Passes Condition B)
- **Data Source:** FYERS_PRIMARY (Passes Condition C)
- **Technical > 75:** Yes (80 > 75) (Passes Condition A)

**Result:** The recommendation remains **BUY**.
*Business Meaning:* The system has extremely high confidence that this is a statistically profitable entry point with confirmed market liquidity and acceptable risk parameters.
