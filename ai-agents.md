# AI Agents — Design & Implementation

This document is a code-driven inventory and explanation of the AI agents implemented in this repository (extracted from the code as of 2026-04-13). It ties behavior directly to implementation files and does not invent components that are not present in the codebase.

Sources: key files referenced inline (open these for full detail):
- [backend/app/agents/orchestrator_agent.py](backend/app/agents/orchestrator_agent.py)
- [backend/app/agents/router_agent.py](backend/app/agents/router_agent.py)
- [backend/app/agents/technical_analysis_agent.py](backend/app/agents/technical_analysis_agent.py)
- [backend/app/agents/news_analysis_agent.py](backend/app/agents/news_analysis_agent.py)
- [backend/app/agents/backtest_agent.py](backend/app/agents/backtest_agent.py)
- [backend/app/agents/recommendation_agent.py](backend/app/agents/recommendation_agent.py)
- [backend/app/agents/ranking_agent.py](backend/app/agents/ranking_agent.py)
- [backend/app/services/llm_service.py](backend/app/services/llm_service.py)
- [backend/app/services/recommendation_service.py](backend/app/services/recommendation_service.py)
- [backend/app/services/technical_analysis_service.py](backend/app/services/technical_analysis_service.py)
- [backend/app/services/backtest_service.py](backend/app/services/backtest_service.py)
- [backend/app/services/news_service.py](backend/app/services/news_service.py)
- [backend/app/services/sentiment_service.py](backend/app/services/sentiment_service.py)
- [backend/app/schemas](backend/app/schemas) (Pydantic contracts)

---

## 1. Overview

Purpose of agents in this system:
- Encapsulate discrete domain responsibilities (technical indicators, backtesting, news sentiment, recommendation synthesis, ranking). Agents are synchronous wrapper classes that delegate to services which implement the heavy work. The agent layer provides a clear place to orchestrate and to unit-test each domain capability.

Key architectural constraint visible in the code: all agents are invoked synchronously inside the request lifecycle (no background queue), and heavy compute is performed inline (pandas, TA, backtests). This drives the operational considerations documented below.

---

## 2. Orchestrator Agent

File: [backend/app/agents/orchestrator_agent.py](backend/app/agents/orchestrator_agent.py)

Responsibilities
- Top-level conductor for analysis flows: `run_full`, `run_partial`, and `run_screener`.
- For each requested symbol it:
  - obtains OHLCV via `FyersService.fetch_ohlcv`,
  - runs technical analysis (`TechnicalAnalysisAgent`),
  - runs backtests (`BacktestAgent`),
  - runs news + sentiment (`NewsAnalysisAgent`),
  - invokes `RecommendationAgent` to produce the `FinalRecommendation`,
  - persists `AnalysisHistory` and `BacktestHistory` records.
- Produces top-level responses: `AnalysisResponse`, `FullAnalysisResponse`, or `ScreenerResponse` (see [backend/app/schemas](backend/app/schemas)).

Decision logic (how it selects agents)
- Deterministic: the Orchestrator always runs the technical, backtest, and news agents for every symbol (modes are resolved from the `AnalysisRequest` - intraday/swing/both). After these agents run it always invokes `RecommendationAgent` and then `RankingAgent` for post-processing. There is no runtime policy that conditionally omits an agent—agents are assembled in a fixed pipeline.

Input / Output formats
- Input: `AnalysisRequest` or `ScreenerRequest` (Pydantic models in [backend/app/schemas/analysis.py](backend/app/schemas/analysis.py)).
- Per-symbol intermediate types: `OHLCVPoint` (candles), `TechnicalAnalysisResult`, `BacktestResult`, `ArticleItem` (news), `FinalRecommendation`.
- Output: `StockAnalysisResult` items collected into `AnalysisResponse` or `FullAnalysisResponse`.

Operational note: the orchestrator runs in-process and sequentially (e.g., items = [self._analyze_symbol(...) for symbol in request.symbols]) — no concurrency/threadpool inside the orchestrator.

---

## 3. Individual agents (implemented in code)

Below are the actual agents present in the repository. The five names you listed earlier (Summary, Scope, Question, Review, Suggestion) are not implemented verbatim in the code; where similar functionality exists I explicitly map it below.

