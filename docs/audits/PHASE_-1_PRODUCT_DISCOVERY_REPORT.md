# PHASE -1.1 — PRODUCT DISCOVERY REPORT

## 1. Product Overview

- **What is this application?** 
  It is a comprehensive automated trading and market analysis system. It features a robust paper trading environment, real-time market data ingestion via WebSockets, algorithmic stock screening, technical analysis generation, and an AI-backed recommendation engine.
- **What business problem does it solve?** 
  It enables algorithmic and discretionary traders to scan broad market universes (e.g., NIFTY 500) for trading setups, track technical indicators in real-time, execute simulated trades (paper trading) to test strategies without financial risk, and monitor portfolio performance.
- **Who is the intended user?** 
  Algorithmic traders, quantitative analysts, and active swing/day traders.
- **Primary goals.** 
  Provide automated background market scanning, accurate risk-free paper trading against live data, AI-driven stock recommendations, and real-time tracking of portfolio PnL.
- **Supported workflows.** 
  Market scanning and filtering, watchlist monitoring, receiving AI-generated recommendations, placing/managing paper trades, backtesting strategies, and real-time dashboard tracking.

---

## 2. Major Features

| Feature Name | Purpose | Current Status | Main Modules | Dependencies | Main Screens | APIs | Database Tables | Business Rules |
|---|---|---|---|---|---|---|---|---|
| **Paper Trading** | Simulate real trading with virtual capital | Implemented | `paper_trading_service.py` | Market Data Service | Paper Trading Page, Dashboard | `/paper-trading/*` | `paper_trading_accounts`, `paper_trading_positions`, `paper_trading_orders` | Checks buying power, uses real-time FYERS quotes for execution. |
| **Market Scanner** | Filter universe based on TA rules | Implemented | `screener_service.py`, `scan_execution_service.py` | Technical Analysis | Scanner Progress, Candidate Table | `/scanner/*` | `scanned_candidates`, `scan_snapshots` | Runs on NIFTY500, caches results, matches predefined technical patterns. |
| **Technical Analysis** | Calculate indicators (RSI, MACD, SMA) | Implemented | `technical_analysis_service.py` | Candle Store | Stock Detail Panel | `/analysis/*` | `historical_candles` | Uses historical OHLCV to compute indicators on the fly. |
| **Market Data Ingestion** | Fetch real-time ticks and history | Implemented | `market_data_service.py`, `fyers_service.py` | FYERS API | Central Command, Dashboard | `/fyers/*` | `historical_candles` | Listens to FYERS WS, normalizes data, caches in SQLite/Redis. |
| **AI Recommendations** | Generate trade ideas via LLM | Implemented | `recommendation_service.py`, `llm_service.py` | OpenAI/LLM API | Candidate Table | `/analysis/recommend` | `analysis_history` | Scores scanner candidates using LLM prompts. |
| **Backtesting Engine** | Test strategies against history | Implemented | `backtest_service.py` | Market Data | Workstation Page | `/backtest/*` | `backtest_history` | Replays historical candles against strategy logic, calculates CAGR/Drawdown. |

---

## 3. User Workflows

- **Scanner Flow:** The system runs a background scan or the user initiates one -> The Screener Service fetches market data -> Applies technical filters (e.g., RSI > 60) -> Stores results in `scan_snapshots` and `scanned_candidates` -> Frontend displays matches in the Candidate Table.
- **Recommendation Flow:** Scanner identifies a candidate -> Analytics Service packages the technical data -> Sends prompt to LLM Service -> LLM returns a confidence score and reasoning -> System saves to `analysis_history` -> Displayed as a "Recommended" signal.
- **Paper Trading Flow:** User submits a Buy order (Limit/Market) -> API logs idempotency key -> Paper Trading Service validates available capital -> Deducts reserved cash -> Fetches real-time price -> If Market order, fills immediately and creates a Position; if Limit, queues for reconciliation -> Updates `paper_trading_positions` and logs to `paper_trading_execution_events`.
- **Trade Closing (Square Off):** User clicks "Close Position" -> Service calculates required opposing order -> Executes at current market price -> Calculates realized PnL -> Moves position to CLOSED state -> Adds funds back to available capital.
- **Market Data Ticking:** Market Engine Session starts -> Authenticates with FYERS -> Opens WebSocket connection -> Receives real-time ticks -> Caches latest prices in `candle_cache.db` -> Broadcasts via WebSockets to the React frontend.
- **Reconciliation:** A background worker loops over pending limit/stop orders -> Compares limit price against the latest cached market price -> If condition met, executes the order and transitions state from PENDING to FILLED.

---

## 4. Screens

- **Dashboard (`Dashboard.tsx`, `DashboardHeader.tsx`)**
  - *Purpose:* High-level summary of account health and daily performance.
  - *Components:* PnL widgets, Market Status badge, Capital overview.
  - *Displayed Data:* Total capital, daily PnL, market open/close status.
