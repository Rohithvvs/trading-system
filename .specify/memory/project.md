# Trading System V2 - Project Memory

**Version:** 1.0  
**Status:** Verified Snapshot  
**Path:** `.specify/memory/project.md`

## 1. System Identity
- **What it is:** A single-user, personal algorithmic trading and paper-trading platform tailored for Indian equity markets (primarily NIFTY500).
- **What it does:** Automates market scanning, technical analysis, AI-assisted recommendations, backtesting, and paper trading.
- **What it is NOT:** A multi-tenant SaaS platform, a horizontally scaled public product, or a broker-side matching engine. Live trading is structurally present but not active as the primary workflow.

## 2. Tech Stack
- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Pydantic, APScheduler, Alembic.
- **Database:** PostgreSQL (primary source of truth), SQLite (ultra-fast tick/candle caching).
- **Frontend:** React 18, Vite, TypeScript, Vanilla CSS (with legacy TailwindCSS in isolated components).
- **Testing:** Pytest (Backend), Playwright (Frontend E2E), Jest/Vitest.
- **AI/LLM:** Groq (via LangChain / direct API wrappers).
- **Broker API:** FYERS API v3.

## 3. Folder Architecture
```text
backend/
├── alembic/             # PostgreSQL database migrations
├── app/
│   ├── agents/          # AI orchestration and LLM pipelines
│   ├── config/          # Environment variables and settings
│   ├── core/            # Logging, Async Task Supervisors, Gap Replay
│   ├── db/              # SQLAlchemy sessions and Redis locks
│   ├── models/          # Declarative ORM models (Postgres)
│   ├── observability/   # Metrics and Diagnostics
│   ├── routes/          # FastAPI HTTP endpoint controllers
│   ├── schemas/         # Pydantic DTOs for request/response validation
│   ├── services/        # Core business logic and external abstractions
│   └── utils/           # Financial math, symbols, generic utilities
├── data/                # Local SQLite cache databases (Gitignored)
└── tests/               # Consolidated Backend Test Suite (unit, integration, legacy)

frontend/
├── e2e/                 # Playwright E2E integration tests
├── src/
│   ├── api/             # HTTP fetch wrappers (fetchWithDiagnostics)
│   ├── components/      # React UI widgets and tables
│   ├── constants/       # Hardcoded tooltips and enumerations
│   ├── hooks/           # Custom React hooks for state and fetching
│   └── pages/           # High-level route views
└── tests/               # React component unit tests
```

## 4. Feature Inventory

| Feature | Status | Backend Entry | Frontend Entry | API Prefix | Key DB Tables |
|---------|--------|---------------|----------------|------------|---------------|
| **Paper Trading** | Implemented | `paper_trading_service.py` | `PaperTradingPage.tsx` | `/paper-trading` | `paper_trading_orders`, `paper_trading_positions` |
| **Market Screener** | Implemented | `screener_service.py` | `CandidateTable.tsx` | `/scanner` | `scan_snapshots` |
| **Tech Analysis** | Implemented | `technical_analysis_service.py` | `StockDetailPanel.tsx` | `/analysis` | `historical_candles` |
| **Market Engine** | Implemented | `market_engine_service.py` | `CentralCommand.tsx` | `/system` | `system_logs` |
| **LLM Recos** | Implemented | `llm_service.py` | `AllAnalyzedStocksTable.tsx`| `/analysis` | N/A |
| **Broker Auth** | Implemented | `token_service.py` | `TokenStatus.tsx` | `/token` | `fyers_tokens` |
| **Backtesting** | Implemented | `backtest_service.py` | N/A | `/backtest` | `analysis` |
| **Live Trading** | [UNVERIFIED] | `live_state_machine.py` | N/A | N/A | `live_trading_orders`, `live_trading_positions` |

## 5. Backend Services Map

**Trading Domain**
- `paper_trading_service.py`: Orchestrates paper portfolio mutations (orders, positions, capital).
- `margin_engine.py`: Calculates required margin and capital blockades for positions.
- `live_state_machine.py`: Enforces strict state transitions (PENDING -> OPEN -> CLOSED).
- `scan_execution_service.py`: Converts scan outputs into actionable trading tasks.

**Market Data Domain**
- `fyers_service.py`: Abstraction layer over the external FYERS broker API.
- `market_data_feed.py`: Manages WebSockets and tick ingestion.
- `market_data_service.py`: Centralized broker data fetcher.
- `candle_store.py` / `ohlcv_store.py`: Interacts with PostgreSQL and SQLite caching for timeseries data.
- `candle_reconciliation_service.py`: Fills gaps and ensures tick-to-candle consistency.

**Analysis & AI Domain**
- `screener_service.py`: Handles vectorization/pandas processing for the NIFTY500 universe.
- `technical_analysis_service.py`: Computes EMA, SMA, RSI, and MACD indicators.
- `sentiment_service.py`: Parses recent news data for macro sentiment.
- `llm_service.py`: Generic Groq/OpenAI wrapper.
- `ranking_service.py`: Scores candidates based on technical strength.
- `recommendation_service.py`: Converts raw analysis into a human-readable recommendation string.