### TechnicalAnalysisAgent
File: [backend/app/agents/technical_analysis_agent.py](backend/app/agents/technical_analysis_agent.py)

Purpose
- Compute indicator payloads and a numeric technical score used by the recommendation engine.

Input
- `symbol: str`, `candles: list[OHLCVPoint]`, `mode: AnalysisMode` (intraday/swing).

Output
- `TechnicalAnalysisResult` Pydantic model containing `mode`, `signal` (`bullish`/`neutral`/`bearish`), `score`, `indicators` (dictionary), and `summary`.

Implementation / prompt strategy
- Delegates to `TechnicalAnalysisService.analyze` which builds a pandas DataFrame and computes indicators (EMA, SMA, MACD, RSI, VWAP, Supertrend, volume stats) using the `ta` package. Scoring thresholds and hard filters are implemented procedurally in `_build_indicator_payload`.

When triggered
- For each mode resolved by `OrchestratorAgent._resolve_modes` inside `_analyze_symbol`.

### BacktestAgent
File: [backend/app/agents/backtest_agent.py](backend/app/agents/backtest_agent.py)

Purpose
- Run a simple strategy backtest to generate performance metrics used in recommendation scoring.

Input
- `symbol: str`, `mode: AnalysisMode`, `candles: list[OHLCVPoint]`.

Output
- `BacktestResult`: fields include `strategy_name`, `total_return`, `cagr`, `max_drawdown`, `win_rate`, `profit_factor`, `trade_count`, `verdict`, and `equity_curve`.

Implementation / prompt strategy
- Uses `BacktestService.run` which constructs a pandas DataFrame, computes EMA/RSI/MACD and simulates entry/exit based on rules. If the candlestick history is too short (len < 35) it returns an `_empty_result` with `verdict='insufficient'`.

When triggered
- Per-mode in `OrchestratorAgent._analyze_symbol` immediately after technical analysis.

### NewsAnalysisAgent
File: [backend/app/agents/news_analysis_agent.py](backend/app/agents/news_analysis_agent.py)

Purpose
- Fetch recent news articles for a symbol and compute an aggregated sentiment.

Input
- `symbol: str`.

Output
- Tuple: `(articles: list[ArticleItem], sentiment_score: float, sentiment_label: str, summary: str)`.

Implementation / prompt strategy
- Uses `NewsService.fetch_recent_news` (which falls back to `generate_mock_articles` when `settings.news_api_key` is not configured) and `SentimentService.summarize` which computes the mean of article sentiment scores and maps thresholds: score >= 0.2 -> `positive`; <= -0.2 -> `negative`; otherwise `neutral`. The service returns a one-line summary string.

When triggered
- During the per-symbol pipeline inside `OrchestratorAgent._analyze_symbol`.

### RecommendationAgent
File: [backend/app/agents/recommendation_agent.py](backend/app/agents/recommendation_agent.py)

Purpose
- Aggregate technical, news and backtest signals and produce a structured `FinalRecommendation` (action, confidence, score, reasoning, trade plans, summary).

Input
- `symbol: str`, `technical_results: list[TechnicalAnalysisResult]`, `sentiment_label: str`, `sentiment_score: float`, `backtests: list[BacktestResult]`, `candles_by_mode: dict[AnalysisMode, list[OHLCVPoint]]`.

Output
- `FinalRecommendation` Pydantic model (fields: `action`, `confidence`, `score`, `reasoning`, `trade_plans`, `summary`).

Implementation / prompt strategy
- Builds an `llm_reasoning` dictionary by calling `LLMService.build_reasoning(symbol, prompt_context)` where `prompt_context` includes technical signals, sentiment, backtest verdict and current price.
- `LLMService` first attempts a provider call to Groq (HTTP POST to `https://api.groq.com/openai/v1/chat/completions`) using a system prompt that enforces JSON-only output and advisory-only language. The user prompt asks for 3 concise bullets, 2 risk factors, 2 invalidation signals and a short summary. Call parameters: `temperature=0.2`, `response_format` type `json_object`, `timeout=20`.
- If the provider call fails or the response is invalid, `LLMService._fallback_reasoning` constructs a deterministic, limited reasoning object from available context (see [backend/app/services/llm_service.py](backend/app/services/llm_service.py)).
- The `RecommendationService.build` converts the `llm_reasoning` plus deterministic signals into a numeric `score`, `confidence`, and `trade_plans` (see [backend/app/services/recommendation_service.py](backend/app/services/recommendation_service.py)). Trade-plans are computed from technical setups and backtest support.

