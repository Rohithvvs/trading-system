# Recommendation Engine: Code Walkthrough

This guide walks through the physical files in `backend/app/` that power the Recommendation Engine.

## `agents/orchestrator_agent.py`
- **Role:** The brain of the operation.
- **Classes:** `OrchestratorAgent`.
- **Methods:**
  - `run_full()`: Main entry point. Coordinates concurrent data fetching and delegates to all sub-agents.
  - `_enforce_strict_buy_gate()`: Critical safety method. Intercepts `BUY` recommendations and downgrades them if technicals, data quality, or R/R are insufficient.
- **Dependencies:** All other agents. FyersService.

## `agents/recommendation_agent.py`
- **Role:** Synthesis coordinator.
- **Classes:** `RecommendationAgent`.
- **Methods:**
  - `run()`: Accepts the arrays of technicals, fundamentals, news, and backtests. Calls `LLMService` to generate reasoning, then calls `RecommendationService.build()` to get the final score and action.
- **Dependencies:** `LLMService`, `RecommendationService`.

## `services/recommendation_service.py`
- **Role:** The mathematical weighting and scoring engine.
- **Classes:** `RecommendationService`.
- **Methods:**
  - `build()`: Calculates the final normalized score (0-100) and assigns the BUY/WATCH/REJECT label.
  - `calculate_dynamic_weights()`: Determines if standard weights or catalyst weights should apply based on volume and news sentiment.
  - `_build_trade_plans()`: Calculates Entry, Stop Loss, and Targets using recent volatility ranges.

## `services/technical_analysis_service.py`
- **Role:** Pure technical calculation.
- **Classes:** `TechnicalAnalysisService`.
- **Methods:**
  - `analyze_bulk_from_frame()`: Highly optimized Pandas routine that calculates EMA, MACD, RSI, etc., and produces a raw `score` out of 100 for each symbol.

## `agents/backtest_agent.py` & `services/backtest_service.py`
- **Role:** Historical simulation.
- **Methods:**
  - `run()`: Simulates the technical strategy over the provided candles, calculating `total_return`, `cagr`, and `win_rate`. Returns a `verdict` (favorable/mixed/insufficient).

## `agents/fundamental_analysis_agent.py`
- **Role:** Financial health check.
- **Methods:**
  - `run()`: Hits `yfinance` to grab PE, debt-to-equity, and growth metrics.
  - `_calculate_fundamental_score()`: Normalizes these disparate financial ratios into a clean -1.0 to +1.0 score.

## `agents/news_analysis_agent.py` & `services/llm_service.py`
- **Role:** Unstructured text processing.
- **Methods:**
  - `analyze_sentiment()`: Prompts Groq to return a sentiment float.
  - `build_reasoning()`: Prompts Groq to explain the setup in plain English.
