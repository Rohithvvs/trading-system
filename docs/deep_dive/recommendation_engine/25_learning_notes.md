# Recommendation Engine: Learning Notes

These notes serve as a primer for developers taking over maintenance or extension of the Recommendation Engine.

## Architectural Decisions

1. **Map-Reduce over Monolith:** Instead of one massive class analyzing a stock, the logic is aggressively decoupled into specialized Agents (Technical, Fundamental, News, Backtest). This makes testing trivial; you can test the `NewsAnalysisAgent` entirely in isolation without needing database connections or market data.
2. **Normalization is Key:** You cannot mathematically add a MACD value of `0.05` to a P/E ratio of `15` to a sentiment string of `"bullish"`. The system enforces that every sub-agent must output a normalized score (either `0 to 100` or `-1.0 to 1.0`). This allows the `RecommendationService` to treat them all identically in a clean, weighted formula.
3. **Strict Gate Overrides:** Math isn't perfect. Even if the weighted formula outputs 99/100, the `Orchestrator` applies business-logic vetoes (like checking if the data source was fake). This clear separation between "mathematical scoring" and "business rules gating" prevents spaghetti code.

## Best Practices

- **Never block the event loop:** The `OrchestratorAgent` coordinates 500 stocks at once. Any heavy math (like calculating moving averages for 10 years of daily data) MUST be done using Pandas vectorization (`analyze_bulk_from_frame`), NOT python `for` loops.
- **Fail Gracefully:** If Yahoo Finance is down, the system doesn't crash; `fundamental_score` becomes `0.0`. If Groq is down, the LLM generates deterministic string fallbacks. Ensure all new external API integrations follow this pattern.

## Common Mistakes

1. **Adding an indicator without updating max scores:** If you add Bollinger Bands to the `TechnicalAnalysisService` and assign it `+10` points, you MUST adjust the other point values so the total maximum score cannot exceed `100.0`. Otherwise, the baseline shifts and too many stocks will trigger a `BUY`.
2. **Polling APIs in a loop:** Never hit Fyers or Yahoo Finance in a loop per symbol. Always fetch in bulk, cache locally, and process from memory.

## Interview Questions (To test understanding)

1. **"Why might a stock have a Final Score of 85, but the UI shows it as a WATCH?"**
   *Answer:* It failed the strict buy gate in the Orchestrator, likely because the TradePlan's Risk/Reward ratio was poor, or the data was mocked.
2. **"How does the system handle a massive earnings miss on a stock that has a perfect uptrend?"**
   *Answer:* The LLM returns a high negative sentiment score. This triggers the Catalyst Regime in the weighting engine, dropping the Technical weight and heavily weighting the negative news, dragging the final score down to REJECT.

## Learning Roadmap (For extending the engine)
1. **Week 1:** Read and fully understand `orchestrator_agent.py` and `recommendation_service.py`. This is the core flow.
2. **Week 2:** Master Pandas DataFrame vectorization by reading `technical_analysis_service.py` (`analyze_bulk_from_frame`).
3. **Week 3:** Understand the AI prompting in `llm_service.py`.
4. **Week 4 (Project):** Try adding a new Agent (e.g., an `InsiderTradingAgent` that scrapes SEBI filings and returns a score from -1.0 to 1.0), and add it to the dynamic weighting formula.