When triggered
- After technical/backtest/news for a symbol inside `OrchestratorAgent._analyze_symbol`.

### RankingAgent
File: [backend/app/agents/ranking_agent.py](backend/app/agents/ranking_agent.py)

Purpose
- Produce ranked lists from the final per-symbol recommendations. Creates `RankingsResponse` which includes ranked lists, grouped buy/watch lists, and best candidates per mode.

Input
- `items: list[StockAnalysisResult]`.

Output
- `RankingsResponse` (rankings, buy_rankings, watch_rankings, best_intraday_candidate, best_swing_candidate, disclaimer).

Implementation
- Delegates to `RankingService.rank` which sorts by `recommendation.score` and constructs grouped lists and best-by-mode calculations.

When triggered
- After the orchestrator has built the `items` collection (final step in `run_full` or `run_partial`).

### RouterAgent (facade)
File: [backend/app/agents/router_agent.py](backend/app/agents/router_agent.py)

Purpose
- Thin adapter used by route handlers to delegate to orchestrator flows. Methods map endpoints to orchestrator methods (e.g., `full_analysis`, `rankings`, `screener_full`).

When triggered
- Called directly from API routes under [backend/app/routes](backend/app/routes).

---

## 4. Agent communication flow (sequence / flow diagram)

Request: POST /analysis/full (frontend calls `runFullAnalysis`) → FastAPI route handler → RouterAgent → OrchestratorAgent

Per-symbol pipeline (simplified):

Client -> HTTP -> FastAPI route (/analysis/full)
  -> RouterAgent.full_analysis()
    -> OrchestratorAgent.run_full()
      -> for symbol in request.symbols:
         -> FyersService.fetch_ohlcv(symbol, mode)  (data retrieval)
         -> TechnicalAnalysisAgent.run(symbol, candles, mode)  (indicators & score)
         -> BacktestAgent.run(symbol, mode, candles)  (performance metrics)
         -> NewsAnalysisAgent.run(symbol)  (articles & sentiment)
         -> RecommendationAgent.run(...)  (calls LLMService.build_reasoning(...))
            -> LLMService._build_with_groq(...) [HTTP call to provider]
               -> fallback to LLMService._fallback_reasoning(...) on error
         -> RecommendationService.build(...)  (final score, trade plans)
         -> persist AnalysisHistory & BacktestHistory
      -> RankingAgent.run(items)
    -> return FullAnalysisResponse -> HTTP response -> Client

Notes:
- All of the above are synchronous, blocking operations (requests, pandas, ta, backtest loops). There is no internal task queue in the orchestrator.

---

## 5. Error handling (what happens if an agent fails)

- LLM failures: `LLMService` catches exceptions from the provider call and returns a deterministic fallback (`_fallback_reasoning`). The recommendation flow continues using fallback reasoning (see [backend/app/services/llm_service.py](backend/app/services/llm_service.py)).
- Data provider failures: `FyersService.fetch_ohlcv` will return generated mock candles when live FYERS credentials are not present. `NewsService.fetch_recent_news` falls back to `generate_mock_articles` when the news API is not configured. These fallbacks are explicit in service code.
- Backtest insufficiency: `BacktestService.run` returns `_empty_result` with `verdict='insufficient'` when there are too few candles; orchestrator still proceeds to recommendation and persists the `insufficient` verdict.
- Persistence / DB errors: Orchestrator calls `self.db.commit()` after adding records; if the DB commit fails an exception will propagate back through FastAPI. The app has a middleware that logs request failures (see [backend/app/main.py](backend/app/main.py)).
- Overall strategy: agents attempt non-fatal fallbacks for external dependencies and propagate structured partial results rather than failing the entire flow silently. Errors are logged and surfaced as HTTP errors only when they are terminal (e.g., invalid input, DB constraint violation).

---

## 6. Extensibility — how to add a new agent

