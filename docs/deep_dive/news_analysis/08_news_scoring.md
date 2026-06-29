# 08 News Scoring

## How News Affects Stock Scores
News sentiment directly impacts the final stock score via the `RecommendationService`.

## Weighting and Thresholds
In `RecommendationService.calculate_dynamic_weights`, a dynamic weighting system is used:
- **Standard Regime**: Technical (50%), Fundamental (25%), Backtest (25%), News (0%).
- **Catalyst Regime**: Triggered if `abs(sentiment_score) >= 0.75` (or high volume).
  - If a catalyst is active, the weights shift to: News (30%), Fundamental (30%), Technical (20%), Backtest (20%).

## Score Calculation
- The raw news score (`sentiment_score * 100`) is multiplied by the dynamic weight (`news_wt`).
- E.g., a sentiment score of `0.80` during a catalyst regime contributes `80 * 0.30 = 24` points to the final 100-point scale.

## Examples
- A stock has a technical score of 80. Sentiment is `0.90` (Catalyst triggered). 
- News Weight becomes 30%. News contributes `90 * 0.30 = 27` points. 
- Technical weight drops to 20%, contributing `80 * 0.20 = 16` points.
- This allows a strong news catalyst to carry a moderately technical setup into a `BUY`.