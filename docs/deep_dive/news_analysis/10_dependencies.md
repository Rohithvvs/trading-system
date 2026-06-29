# 10 Dependencies

The News Analysis Engine is deeply integrated into the Orchestrator flow.

## 1. Market Data (FyersService)
News is not processed in isolation. The `RecommendationService` looks at the latest volume from the OHLCV candles (provided by `FyersService`) to see if the news correlates with a volume spike (`current_volume > avg_volume * 3.0`).

## 2. Technical Analysis Engine
News scoring weights are blended with the `TechnicalAnalysisResult`. 

## 3. Recommendation Engine
The final consumer of the News Engine.

## 4. Database
`AnalysisHistory` stores the final `sentiment_score`. (No Redis caching is used).

## 5. Schedulers
Not implemented. Orchestrator triggers news on-the-fly sequentially per symbol.

## 6. External APIs
- Groq API (LLM inference)
- DuckDuckGo (Fallback web search)
- Custom News API endpoint (Configured via env vars)