# 09 Signal Generation

## Sentiment Contribution
The sentiment score feeds directly into `FinalRecommendation`.

## Dependency Chain
1. `NewsService` fetches raw articles.
2. `SentimentService` calculates float score via `LLMService`.
3. `RecommendationService.build` evaluates:
   - If `sentiment_score >= 0.75` or `<= -0.75`, it triggers **Catalyst Regime**.
   - Applies dynamic weights.
   - Calculates total score out of 100.
4. Thresholds applied to Total Score:
   - `>= 72` -> **BUY**
   - `>= 55` -> **WATCH**
   - `< 55` -> **REJECT**

## Reasoning Generation
The `LLMService.build_reasoning` incorporates the `news_label` (e.g., "positive", "negative") into the prompt context to generate readable risk factors and summaries explaining *why* the signal was generated.