**Infrastructure Domain**
- `lock_service.py`: Manages distributed Postgres/Redis advisory locks.
- `persistence_service.py`: Generic database save/commit abstractions.
- `retention_service.py`: Cleans up old ephemeral logs and system records.
- `token_service.py`: Stores, encrypts, and refreshes the FYERS OAuth tokens.

## 6. Agents Map (in `backend/app/agents`)
- `orchestrator_agent.py`: Top-level coordinator that calls all sub-agents sequentially.
- `router_agent.py`: Determines which analysis pipelines a stock requires based on basic thresholds.
- `technical_analysis_agent.py`: Translates raw technical indicators into LLM-friendly textual context.
- `fundamental_analysis_agent.py`: Wraps macro financial data (placeholder/scaffolded).
- `news_analysis_agent.py`: Determines sentiment from scraped/fed news.
- `ranking_agent.py`: Evaluates and ranks multiple analyzed stocks relative to each other.
- `recommendation_agent.py`: Drafts the final buy/sell/hold paragraph using Groq.
- `backtest_agent.py`: Orchestrates historical strategy evaluation.

## 7. API Route Map
- `/analysis` - Endpoint for running ad-hoc technical checks and LLM evaluations.
- `/fyers` - Raw FYERS proxy endpoints (mostly deprecated in favor of abstractions).
- `/health` - Liveness/Readiness probes for Docker and Load Balancers.
- `/logs` - Fetches and exposes backend logs for the frontend `SystemLogs.tsx`.
- `/paper-trading` - Complete CRUD for paper portfolio, orders, and positions.
- `/scanner` - Endpoints to trigger scans and retrieve the latest candidate snapshots.
- `/scheduler` - Endpoints to query APScheduler jobs.
- `/settings` - Manage persistent global application configurations.
- `/stocks` - Master symbol lists and universe fetching.
- `/system` - Market engine spin-up/spin-down and diagnostics.
- `/token` - FYERS OAuth callback and validation flows.
- `/workstation` - High-level aggregates for the Workstation UI.

## 8. Database Tables
- **`paper_trading_accounts`**: Stores available capital and total equity.
- **`paper_trading_positions`**: Active and historical asset holdings with computed PnL.
- **`paper_trading_orders`**: Immutable records of requested executions.
- **`fyers_tokens`**: Stores refresh and access tokens for broker auth.
- **`fyers_token_history`**: Audit trail of token refreshes and failures.
- **`historical_candles`**: Massive time-series table for 1m, 5m, 15m OHLCV data.
- **`scan_snapshots` & `scan_snapshot_records`**: Preserves full outputs of the market screener over time.
- **`idempotency_records`**: Protects against duplicate POST mutations.
- **`system_logs`**: Durable storage for application-level execution traces.

## 9. Scheduler Jobs
- `job_market_engine_spin_up`: Daily morning job to initialize the WS listener and cache. (Active)
- `job_market_engine_spin_down`: Daily evening job to disconnect WS and flush cache. (Active)
- `job_trigger_scans`: Interval job during market hours to run the screener. (Active)
- `job_token_refresh`: Pre-market token validity check. (Active)
- `nightly_candle_sync`: Historical backfill job. (**Orphaned / Debt**)

## 10. Background Workers
- **Market Data WebSocket Listener:** Holds an open connection to FYERS, mutating `candle_cache.db` constantly.
- **Scanner Background Worker:** Offloads heavy pandas CPU work to a ThreadPoolExecutor.
- **Reconciliation Task:** Async background loop comparing `PENDING` paper orders to the current cached LTPs to simulate fills.

## 11. Frontend Screens
- **`Dashboard.tsx`**: Main entry point; renders `ScannerProgress` and `CentralCommand`. (Legacy routing).
- **`PaperTradingPage.tsx`**: Primary trading interface. (Uses aggressive 1s and 10s polling for live data).
- **`WorkstationPage.tsx`**: Consolidated view of account summaries and logs.
- **`SystemLogs.tsx`**: Renders database system logs and diagnostics.

## 12. Known Technical Debt
1. **App.tsx / Dashboard.tsx Duplication:** The application shell and routing logic are duplicated across these two files.
2. **PaperTradingPage Polling:** The paper trading UI relies on aggressive 1-second (quotes) and 10-second (status) HTTP polling instead of WebSockets.
3. **CentralCommand Tailwind Usage:** Tailwind CSS is used ad-hoc inside `CentralCommand.tsx`, violating the project's Vanilla CSS standard.
4. **Orphaned nightly_candle_sync:** This APScheduler job exists but is disconnected/failing, requiring manual backfills.
5. **window.alert Usage:** `window.alert()` and `window.prompt()` exist in legacy components instead of proper toast notifications.
6. **Missing Authentication:** The API is unauthenticated globally, relying on single-user deployment isolation.

## 13. External Integrations
- **FYERS API:** Primary real-time market data (WebSocket) and historical data (REST) broker.
- **Groq:** High-speed LLM inference for technical recommendations.
- **PostgreSQL:** Primary durable relational store.
- **SQLite:** Ephemeral, high-throughput memory-mapped cache for the market engine (`candle_cache.db`).