Pattern observed in codebase:
1. Add a service that implements the heavy logic in `backend/app/services` (optional, recommended for testability and separation).
2. Add an agent class in `backend/app/agents` that wraps that service and exposes a `.run(...)` method returning a typed Pydantic result (or a primitive tuple) — follow existing agents (e.g., `TechnicalAnalysisAgent`).
3. Instantiate the agent inside `OrchestratorAgent.__init__` and call it from `_analyze_symbol` at the appropriate point.
4. If the agent returns new fields that should be included in API responses, extend the Pydantic schemas in `backend/app/schemas` accordingly.
5. Add unit tests for the service and an integration test for the orchestrator pipeline.

Minimal example (pseudocode, follow repository patterns):

1) service: `backend/app/services/my_new_service.py` (pure logic)
2) agent wrapper: `backend/app/agents/my_new_agent.py`

class MyNewAgent:
    def __init__(self):
        self.service = MyNewService()

    def run(self, symbol, context):
        return self.service.execute(symbol, context)

3) orchestration: add `self.my_new_agent = MyNewAgent()` to `OrchestratorAgent.__init__` and call `output = self.my_new_agent.run(symbol, ...)` inside `_analyze_symbol`.

---

## 7. Mapping requested agent names (Summary, Scope, Question, Review, Suggestion)

The repository does not contain agents named `SummaryAgent`, `ScopeAgent`, `QuestionAgent`, `ReviewAgent`, or `SuggestionAgent`. Below are mapping notes for where similar responsibilities currently live in code:

- **Summary**: `LLMService.build_reasoning` (invoked by `RecommendationAgent`) produces a `summary` field returned inside the `FinalRecommendation.reasoning.summary`.
- **Suggestion**: `RecommendationService.build` creates `trade_plans` and a human-readable `summary` — this is the system's actionable suggestion layer.
- **Review**: `RankingAgent` + `RankingService` produce ranked review lists and context; historical review data is persisted via `AnalysisHistory` and `BacktestHistory` by the `OrchestratorAgent`.
- **Scope / Question**: there is no dedicated agent that formulates scope or follow-up questions. Those features would be implemented by adding a new agent (see Extensibility) that calls the LLM with a context and a question-generation prompt.

If you want these exact-named agents added, the codebase pattern above shows where to add them: implement the service, unit-test, wrap in an agent class, and call from the orchestrator (or expose via a new route).

---

## 8. Operational remarks tied to code

- Sync/blocking pipeline: because the current orchestrator calls services synchronously and uses blocking HTTP calls and CPU-bound computations (pandas/ta/backtests), the deployed server must either limit concurrent request workers or move heavy tasks to background workers (e.g., Celery / RQ / Azure Functions) to avoid request timeouts.
- LLM provider abstraction: `LLMService` currently uses Groq (settings.llm_provider default) and falls back to deterministic reasoning. To swap to Azure OpenAI, implement an alternative `_build_with_azure` path in `LLMService` or add a provider adapter.
- Data source awareness: `OrchestratorAgent._data_source_label()` and `_data_warning()` explicitly signal when results are mock-only; the frontend surfaces `data_warning`. This is important for safety if productionizing.

---

## 9. Quick references (where to look in code)
- Orchestration: [backend/app/agents/orchestrator_agent.py](backend/app/agents/orchestrator_agent.py)
- LLM integration: [backend/app/services/llm_service.py](backend/app/services/llm_service.py)
- Recommendation logic: [backend/app/services/recommendation_service.py](backend/app/services/recommendation_service.py)
- Technical indicators: [backend/app/services/technical_analysis_service.py](backend/app/services/technical_analysis_service.py)
- Backtest engine: [backend/app/services/backtest_service.py](backend/app/services/backtest_service.py)
- News & sentiment: [backend/app/services/news_service.py](backend/app/services/news_service.py), [backend/app/services/sentiment_service.py](backend/app/services/sentiment_service.py)
- Agents folder: [backend/app/agents](backend/app/agents)

---

If you want, I can now:
- generate a diagram in PlantUML or Mermaid from this flow, or
- scaffold a `SummaryAgent` / `QuestionAgent` prototype and wire it into the orchestrator as a pull request.