- **Paper Trading Page (`PaperTradingPage.tsx`)**
  - *Purpose:* Manage simulated trades and portfolio.
  - *Components:* Order entry form, Positions table, Pending orders table, Trade history.
  - *API Calls:* `GET /paper-trading/positions`, `POST /paper-trading/orders`.
- **Workstation Page (`WorkstationPage.tsx`, `CentralCommand.tsx`)**
  - *Purpose:* Core terminal for controlling the engine and analyzing specific assets.
  - *Components:* Infrastructure Status, System control toggles.
- **Scanner Results (`CandidateTable.tsx`, `AllAnalyzedStocksTable.tsx`, `ScannerProgress.tsx`)**
  - *Purpose:* Display the output of the automated market screener.
  - *Components:* Data grids with technical scores, AI confidence meters.
- **Stock Detail Panel (`StockDetailPanel.tsx`)**
  - *Purpose:* Deep dive into a single instrument.
  - *Displayed Data:* OHLCV charts, current indicator values (RSI, MACD).
- **System Logs & Notifications (`SystemLogs.tsx`, `NotificationBell.tsx`)**
  - *Purpose:* Real-time visibility into backend events and alerts.

---

## 5. Backend Modules

- **`paper_trading_service.py`**: Manages mock portfolios, order validation, PnL calculations, and idempotency checks.
- **`screener_service.py` & `scan_execution_service.py`**: Handles filtering universes, evaluating technical constraints, and persisting scan snapshots.
- **`technical_analysis_service.py`**: Responsible for calculating mathematical indicators (SMA, EMA, RSI, MACD) on timeseries data.
- **`market_engine_service.py`**: Orchestrates the background lifecycle, starting/stopping loops, handling market hours, and triggering scheduled scans.
- **`market_data_service.py` & `candle_store.py`**: Interfaces with internal DB and caches to serve historical and live OHLCV data.
- **`fyers_service.py` & `token_service.py`**: External adapter for communicating with the FYERS API and managing OAuth tokens.
- **`analytics_service.py` & `llm_service.py`**: Integrates with external LLMs to score trade setups.
- **`candle_reconciliation_service.py`**: Ensures historical data integrity and fills missing gaps.
- **`backtest_service.py`**: Runs simulation loops over historical data arrays to evaluate strategy performance.

---

## 6. Database Overview

- **`live_accounts` / `paper_trading_accounts`**
  - *Purpose:* Stores base currency, available cash, and total equity.
  - *Relationships:* Parent to positions and orders.
- **`live_positions` / `paper_trading_positions`**
  - *Purpose:* Tracks active/closed holdings, average entry price, and realized/unrealized PnL.
  - *Relationships:* Belongs to an account.
- **`live_orders` / `paper_trading_orders`**
  - *Purpose:* The source of truth for all placed orders (status, qty, price, idempotency key).
  - *Relationships:* Belongs to an account.
- **`paper_trading_execution_events`**
  - *Purpose:* Append-only ledger of state transitions for auditing.
- **`historical_candles`**
  - *Purpose:* Primary timeseries storage for OHLCV data.
  - *Primary Key:* `id` (Unique composite on symbol, resolution, timestamp).
- **`scan_snapshots` & `scan_snapshot_records`**
  - *Purpose:* Preserves full historical point-in-time outputs of the market screener.
- **`fyers_tokens`**
  - *Purpose:* Stores active and refresh tokens for broker authentication.
- **`idempotency_records`**
  - *Purpose:* Prevents duplicate order submissions.

---

## 7. API Inventory

*Note: Grouped by the Paper Trading feature as an example of verified implementation.*

**Paper Trading**
- `GET /paper-trading/dashboard` - Fetches high-level account and positions summary.
- `GET /paper-trading/account/summary` - Returns compact account metrics (Capital, PnL).
- `POST /paper-trading/account/reset` - Resets the paper trading account balance to default.
- `PUT /paper-trading/account/capital` - Updates the starting capital amount.
- `POST /paper-trading/orders` - Places a new paper order (requires Idempotency-Key).
- `GET /paper-trading/orders/pending` - Lists unfilled orders.
- `GET /paper-trading/orders/history` - Lists past orders.
- `PUT /paper-trading/orders/{order_id}` - Modifies a pending order.
- `DELETE /paper-trading/orders/{order_id}` - Cancels a pending order.
- `GET /paper-trading/positions` - Retrieves active positions.
- `POST /paper-trading/positions/squareoff-all` - Market sells all open positions.
- `POST /paper-trading/positions/{position_id}/close` - Closes a specific position.
- `GET /paper-trading/trades` - Lists completed trade history.

**Market Engine & Core**
- `POST /paper-trading/engine/start` - Starts the background market engine.
- `POST /paper-trading/engine/stop` - Stops the background engine.
- `GET /paper-trading/engine/status` - Checks engine health and active connections.
- `POST /paper-trading/engine/heartbeat` - Automated trigger from cron to keep engine alive and trigger scheduled scans.

