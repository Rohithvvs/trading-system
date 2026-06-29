# Recommendation Engine: Weighting Engine

The Weighting Engine (`RecommendationService.calculate_dynamic_weights`) defines how much influence each analytical module has over the final decision. The engine employs **Dynamic Weights**, meaning the percentages shift depending on real-time market catalysts.

## Standard Regime
Under normal market conditions, Technicals drive the decision, validated by Fundamentals and Historical Backtesting. News sentiment is ignored to prevent noise.

- **Technical:** 50% (`0.50`)
- **Fundamental:** 25% (`0.25`)
- **Backtest:** 25% (`0.25`)
- **News/Sentiment:** 0% (`0.0`)

## Catalyst Regime
If the system detects a significant catalyst, the weighting dynamically shifts to prioritize immediate macro or micro events over historical and pure technical data.

### Catalyst Triggers:
1. **News Catalyst:** The absolute sentiment score is extreme (`abs(sentiment_score) >= 0.75`).
2. **Volume Catalyst:** The current candle's volume is more than 300% (3x) of the recent 20-period average volume.

### Catalyst Weights:
When a catalyst is active, News and Fundamentals become the dominant drivers, while Technicals and Backtesting are suppressed.

- **News/Sentiment:** 30% (`0.30`)
- **Fundamental:** 30% (`0.30`)
- **Technical:** 20% (`0.20`)
- **Backtest:** 20% (`0.20`)

## Why are weights configurable this way?
This dynamic approach solves a critical business problem: **Lagging Indicators.**
Technical indicators like EMAs and SMAs lag price. In a highly volatile catalyst event (e.g., earnings blowout or catastrophic regulatory news), technicals will look fine for several candles while the stock is actually crashing. By detecting the volume surge or extreme news sentiment, the engine instantly down-weights the lagging technicals and allows the negative news score to aggressively override the final score, protecting the trader.
