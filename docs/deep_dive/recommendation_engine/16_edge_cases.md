# Recommendation Engine: Edge Cases

## 1. Technical indicators conflict (e.g. RSI is overbought, but MACD is crossing up)
- **What happened:** Price structure is mixed.
- **Implementation:** `TechnicalAnalysisService` adds points for MACD, but might not add points for RSI if it's out of the 'buy zone' (55-68). The overall Technical Score will likely be mediocre (~50-60). 
- **Recovery:** Will result in a `WATCH` or `REJECT` recommendation.

## 2. News unavailable / API fails
- **What happened:** News API times out or returns no articles.
- **Implementation:** `NewsAnalysisAgent` returns empty articles, `LLMService` returns a neutral `0.0` sentiment score.
- **Recovery:** Weighting engine uses standard weights (0% to news). No impact on core technical/backtest scoring.

## 3. Backtesting unavailable (Not enough candles)
- **What happened:** A recently listed stock has only 20 daily candles, but SMA200 requires 200+.
- **Implementation:** `BacktestService.run()` detects `< 35` candles and immediately returns an empty result (`verdict="insufficient"`).
- **Recovery:** `RecommendationService` assigns `0.0` points for the backtest component. A stock with no backtest history will likely struggle to hit the `BUY` threshold, defaulting to `WATCH`.

## 4. Market Data Source Failed (Fallback to Mock Data)
- **What happened:** Fyers API credentials expire during the day.
- **Implementation:** The orchestrator switches to mocked data or fallback modes.
- **Recovery:** `OrchestratorAgent._enforce_strict_buy_gate()` checks `data_quality.get("mock_warning")`. Because it is true, ANY `BUY` recommendation is forcefully downgraded to `WATCH` to prevent trading on fake data.

## 5. Low Volume / Gap Up / Extreme Volatility
- **What happened:** A massive gap up on 10x normal volume.
- **Implementation:** `RecommendationService.calculate_dynamic_weights` detects `current_volume > (avg_volume * 3.0)`. It triggers the **Catalyst Regime**, assigning 30% weight to News and Fundamentals, anticipating that the gap is fundamentally driven.
- **Recovery:** If the news isn't highly positive, the score will collapse.

## 6. AI Timeout
- **What happened:** Groq API hangs for 20+ seconds.
- **Implementation:** `LLMService.build_reasoning` catches the timeout exception.
- **Recovery:** Immediately falls back to `_fallback_reasoning()`, generating deterministic Python-formatted strings. The pipeline does not halt.

## 7. No Shortlisted Stocks
- **What happened:** `ScreenerService` finds zero stocks matching the current market criteria.
- **Implementation:** `OrchestratorAgent` detects an empty shortlist.
- **Recovery:** Skips the entire `RecommendationAgent` flow and returns an empty `ScreenerResponse`.