---

## 8. Background Processes

- **Scanner Background Worker:** Scheduled via heartbeat pings (e.g., morning 9:00 AM baseline scan, and 30-minute intervals). Orchestrates heavy pandas dataframe operations in a dedicated ThreadPoolExecutor.
- **Market Data WebSocket Listener:** Maintains an active WSS connection to FYERS, processing ticks, updating `candle_cache.db`, and pushing events to the frontend via Redis Pub/Sub or direct WS.
- **Reconciliation Task:** A polling loop/state machine that continually checks `PENDING` orders against the latest cached market prices to simulate limit/stop order execution.
- **Data Backfill Jobs:** Scheduled tasks to pull missing EOD candles from the broker into `historical_candles`.

---

## 9. External Integrations

- **FYERS API:** Primary broker integration for historical data fetching, real-time WebSockets (quotes), and potentially live trading execution.
- **PostgreSQL:** Primary relational database storing accounts, orders, positions, and analysis history.
- **Redis (Assumed/Supported):** Used for Pub/Sub WebSocket broadcasting and fast key-value caching.
- **SQLite (`candle_cache.db`):** Used as an ultra-fast, local memory-mapped cache for real-time OHLCV aggregation.
- **OpenAI / LLM APIs:** Used by the `llm_service` to generate natural language reasoning and confidence scores for trade recommendations.

---

## 10. Folder Architecture

- **`backend/`**: Contains the FastAPI Python backend.
  - **`app/`**: Main application source.
    - **`routes/`**: FastAPI endpoint controllers.
    - **`services/`**: Core business logic separating concerns from HTTP.
    - **`models/`**: SQLAlchemy declarative base models matching DB tables.
    - **`schemas/`**: Pydantic models for request/response validation.
  - **`alembic/`**: Database migration scripts and versions.
- **`frontend/`**: React application built with Vite and TypeScript.
  - **`src/pages/`**: Top-level route views (Dashboard, PaperTrading).
  - **`src/components/`**: Reusable UI widgets (CandidateTable, NotificationBell).
- **`docs/`**: Markdown documentation, architecture diagrams, and schema exports.
- **`scripts/` & `tools/`**: Utility python files for schema extraction, DB resetting, and auditing.

---

## 11. Current Architecture

The system utilizes a modern, decoupled architecture:
1. **Frontend:** A React SPA (Single Page Application) built with Vite, TypeScript, and TailwindCSS, managing state and data fetching (likely via React Query or Axios), and listening to WebSockets for real-time updates.
2. **API Gateway / Backend:** A FastAPI Python server handling RESTful requests, validating schemas via Pydantic, and managing idempotency.
3. **Service Layer:** Fat service layer containing domain logic (Paper Trading, Screener, Technical Analysis), isolating the database from the API routers.
4. **Data Persistence:** 
   - **Primary DB:** PostgreSQL for relational integrity (Users, Orders, Positions).
   - **Fast Cache:** SQLite/Redis for high-throughput market tick caching.
5. **Background Workers:** In-process threads (ThreadPoolExecutor) and asyncio event loops managing market data ingestion and scheduled scanning without blocking API threads.

*(Not verified from repository if Kubernetes or external load balancers are actively used in production, though diagrams suggest it as a deployment model).*

---

## 12. Feature Inventory Table

| Feature | Backend | Frontend | Database | Scheduler | API | Status |
|---|---|---|---|---|---|---|
| **Paper Trading** | `paper_trading_service.py` | `PaperTradingPage.tsx` | `paper_trading_*` tables | Background Reconciliation | `/paper-trading/*` | Implemented |
| **Market Screener** | `screener_service.py` | `CandidateTable.tsx` | `scanned_candidates` | 30-min heartbeat interval | `/scanner/*` | Implemented |
| **Tech Analysis** | `technical_analysis_service.py` | `StockDetailPanel.tsx` | `historical_candles` | On-Demand | `/analysis/*` | Implemented |
| **Market Engine** | `market_engine_service.py` | `CentralCommand.tsx` | `market_engine_sessions` | Continuous WS Loop | `/engine/*` | Implemented |
| **LLM Recos** | `llm_service.py` | `AllAnalyzedStocksTable.tsx`| `analysis_history` | Triggered post-scan | `/analysis/recommend` | Implemented |
| **Broker Auth** | `token_service.py` | `TokenStatus.tsx` | `fyers_tokens` | Daily Refresh | `/token/*` | Implemented |
| **Backtesting** | `backtest_service.py` | (Not explicitly found in components) | `backtest_history` | On-Demand | `/backtest/*` | Backend Implemented |
| **Live Trading** | `live_trading.py` (Models) | (Not explicitly found in components) | `live_*` tables | N/A | N/A | Schema Implemented |
