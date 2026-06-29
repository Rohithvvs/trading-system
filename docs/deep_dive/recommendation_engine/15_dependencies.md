# Recommendation Engine: Dependencies

This document maps the architectural dependencies of the Recommendation Engine.

## Which modules Recommendation Engine depends on (Upstream)
- **`TechnicalAnalysisService`**: For EMA/SMA/MACD/RSI/Volume scores and structure evaluation.
- **`BacktestService`**: For historical performance (CAGR, Win Rate, Drawdown) of the current setup.
- **`FundamentalAnalysisAgent` / `yfinance`**: For Rev Growth, Margins, D/E, P/E.
- **`NewsAnalysisAgent` / `LLMService`**: For sentiment scoring and reasoning generation.
- **`ScreenerService`**: Provides the initial shortlist of eligible symbols to analyze.
- **`FyersService` / `MarketDataFeed`**: The core provider of all OHLCV market data.

## Which modules depend on Recommendation Engine (Downstream)
- **`OrchestratorAgent`**: Calls the recommendation logic to formulate the `AnalysisResponse` and `FullAnalysisResponse`.
- **`RankingAgent` / `RankingService`**: Depends on the `score` produced by the Recommendation Engine to sort the final list of stocks.
- **Frontend / UI**: The final React UI renders the `FinalRecommendation` object (BUY/WATCH/REJECT badges, AI reasoning bullets, and Trade Plans).
- **`PaperTradingService` (Future Integration)**: The automated trading engine relies entirely on a strong `BUY` recommendation from this engine to initiate an automated entry state (`PENDING_ENTRY`).
