# Specification — Trading System

Derived strictly from the repository code. This file documents functional modules, API capabilities (grouped), AI responsibilities, frontend flows, storage design, and integrations found in the codebase.

**1. High-level modules**
- **API / HTTP**: [backend/app/main.py](backend/app/main.py) registers routes and middleware.
- **Routes**: grouped under [backend/app/routes](backend/app/routes) — `analysis`, `stocks`, `paper-trading`, `health`.
- **Agents**: orchestration layer under [backend/app/agents](backend/app/agents) — `OrchestratorAgent`, `RouterAgent`, `TechnicalAnalysisAgent`, `NewsAnalysisAgent`, `BacktestAgent`, `RecommendationAgent`, `RankingAgent`.
- **Services**: domain logic under [backend/app/services](backend/app/services) — technical analysis, backtest, recommendation, ranking, LLM wrapper, FYERS client, news, sentiment, paper trading.
- **Models & Schemas**: DB models under [backend/app/models](backend/app/models) and Pydantic schemas under [backend/app/schemas](backend/app/schemas).
- **DB & config**: SQLAlchemy wiring in [backend/app/db](backend/app/db), settings in [backend/app/config/settings.py].
- **Frontend**: Vite + React app in `frontend/` (notably `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/components`).

**2. Data flow (typical request)**
1. Client triggers scan or analysis via frontend (`runPresetScreener` or `runFullAnalysis`) → HTTP POST to API.
2. API route delegates to `RouterAgent` which uses `OrchestratorAgent`.
3. `OrchestratorAgent` coordinates: fetch candles via `FyersService`, run `TechnicalAnalysisAgent`, `BacktestAgent`, `NewsAnalysisAgent` → gather signals.
4. `RecommendationAgent` calls `LLMService` for reasoning and `RecommendationService` to produce `FinalRecommendation`.
5. `RankingAgent` produces rankings; results are optionally persisted (analysis and backtest history) via Orchestrator.
6. Response returned and rendered by frontend components (CandidateTable, StockDetailPanel); user may send prefill to paper trading endpoints.

**3. API capabilities (grouped by feature)**
- **Health**
  - `GET /health` — quick environment + disclaimer payload. ([backend/app/routes/health.py](backend/app/routes/health.py))
- **Analysis / Screener**
  - `POST /analysis/full` — run the full analysis pipeline returning `FullAnalysisResponse`.
  - `POST /analysis/technical` — technical-only response.
  - `POST /analysis/news` — news-only analysis.
  - `POST /analysis/backtest` — backtest-only response.
  - `POST /analysis/final-recommendation` — final recommendation run path.
  - `POST /analysis/rankings` — return `RankingsResponse` for a given request.
  - `POST /analysis/screener/full` — run screener that shortlists top symbols and runs subsequent analysis on shortlist. (See [backend/app/routes/analysis.py](backend/app/routes/analysis.py) and orchestrator logic in [backend/app/agents/orchestrator_agent.py](backend/app/agents/orchestrator_agent.py)).
- **Stocks**
  - `POST /stocks/analyze` — wrapper to run a per-symbol analysis (delegates to `RouterAgent`).
- **Paper Trading**
  - `GET /paper-trading/dashboard` — returns `PaperTradingDashboardResponse`.
  - `GET /paper-trading/account` — alias for dashboard/account data.
  - `POST /paper-trading/account/reset` — reset paper account balances and wipe positions/trades.
  - `POST /paper-trading/orders` — place a paper order. Validation and simple fill logic implemented in `PaperTradingService`.
  - `POST /paper-trading/orders/{order_id}/cancel` — cancel a pending order.
  - `POST /paper-trading/positions/{position_id}/close` — close a paper position.
  - `PATCH /paper-trading/positions/{position_id}` — update position (stop/target/notes).
  - `POST /paper-trading/from-recommendation` — prefill ticket from recommendation.
  - `GET /paper-trading/symbols` and `GET /paper-trading/symbols/{symbol}/workspace` / `quote` endpoints for market data.

**4. Data contracts (Pydantic schemas)**
- `AnalysisRequest`, `ScreenerRequest`, `OHLCVPoint`, `TechnicalAnalysisResult`, `BacktestResult`, `FinalRecommendation`, `StockAnalysisResult`, `AnalysisResponse`, `FullAnalysisResponse`, `ScreenerResponse`, and the paper-trading types are defined under [backend/app/schemas](backend/app/schemas).
- Key constraints visible in code: `symbols` length (1..25) for analysis, screener `top_n` bounds, `PaperOrderCreateRequest` validations.

**5. AI agents and responsibilities**
- `OrchestratorAgent` — top-level conductor for full analysis, screener and persistency of results.
- `RouterAgent` — thin adapter exposing orchestrator flows to routes.
- `TechnicalAnalysisAgent` — wraps `TechnicalAnalysisService.analyze` (indicator generation + scoring).
- `BacktestAgent` — wraps backtest engine (`BacktestService.run`).
- `NewsAnalysisAgent` — fetches articles and produces sentiment (via `NewsService` and `SentimentService`).
- `RecommendationAgent` — aggregates signals, invokes `LLMService.build_reasoning`, and delegates to `RecommendationService.build` to produce `FinalRecommendation`.
- `RankingAgent` — ranks results via `RankingService`.

**6. Frontend features & user flows**
- **Scanner flow**: `App.tsx` drives running the screener (`runPresetScreener` in `frontend/src/api.ts`) → table of shortlisted names (`CandidateTable`) → inspect symbol (`StockDetailPanel`) → optionally send to Paper Trading.
- **Paper trading**: `PaperTradingPage` provides simulated order flow using endpoints in `/paper-trading`.
- **Local UX behavior**: scan history saved in `localStorage`; UI supports sample data toggle and fallback messaging when `data_warning` is present.

**7. Chatbot / conversational agents**
- No chat UI is present. LLM usage is limited to producing structured reasoning for recommendations; there is no conversational, multi-turn chat component in the frontend.

**8. Data storage design**
- Relational tables via SQLAlchemy declarative models include: `watched_stocks`, `analysis_history`, `backtest_history`, and paper trading tables (`paper_trading_accounts`, `paper_trading_positions`, `paper_trading_orders`, `paper_trading_trade_history`). DB initialization and session management are in [backend/app/db](backend/app/db).
- Default persistence target is derived from `Settings.database_url` and defaults to a local SQLite file.

**9. External integrations**
- **FYERS**: live quotes and candles via `FyersService` (fallback to generated mock candles when credentials are missing).
- **News provider**: `NewsService` uses a provider variable but will fall back to generated mock articles.
- **LLM**: `LLMService` is an abstraction with a provider path for Groq (used in code) and a fallback deterministic generator.

**10. Async vs sync**
- Most service implementations are synchronous. FastAPI endpoints are defined with standard `def` (not `async def`) and external calls use `requests`, making the API susceptible to blocking on external network or CPU-bound tasks.

**11. Observability**
- Logging is configured in [backend/app/utils/logger.py](backend/app/utils/logger.py) and used throughout services and agents; middleware logs request start/end and exceptions.

**12. Security notes**
- No authentication present — add as top priority for any public or semi-public deployment.

**13. Constraints and assumptions**
- The repository contains explicit mock fallbacks and developer conveniences. The specification above reflects only what exists in code; integration with cloud storage/managed DBs is not present and must be added separately.
