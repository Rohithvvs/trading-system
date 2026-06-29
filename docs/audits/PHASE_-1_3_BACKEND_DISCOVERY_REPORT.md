# Trading System Core Workflows & Architecture

## 1. Schedulers & Background Workers

### APScheduler Jobs (`main.py`)
The system binds a distributed cron-like scheduler using `AsyncIOScheduler`. Scheduled tasks will only execute if the `singleton-workers` PostgreSQL advisory lease is acquired, ensuring only one instance in a cluster runs them.

- **`job_market_engine_spin_up`**: Mon-Fri 08:55. Triggers `MarketEngineService.request_start()`.
- **`job_intraday_heartbeat`**: Runs at multiple intervals between 09:15 and 15:30. Triggers `MarketEngineService.heartbeat()`.
- **`job_market_engine_cool_down`**: Mon-Fri 15:30. Triggers `MarketEngineService.request_stop()`.
- **`track_strategy_drift_job`**: Fri 16:00. Analyzes performance and detects strategy drift via `AnalyticsService`.
- **`job_retention_cleanup`**: Daily 02:15. Sweeps and deletes old retained records from the database.
- **`automated_screening_job`**: (Currently disabled in `main.py` but executable via API). Pre-market deep scan triggered via `OrchestratorAgent`.
- **`nightly_candle_sync`**: Defined as an async batch process for 1D candle cache refresh, but currently orphaned (not attached to an active `add_job` trigger).

### Background Workers
- **Market Engine Loop** (`market-engine-loop`): Long-running task started during Fastapi `lifespan`. Manages Market Engine state machine (starting, paused, waiting for market open), re-connects WebSockets, and polls missing prices.
- **Reconciliation Loop** (`market-reconciliation-loop`): Runs every 5 minutes within Market Engine. Sweeps open paper positions checking for unresolved gaps.
- **Legacy Alert Monitor** (`legacy-alert-monitor`): Spawned via `TaskSupervisor`. A 5-second tick loop that monitors legacy target prices for alerts on active lists, pushing notifications.
- **Scan Execution Task** (`ScanExecutionService._run_scan_task`): Ephemeral background task spun up via the `/scheduler/run-scanner` API endpoint. Handles long-running Orchestrator operations concurrently while preventing duplicates.

---

## 2. Complete Execution Workflows

### Scanner
- **Trigger**: Called manually via UI or cron-triggered via `/scheduler/run-scanner`.
- **Initialization**: Acquires a distributed lock (`DistributedLockService`) to enforce single-run semantics. A placeholder `ScanSnapshot` is created in DB.
- **Execution**: `RouterAgent.screener_full` determines technical scores and matches. Process uses a `progress_queue` to emit SSE status updates (if initiated via UI).
- **Completion**: Updates the `ScanSnapshot` status, saves snapshot locally, and unlocks.

### Market Engine
- **Lifecycle**: Automatically switches between `RUNNING` and `WAITING_MARKET_OPEN` based on IST exchange hours (09:15 to 15:30) in `_reconcile_session`. Handles `TOKEN_EXPIRED_PAUSED` degradations.
- **Tick Processing**: Websocket callbacks hit `_on_tick`. Order evaluation is wrapped in a DB transaction with `FOR UPDATE SKIP LOCKED`.
  - Pending orders hitting LTP trigger entry fills (`ENTRY_FILLED`).
  - Open positions hitting target or stop-loss trigger `auto_exit()`.

### Reconciliation
- **Purpose**: Recovers missed exits during websocket disconnections, provider lag, or server crashes.
- **Workflow**: Sweeps `OPEN` positions every 5 minutes. Calculates the time gap since the last evaluated timestamp. Pulls exact 1-minute historical OHLCV data from FYERS and locally replays the gap sequence.
- **Resolution**: If a 1-minute candle breaches target/stop-loss, it triggers a retroactive exit and records an `ExecutionEvent`.

### Paper Trading
- **Creation**: Orders are lodged via `PaperTradingService` as `PENDING`.
- **Mutation limits**: Synchronous DB wrappers (`db.run_sync()`) are strictly used when altering account margin balances and logging events to isolate threading limits. Includes dedupe keys (e.g., `exit-filled:123:TARGET_HIT`) for idempotency.

### Market Data
- **Live Feed**: `FyersMarketDataFeed` connects to the websocket.
- **Polling Fallback**: `_poll_missing_prices` fetches prices over REST for desired symbols not receiving live ticks.
- **Offline Gap Replay**: A one-off script `run_gap_replay` runs during application boot phase to align historical discrepancies before the live engine attaches.

### Notifications
- Dispatched via `PaperTradingService.add_notification()`. Errors (like token missing/expired) or fill events (entry/exit) append directly to the notification DB tables to alert the UI synchronously.

### Backtesting
- Executed on-the-fly via `BacktestService.run()`.
- Calculates technical indicators (MACD, RSI, EMA) using `pandas` and `ta`.
- Analyzes entry/exit criteria generating simulated `pnl_percent`. Outputs trade history, Win Rate, Profit Factor, Sharpe Ratio, and Equity Curve points.

### AI Analysis
- Proxied via `LLMService` leveraging Groq (or fallback).
- **Reasoning**: Ingests TA and backtest variables, outputting formatted JSON advice (Bullets, Risk Factors, Invalidation Signals).
- **Sentiment**: Scores headlines via custom quantifiable mapping limits between -1.0 (Highly Bearish) and +1.0 (Highly Bullish).

---

## 3. Architecture Context

### Startup
FastAPI lifespan (`main.py`) performs sequential bootstrap:
1. Tunes AnyIO limits (`limiter.total_tokens = 100`).
2. Checks Alebmic DB Lineage (`check_alembic_head`).
3. Acquires PostgreSQL Singleton lock.
4. Executes offline Gap Replay (`run_gap_replay`).
5. Bootstraps schedulers and async loops (Market Engine & Supervisor).

### Shutdown
Lifespan closure safely executes:
1. `scheduler.shutdown()` (halts cron triggers).
2. `market_engine.shutdown()` (halts websocket and loops).
3. `task_supervisor.shutdown()` (cancels legacy background runners).
4. `server_state` shutdown time log (used to detect crash vs clean reboot).

### Dependency Injection
Core dependencies rely heavily on SQLAlchemy `AsyncSession` provided primarily by `Depends(get_db)` in Fastapi routes. For background workers out of route context, `AsyncSessionLocal` is used inside explicit async context managers.

### Async Boundaries
- Event Loop drives I/O: Websockets, FYERS REST calls.
- CPU/Synchronous DB isolation: Pandas intensive ops (Backtests) and specific atomic DB operations using `db.run_sync()` or `asyncio.to_thread()`.

### Locks
- **PostgreSQL Advisory**: `acquire_singleton_lease` used system-wide for single worker pod allocation.
- **Row-level (FOR UPDATE SKIP LOCKED)**: Prevent race conditions across parallel ticks inside Market Engine evaluating the same `PaperPosition`.
- **DistributedLocks**: Custom `DistributedLockService` avoids duplicate Scanner execution collisions across Cron / UI calls.

### Retries & Idempotency
- System degrades gracefully to `ERROR_RETRYING` internally in Market Engine during disconnections, auto-recovering on next loop.
- `ExecutionEvent` ensures idempotency utilizing unique hash/identifiers in `dedupe_key` column avoiding multiple executions of the same trigger.

### Caching
- `candle_store.py` manages local OHLC data. 
- Fast memory references are maintained for real-time routing (`_active_positions_cache` and `latest_ltp` dicts).

### Observability
- Event logging mapped to `EVENT_JOB_EXECUTED` for APScheduler diagnostics.
- Advanced diagnostic trackers (`scan_diagnostics.py`) log application state, DB pool size, token age, process duration, memory heap changes (via `psutil`), and outputs rich JSON environments.

### Transactions
Leverages `async with db.begin()` to enforce commit atomicity across execution lifecycle state mutations and notification logging. Rollbacks execute on unhandled exceptions protecting portfolio states.
# API Routes Analysis

This document details all routes defined in `backend/app/routes` along with their associated schemas, logic, and metrics.

## 1. Health (`health.py`)

### `GET /health`
- **Purpose**: Basic health check for the application.
- **HTTP Method**: GET
- **URL**: `/health`
- **Authentication**: None
- **Input DTO**: None
- **Output DTO**: `HealthResponse` (status, environment, disclaimer)
- **Validation**: None
- **Business Rules**: Returns the environment variable and a disclaimer advisory.
- **Services Called**: None
- **Database Writes**: None
- **Database Reads**: None
- **External APIs**: None
- **Exceptions**: None
- **Failure Responses**: None
- **Logging**: None
- **Metrics**: None

### `GET /health/heartbeat`
- **Purpose**: Check market engine heartbeat.
- **HTTP Method**: GET
- **URL**: `/health/heartbeat`
- **Authentication**: None
- **Input DTO**: None
- **Output DTO**: JSON containing status and engine status.
- **Validation**: None
- **Business Rules**: Checks the health of the `market_engine`.
- **Services Called**: `market_engine.heartbeat()`, `market_engine.status()`
- **Database Writes**: None
- **Database Reads**: None
- **External APIs**: None
- **Exceptions**: None
- **Failure Responses**: None
- **Logging**: None
- **Metrics**: None

## 2. Stocks (`stocks.py`)

### `POST /stocks/analyze`
- **Purpose**: Delegate stock analysis to the RouterAgent.
- **HTTP Method**: POST
- **URL**: `/stocks/analyze`
- **Authentication**: None explicitly defined.
- **Input DTO**: `AnalysisRequest` (symbols, mode, timeframe)
- **Output DTO**: `AnalysisResponse`
- **Validation**: Pydantic validation (requires at least 1 symbol).
- **Business Rules**: Defers analysis to the `RouterAgent`.
- **Services Called**: `RouterAgent.analyze_stocks`
- **Database Writes**: Handled in Agent.
- **Database Reads**: Handled in Agent.
- **External APIs**: Handled in Agent.
- **Exceptions**: Unhandled directly here.
- **Failure Responses**: standard 422 on validation failure.
- **Logging**: None.
- **Metrics**: None.

## 3. Fyers (`fyers.py`)

### `POST /fyers/token`
- **Purpose**: Save a new FYERS access token.
- **HTTP Method**: POST
- **URL**: `/fyers/token`
- **Authentication**: None
- **Input DTO**: `FyersTokenCreate`
- **Output DTO**: Dict with status, message, and token_id.
- **Validation**: Pydantic fields.
- **Business Rules**: Deactivates any existing tokens and saves the new one.
- **Services Called**: `token_service.save_access_token`
- **Database Writes**: Inserts/updates `FyersToken`.
- **Database Reads**: Checks existing tokens.
- **External APIs**: None.
- **Exceptions**: Raises HTTP 500 on failure.
- **Failure Responses**: 500 Internal Server Error.
- **Logging**: Logs error if token save fails.
- **Metrics**: None.

### `GET /fyers/token/status`
- **Purpose**: Check the status of the active FYERS token.
- **HTTP Method**: GET
- **URL**: `/fyers/token/status`
- **Authentication**: None
- **Input DTO**: None
- **Output DTO**: JSON `{"has_token": bool, "created_at": str, "expires_at": str, "is_active": bool}`
- **Validation**: None
- **Business Rules**: Selects the active token from the database.
- **Services Called**: None
- **Database Writes**: None
- **Database Reads**: `FyersToken` table.
- **External APIs**: None
- **Exceptions**: Raises HTTP 500 on DB failure.
- **Failure Responses**: 500 Internal Server Error.
- **Logging**: Logs exception on failure.
- **Metrics**: None.

### `DELETE /fyers/token`
- **Purpose**: Clear all active FYERS tokens.
- **HTTP Method**: DELETE
- **URL**: `/fyers/token`
- **Authentication**: None
- **Input DTO**: None
- **Output DTO**: JSON with success message.
- **Validation**: None
- **Business Rules**: Updates all tokens to `is_active=False`.
- **Services Called**: None
- **Database Writes**: Updates `FyersToken` table.
- **Database Reads**: None
- **External APIs**: None
- **Exceptions**: Raises HTTP 500 on failure and rolls back DB.
- **Failure Responses**: 500 Internal Server Error.
- **Logging**: Logs exception on failure.
- **Metrics**: None.

## 4. Scanner (`scanner.py`)

### `GET /scanner/latest`
- **Purpose**: Fetch the latest completed scan results for the dashboard.
- **HTTP Method**: GET
- **URL**: `/scanner/latest`
- **Authentication**: None
- **Input DTO**: None
- **Output DTO**: JSON scan results.
- **Validation**: None
- **Business Rules**: Returns the latest scan; if none found, returns empty candidate arrays.
- **Services Called**: `LatestScanService.get_latest_completed_scan`, `diagnostics.record_dashboard_snapshot`
- **Database Writes**: None
- **Database Reads**: via `LatestScanService`.
- **External APIs**: None
- **Exceptions**: Unhandled exceptions fallback to FastAPI 500.
- **Failure Responses**: Returns `{"message": "No completed scans found", ...}` if not found.
- **Logging**: `log_dashboard_request` to log metrics.
- **Metrics**: Records response time, returned records, query duration, snapshot_id.

## 5. System (`system.py`)

### `GET /system/shadow-run/status`
- **Purpose**: Get the shadow run diagnostic status.
- **HTTP Method**: GET
- **URL**: `/system/shadow-run/status`
- **Authentication**: None
- **Input DTO**: None
- **Output DTO**: JSON
- **Validation**: None
- **Business Rules**: Gathers metrics from diagnostics service.
- **Services Called**: `diagnostics.get_db_health`, `diagnostics.get_memory_metrics`
- **Database Writes**: None
- **Database Reads**: `get_db_health` queries DB.
- **External APIs**: None
- **Exceptions**: Unhandled.
- **Failure Responses**: Unhandled.
- **Logging**: None
- **Metrics**: Gathers detailed memory and run metrics.

### `GET /system/shadow-run/report`
- **Purpose**: Generate shadow run report.
- **HTTP Method**: GET
- **URL**: `/system/shadow-run/report`
- **Authentication**: None
- **Input DTO**: None
- **Output DTO**: JSON report.
- **Validation**: None
- **Business Rules**: Defers to `diagnostics.get_shadow_run_report(db)`.
- **Services Called**: `diagnostics.get_shadow_run_report`
- **Database Writes**: None
- **Database Reads**: via service.
- **External APIs**: None
- **Exceptions**: None.
- **Failure Responses**: None.
- **Logging**: None.
- **Metrics**: Detailed metric report.

### `GET /system/shadow-run/health/ready`
- **Purpose**: Check readiness of subsystems (DB, scheduler, snapshot, fyers token).
- **HTTP Method**: GET
- **URL**: `/system/shadow-run/health/ready`
- **Authentication**: None
- **Input DTO**: None
- **Output DTO**: JSON dict `{"ready": bool, "checks": dict}`.
- **Validation**: None
- **Business Rules**: Executes checks to ensure app components are functional.
- **Services Called**: `get_current_access_token`
- **Database Writes**: None
- **Database Reads**: Executes direct checks `SELECT 1`.
- **External APIs**: None
- **Exceptions**: Caught silently, marks check as `False`.
- **Failure Responses**: Returns `ready: False` in payload.
- **Logging**: None
- **Metrics**: None

## 6. Workstation (`workstation.py`)

Provides endpoints delegating to `WorkstationService`:
- `GET /workstation/universes`: Lists universes.
- `GET /workstation/market-overview`: Returns `MarketOverviewResponse`.
- `GET /workstation/saved-scans`: Lists saved scans.
- `POST /workstation/saved-scans`: Creates a saved scan (Input: `SavedScanCreate`).
- `DELETE /workstation/saved-scans/{scan_id}`: Deletes a scan.
- `GET /workstation/scan-history`: Returns scan history items.
- `GET /workstation/scan-history/{scan_id}/compare`: Compares scans (Output: `ScanComparisonResponse`, raises 404 on ValueError).
- `GET /workstation/alerts`: Lists workstation alerts.
- `POST /workstation/alerts`: Creates an alert (Input: `AlertCreate`, raises 400 on ValueError).
- `DELETE /workstation/alerts/{alert_id}`: Deletes an alert.
- `GET /workstation/risk-settings`: Returns risk settings.
- `PUT /workstation/risk-settings`: Updates risk settings (Input: `RiskSettingsRequest`).
- `GET /workstation/api-health`: Returns health state (Output: `ApiHealthResponse`).
- **Services Called**: `WorkstationService` methods.
- **Database Access**: Handled inside `WorkstationService`.
- **Exceptions**: Catches `ValueError` and raises 400/404 HTTPExceptions.

## 7. Analysis (`analysis.py`)

### Analysis Trigger Endpoints:
`/analysis/technical`, `/analysis/news`, `/analysis/backtest`, `/analysis/final-recommendation`, `/analysis/full`, `/analysis/rankings`
- **Purpose**: Provides various stock analysis layers.
- **HTTP Method**: POST
- **Authentication**: None explicitly.
- **Input DTO**: `AnalysisRequest`
- **Output DTO**: `AnalysisResponse` / `FullAnalysisResponse` / `RankingsResponse`
- **Business Rules**: Calls respective methods on `RouterAgent`.
- **Services Called**: `RouterAgent` methods.
- **Exceptions**: Handled mostly via agent exceptions.
- **Logging**: Logs API entry/exit for full analysis.

### `POST /analysis/screener/full`
- **Purpose**: Execute a full screener scan.
- **Input DTO**: `ScreenerRequest`
- **Output DTO**: Server-Sent Events (SSE) `StreamingResponse`
- **Services Called**: `ScanExecutionService.execute_scan`
- **Exceptions**: Catches `LockAcquisitionError` and returns 409 Conflict if scan already in progress.
- **Logging**: Logs entry parameters.

### `GET /analysis/symbol/{symbol}/detail`
- **Purpose**: Detail view for a specific symbol.
- **Output**: JSON payload with technical, backtest, news, company details.
- **Services Called**: `RouterAgent.full_analysis`, `MarketInfoService.get_company_profile`, `FyersService.fetch_quote_profile`.
- **Exceptions**: Detailed error mapping for Fyers errors (`FyersAuthExpiredError` -> 401, `FyersRateLimitError` -> 429, etc.).
- **Failure Responses**: JSON error payloads matching Fyers issues.

### `GET /analysis/scan/latest`, `GET /analysis/candidates/today`
- **Purpose**: Retrieves recent scan results/candidates directly from DB or store.

## 8. Paper Trading (`paper_trading.py`)

Extensive wrapper around `PaperTradingService` and `market_engine`:
- **Dashboard/Account**: `/paper-trading/dashboard`, `/paper-trading/account`, `/paper-trading/account/summary`.
- **Orders**: `POST /paper-trading/orders` (Requires idempotency key), `GET /paper-trading/orders/pending`, `GET /paper-trading/orders/history`, `PUT /paper-trading/orders/{order_id}`, `DELETE /paper-trading/orders/{order_id}`, `POST /paper-trading/orders/{order_id}/cancel`.
- **Positions**: `GET /paper-trading/positions`, `POST /paper-trading/positions/squareoff-all`, `POST /paper-trading/positions/{position_id}/close`, `PATCH /paper-trading/positions/{position_id}`.
- **Trades/Analytics**: `GET /paper-trading/trades`, `GET /paper-trading/analytics`.
- **Market Engine Control**: `/paper-trading/engine/start`, `/paper-trading/engine/stop`, `/paper-trading/engine/status`, `/paper-trading/engine/heartbeat` (Includes logic for automated background scanning).
- **Other endpoints**: Symbols, Workspace, Quotes, Notifications, Alerts, Transactions.
- **Input/Output DTOs**: defined in `app/schemas/paper_trading.py` (`PaperOrderCreateRequest`, `PaperOrderResponse`, `PaperPositionResponse`, etc.)
- **Validation**: Strict validation (Idempotency keys, symbol canonicalization).
- **Exceptions**: Catches `ValueError` and converts to 400/404 HTTPExceptions.

## 9. Scheduler (`scheduler.py`)

- **Endpoints**: `GET /scheduler/run-scanner`, `POST /scheduler/daily-scan`, `GET /scheduler/status`.
- **Purpose**: Endpoints to trigger automated background jobs.
- **Authentication**: Validates against `CRON_SECRET` or `X-Scheduler-Secret` headers/query params. Raises 403/401 on failure.
- **Business Rules**: Uses `ScanExecutionService.execute_scan`.
- **Exceptions**: Returns 409 (run-scanner) or 202 (daily-scan) if a lock is currently acquired (`LockAcquisitionError`). Logs full stack trace on unexpected failures.

## Schemas Analysis
Schemas in `app/schemas` define strict Pydantic models for validation:
- `health.py`: Health response models.
- `fyers_token.py`: Models for token creation and response.
- `analysis.py`: Enum `AnalysisMode`, request models like `AnalysisRequest`, `ScreenerRequest`, and highly detailed output models.
- `workstation.py`: Models for user workstations, scanning UI requests, alerts, risk settings, etc.
- `paper_trading.py`: Huge list of models managing paper trading, orders, positions, capital update limits, analytics, etc. Includes canonicalization validators on symbols.
# Services Analysis Report (a to m)

## 1. analytics_service.py
- **Responsibilities:** Tracks strategy performance and drift by calculating realized alpha on historical recommendations.
- **Public Methods:** `track_strategy_drift`
- **Internal Methods:** `fetch_data` (nested async helper)
- **Dependencies:** `asyncio`, `datetime`, `sqlalchemy`, models (`AnalysisHistory`, `StrategyPerformanceLog`, `WatchedStock`), `FyersService`.
- **Database Access:** Reads `AnalysisHistory` & `WatchedStock`; Writes `StrategyPerformanceLog`.
- **Transactions:** Standard implicit transactions via `db.execute` and `db.add`. DB inserts are sequenced outside of the concurrent API fetches.
- **Concurrency:** Uses `asyncio.Semaphore(5)` and `asyncio.gather` to perform concurrent broker API calls without concurrent DB session access.
- **Retry Logic:** None directly (relies on FYERS broker service).
- **Timeouts:** None explicitly handled.
- **Caching:** None.
- **Idempotency:** Queries existing log entries (`scalar_one_or_none()`) to update rather than duplicate records.
- **Observability:** Centralized logger used (`self.logger.info`, `self.logger.error`).
- **Failure Handling:** Broad `try...except` gracefully logs and suppresses errors for individual symbols, returning `None`.

## 2. backtest_service.py
- **Responsibilities:** Runs technical indicator-based backtesting strategies on historical candle data to evaluate past performance.
- **Public Methods:** `run`
- **Internal Methods:** `_empty_result`
- **Dependencies:** `pandas`, `ta.momentum` (RSIIndicator), `ta.trend` (EMAIndicator, MACD), schemas (`AnalysisMode`, `BacktestResult`, `OHLCVPoint`).
- **Database Access:** None (acts entirely on provided candle data).
- **Transactions:** None.
- **Concurrency:** Synchronous linear processing (`pandas.DataFrame.iterrows`).
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Pure function (side-effect free).
- **Observability:** None.
- **Failure Handling:** Validates length of candles (`< 35`) and returns `_empty_result`; uses broad exception block when safely calculating Sharpe ratio.

## 3. candle_reconciliation_service.py
- **Responsibilities:** Idempotent background job to scan, detect, and repair missing historical market data gaps.
- **Public Methods:** `detect_gaps`, `reconciliation_job`
- **Internal Methods:** `_is_trading_day`, `_parse_gap_timestamp`, `_run_reconciliation`
- **Dependencies:** `pandas`, `asyncio`, `sqlalchemy`, `MarketDataService`, `FyersService`, `DistributedLockService`.
- **Database Access:** Complex PostgreSQL queries (gap detection CTE), interacts with `historical_candles` and `empty_gaps` via `AsyncSessionLocal`.
- **Transactions:** `db.commit()` used during empty gaps cleanup and saving.
- **Concurrency:** Distributed coordination via `DistributedLockService`; uses `asyncio.to_thread` for IO blocking requests.
- **Retry Logic:** Backpressure safety implemented (`asyncio.sleep(0.5)`). Relies on FyersService for API retries.
- **Timeouts:** Distributed lock sets a TTL (`ttl_seconds=3600`).
- **Caching:** PostgreSQL-backed cache (`empty_gaps`) stores valid empty ranges for 24h to prevent redundant API calls.
- **Idempotency:** Distributed lock restricts multiple running instances. Cache prevents repeating repairs on known empty gaps.
- **Observability:** Circuit breaker extra attributes logged; explicit events (`reconciliation_circuit_breaker_tripped`, `holiday_gap_skipped`).
- **Failure Handling:** Circuit breaker logic suspends operation for 15 mins upon 5 consecutive API failures.

## 4. candle_store.py
- **Responsibilities:** Core repository for querying, upserting, and validating market data caches in PostgreSQL.
- **Public Methods:** `get_last_stored_date`, `get_last_stored_timestamp`, `store_candles`, `load_candles`, `save_candles`, `get_candle_count`, `update_ltp`, `get_ltp`, `get_last_trading_day`, `get_latest_completed_market_session_date`, `has_completed_daily_session`, `is_cache_fresh`, `is_cache_fresh_with_age`, `get_all_cached_symbols`, `load_all_cached_candles`.
- **Internal Methods:** None.
- **Dependencies:** `pandas`, `sqlalchemy`, `datetime`.
- **Database Access:** High volume read/write on `market_data.candles` and `market_data.ltp_cache`.
- **Transactions:** Standard DB queries with auto-commits (`db.commit()` explicitly called after insertions).
- **Concurrency:** Standard asyncio database execution.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** Manages the DB layer of the LTP cache and historical timeframe caches based on age thresholds.
- **Idempotency:** Enforced natively using PostgreSQL `INSERT ... ON CONFLICT DO UPDATE`.
- **Observability:** Standard logger used for write failures (`logger.error`).
- **Failure Handling:** Suppresses parsing and storage exceptions returning safe defaults/False values.

## 5. db_logger.py
- **Responsibilities:** Writes application logs directly to the system database.
- **Public Methods:** `log_to_db`
- **Internal Methods:** None.
- **Dependencies:** `asyncio`, `datetime`, `sqlalchemy`, `SystemLog`.
- **Database Access:** Instantiates and inserts `SystemLog` objects.
- **Transactions:** Wrapped inside `async with db.begin()` to enforce transactional integrity.
- **Concurrency:** Async database operation.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Every call inserts a distinct row.
- **Observability:** Print statements used as fallback.
- **Failure Handling:** Caught exceptions fall back to a standard `print` block.

## 6. diagnostics_service.py
- **Responsibilities:** Collects detailed runtime diagnostics, memory usage, API metrics, and system snapshots.
- **Public Methods:** `set_scanner_running`, `set_scanner_success`, `set_scanner_failed`, `record_scanner_run`, `record_scheduler_run`, `increment_fyers_metric`, `record_dashboard_snapshot`, `set_scanner_memory`, `get_memory_metrics`, `get_db_health`, `get_shadow_run_report`.
- **Internal Methods:** None.
- **Dependencies:** `psutil`, `datetime`, `sqlalchemy`.
- **Database Access:** Executes direct SQL (`pg_stat_activity`) for DB connection profiling.
- **Transactions:** Read-only executions.
- **Concurrency:** Synchronous class management; dictionary operations.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** State kept continuously in bounded memory lists (e.g., `< 50 runs`, `< 100 snapshots`).
- **Idempotency:** State setters overwrite exact fields.
- **Observability:** Acts as the primary observability bus tracker for metrics.
- **Failure Handling:** Extremely defensive execution. Broad exception handling falls back to zeros/None variables.

## 7. fyers_service.py
- **Responsibilities:** Serves as the primary broker adapter bridging FYERS API into the application context.
- **Public Methods:** `validate_token_sync`, `fetch_ltp`, `fetch_quote_profile`, `fetch_ohlcv`, `get_ltp_source`, `get_ohlcv_source`, `is_fyers_sdk_available`, `has_fyers_credentials`, `fetch_incremental_ohlcv`, `combine_candles`.
- **Internal Methods:** `_is_fyers_configured`, `_fetch_fyers_ltp`, `_fetch_fyers_candles`, `_normalize_symbol`, `_cache_symbol`, `_store_ohlcv_cache`, `_client`, `_request_history_with_retries`, `_fetch_yfinance_candles`, `_is_blacklisted`, `_blacklist_symbol`, `_is_rate_limit_error`, `_map_resolution`, `_parse_timestamp`, `_to_float`.
- **Dependencies:** `fyers_apiv3`, `pandas`, `yfinance`, `sqlalchemy`, `requests`, `threading`, `asyncio`.
- **Database Access:** Fetches token and caches data using DB services.
- **Transactions:** Standard usage.
- **Concurrency:** Leverages `asyncio.Lock` for LTP deduplication and `threading.BoundedSemaphore(3)` to serialize FYERS history rates. External ThreadPoolExecutor used for SDK calls.
- **Retry Logic:** Built-in exponential backoff up to 3 retries for broker failures, locking timeouts, and rate limits.
- **Timeouts:** Robust `NetworkTimeoutContext` used to bound requests natively at 3, 5, or 10 seconds.
- **Caching:** Comprehensive memory caching layer (`_ohlcv_cache`) with TTL (300s) alongside PostgreSQL DB caches.
- **Idempotency:** Safe DB UPSERT operations.
- **Observability:** Tracks latency, sources (Memory vs API vs DB), rate limits, emits standard telemetry.
- **Failure Handling:** Fails over cleanly to Yahoo Finance (`yfinance`). Uses 24h symbol quarantines for delisted/bad symbols. Emits custom exceptions (`FyersAuthExpiredError`, etc).

## 8. latest_scan_service.py
- **Responsibilities:** Archives completed orchestrator screener passes into permanent storage.
- **Public Methods:** `persist_successful_scan`, `get_latest_completed_scan`.
- **Internal Methods:** None.
- **Dependencies:** `uuid`, `datetime`, `sqlalchemy`.
- **Database Access:** Interacts with `ScanSnapshot` and `ScanSnapshotRecord`.
- **Transactions:** Uses `await self.db.flush()` assuming calling context handles commits.
- **Concurrency:** Standard async DB inserts.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Operates using supplied (or generated) UUIDs to avoid duplicates. Reuses objects if existing context requires it.
- **Observability:** Metrics logged manually using `log_scan_persist` and `log_dashboard_request`.
- **Failure Handling:** Logs exception and bubbles it up out of the service layer.

## 9. live_observability.py
- **Responsibilities:** Acts as an intermediate telemetry adapter designed explicitly for tracking internal system anomalies.
- **Public Methods:** `record_stale_executing`, `record_stale_reconciling`, `record_margin_mismatch`, `record_broker_timeout`, `record_trade_replay`.
- **Internal Methods:** None.
- **Dependencies:** `logging`.
- **Database Access:** None.
- **Transactions:** None.
- **Concurrency:** Synchronous execution.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Cumulative telemetry (adds incrementally per trigger).
- **Observability:** Fully defines explicit gauge and counter metrics output to log streams via specific string prefixes (`METRIC [name]`).
- **Failure Handling:** None required.

## 10. live_state_machine.py
- **Responsibilities:** Enforces strict and legally compliant lifecycle state transitions for paper and live trading.
- **Public Methods:** `validate_transition`, `is_terminal`, `transition_order_state`.
- **Internal Methods:** None.
- **Dependencies:** `sqlalchemy`, `datetime`, `logging`.
- **Database Access:** Persists `OrderExecutionEvent`.
- **Transactions:** Completes DB updates and commits modifications transactionally (`await db.commit()`).
- **Concurrency:** Linear application of DB actions per call.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Validates states and short-circuits execution identically if no state jump is needed, preventing audit bloat.
- **Observability:** Fully auditable transitions generated in `OrderExecutionEvent`.
- **Failure Handling:** Intercepts and raises `ValueError` for structurally invalid transitions.

## 11. llm_service.py
- **Responsibilities:** Connects to Groq to synthetically generate reasoning analyses and sentiment extraction via LLM prompts.
- **Public Methods:** `build_reasoning`, `analyze_sentiment`.
- **Internal Methods:** `_build_with_groq`, `_fallback_reasoning`.
- **Dependencies:** `requests`, `json`.
- **Database Access:** None.
- **Transactions:** None.
- **Concurrency:** Synchronous API operations natively blocking.
- **Retry Logic:** None (falls back instead of retrying).
- **Timeouts:** Fixed 10s and 20s request timeouts.
- **Caching:** None.
- **Idempotency:** Predictable outputs driven by prompt.
- **Observability:** `logger.error` on LLM endpoint failure.
- **Failure Handling:** Exception catches completely fall back to internal static logic `_fallback_reasoning` or 0.0 scores to maintain uptime.

## 12. lock_service.py
- **Responsibilities:** Implements distributed PostgreSQL-backed locking mechanisms to coordinate independent services.
- **Public Methods:** `acquire`, `release`, `heartbeat`, `start_heartbeat`, `stop_heartbeat`.
- **Internal Methods:** `_try_acquire`, `_heartbeat_loop`.
- **Dependencies:** `asyncio`, `socket`, `sqlalchemy`.
- **Database Access:** Creates/Updates/Deletes `SystemLock`.
- **Transactions:** Utilizes `db.begin()` and `db.begin_nested()` for safe concurrency enforcement.
- **Concurrency:** Uses a background async loop (`_heartbeat_task`) to renew lock TTL dynamically.
- **Retry Logic:** Uses while loop inside `acquire()` to retry for `timeout_seconds` with a `retry_delay`.
- **Timeouts:** Controls lock persistence via `ttl_seconds`.
- **Caching:** None.
- **Idempotency:** Integrates safely with existing DB constraints (`IntegrityError`). Stale lock recovery guarantees idempotent execution ownership.
- **Observability:** Lock captures owner ID, acquisition status, releases, timeouts, and stale recoveries explicitly.
- **Failure Handling:** Context managers explicitly throw `LockAcquisitionError`.

## 13. logger_service.py
- **Responsibilities:** Core asynchronous queue-based logger managing console, database, and websocket telemetry.
- **Public Methods:** `start`, `shutdown`, `flush_now`, `log`, `log_error`, `log_trade`, `log_job`, `log_info`, `log_warn`.
- **Internal Methods:** `_broadcast`, `_ensure_queue_for_current_loop`, `_write_fallback`, `_flush_worker`, `_drain_batch`, `_persist_batch`, `_async_persist`, `_emergency_snapshot`.
- **Dependencies:** `asyncio`, `hashlib`, `json`, `SystemLog`.
- **Database Access:** Dispatches batched log payloads to DB `SystemLog` table.
- **Transactions:** Transactions batched aggressively (`DB_BATCH_SIZE=50`) under `db.begin()`.
- **Concurrency:** Implements completely non-blocking internal queue. Flush worker managed as separate `asyncio.Task`.
- **Retry Logic:** None.
- **Timeouts:** Applies bounding (`timeout=5.0`) dynamically during engine shutdown cycles.
- **Caching:** Bounded asyncio queue buffer up to 10,000 logs.
- **Idempotency:** Generates error hashes independently.
- **Observability:** Supports metrics on queue sizes and masks raw fields matching internal string secrets.
- **Failure Handling:** Fails gracefully down to a `.jsonl` disk fallback artifact.

## 14. margin_engine.py
- **Responsibilities:** Enforces deterministic checks limiting live trading to strictly available liquid margins.
- **Public Methods:** `reserve_margin`, `release_margin`, `consume_margin`, `adjust_reservation_for_modify`.
- **Internal Methods:** None.
- **Dependencies:** `sqlalchemy`, `decimal`.
- **Database Access:** Validates limits using `LiveAccount` references.
- **Transactions:** Operates optimally in transactions executing `with_for_update()`.
- **Concurrency:** Exploits row-level PostgreSQL locking (`FOR UPDATE`) preventing any concurrent double spends.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Applies delta checks securely.
- **Observability:** Tracks margin adjustments via detailed logger information.
- **Failure Handling:** Raises `ValueError` explicitly to fail illegal margin operations safely without impacting parent models.

## 15. market_data_feed.py
- **Responsibilities:** Lightweight background WS adapter to stream raw market websocket ticks from the broker.
- **Public Methods:** `start`, `stop`, `sync_symbols`.
- **Internal Methods:** `_normalize_symbol`.
- **Dependencies:** `fyers_apiv3.FyersWebsocket`, `threading`.
- **Database Access:** None directly.
- **Transactions:** None.
- **Concurrency:** Subscribes execution to isolated `Thread`, tracking active pools using a mutex (`threading.Lock()`).
- **Retry Logic:** None manually written (delegates `reconnect=True` logic to native FYERS WS SDK).
- **Timeouts:** None.
- **Caching:** Symbol state kept perfectly synchronized between external desired list and internal connection.
- **Idempotency:** `sync_symbols` intelligently diffs and patches only deltas.
- **Observability:** Passes events up to external controllers cleanly (`on_tick`, `on_error`, `on_connection_change`).
- **Failure Handling:** Wraps schema errors inside a try-catch for Pydantic drops to keep socket running smoothly.

## 16. market_data_service.py
- **Responsibilities:** Advanced high-throughput historical PostgreSQL chunking system managing candle storage safely.
- **Public Methods:** `get_latest_candle_time`, `get_candle_count`, `validate_candle_continuity`, `check_stale_candles`, `upsert_candles`, `load_full_history`.
- **Internal Methods:** `_upsert_chunk`.
- **Dependencies:** `pandas`, `sqlalchemy`.
- **Database Access:** High performance manipulation of `HistoricalCandle` with `func.now()`.
- **Transactions:** Utilizes `async with db.begin()` for massive array imports alongside PostgreSQL `ON CONFLICT DO UPDATE`.
- **Concurrency:** Divides processing workloads gracefully via `MAX_CHUNK_SIZE=900`.
- **Retry Logic:** Intelligently retries strictly upon detecting SQLite/Postgres DB lock events using geometric exponent backoffs plus a random jitter.
- **Timeouts:** None inside operations.
- **Caching:** Tracks granular health evaluations measuring local db freshness rules based heavily upon varying timescales.
- **Idempotency:** Natively enforced via `on_conflict_do_update` using primary database constraints.
- **Observability:** Very high level; captures duplicate rows, execution lengths (ms), lock wait counts, and silent row rollbacks.
- **Failure Handling:** Raises out after strict backoff limit reached; initiates local rollbacks properly.

## 17. market_engine_service.py
- **Responsibilities:** Top-level continuous orchestrator running live market data loops and automated position reconciliations.
- **Public Methods:** `start_loop`, `shutdown`, `request_start`, `request_stop`, `heartbeat`, `status`, `is_market_hours`.
- **Internal Methods:** Contains over a dozen internals including `_run_loop`, `_reconcile_session`, `_poll_missing_prices`, `_on_tick`, `_sweep_historical_positions`, `_reconcile_ohlcv_sequence`.
- **Dependencies:** `asyncio`, `sqlalchemy`, `FyersMarketDataFeed`, `PaperTradingService`.
- **Database Access:** Modifies core records like `MarketEngineSession`, `PaperOrder`, and `PaperPosition`.
- **Transactions:** Applies `with_for_update(skip_locked=True)` internally resolving race conditions between loops and incoming ticks safely.
- **Concurrency:** Operates concurrent asyncio tasks (tick loop, background recon loop) coordinating thread-safely across states. Uses async `Semaphore` restrictions for external backpressures.
- **Retry Logic:** Automated state loop transitions cleanly back to `RUNNING` from `ERROR_RETRYING`.
- **Timeouts:** Monitors exact time bounds matching specific market hours (IST zone logic).
- **Caching:** Subscriptions mapped actively via local RAM caches (`latest_ltp`, `_active_positions_cache`).
- **Idempotency:** `_record_event` restricts duplication via explicitly crafted `dedupe_key` signatures matching exactly to unique database state updates.
- **Observability:** Pushes extensive and granular event notifications to both users and telemetry backends.
- **Failure Handling:** Highly resilient: if web socket dies, switches to polling (`_poll_missing_prices`), auto-pauses when auth is revoked, and retroactively reconstructs OHLC timelines to fix missed data safely.

## 18. market_info_service.py
- **Responsibilities:** Serves static fallback information representing base company details or profiles seamlessly.
- **Public Methods:** `get_company_profile`.
- **Internal Methods:** `_get_nifty_csv_profile`, `_load_nifty_profiles`, `_normalize_symbol`.
- **Dependencies:** `requests`, `csv`.
- **Database Access:** Reads data via bundled application payload CSV files (bypassing DB usage entirely).
- **Transactions:** None.
- **Concurrency:** Blocking execution natively.
- **Retry Logic:** None.
- **Timeouts:** Fast execution bound artificially at 6s timeout bounds limits (`timeout=6`).
- **Caching:** Pre-caches large payload NIFTY 500 definitions lazily (`_nifty_profile_cache`).
- **Idempotency:** Pure data translation logic safely returning deterministic results.
- **Observability:** Mutes exceptions during background updates silently.
- **Failure Handling:** Binds failed API payloads automatically directly toward identical matching keys inside internal bundled datasets.
# Analysis Report: Agents & Services (N-Z)

## Agents

### backtest_agent.py
- **Responsibilities:** Runs backtesting for a given symbol and mode using historical candles.
- **Inputs:** `symbol` (str), `mode` (AnalysisMode), `candles` (list[OHLCVPoint]).
- **Outputs:** `BacktestResult`.
- **Decision Logic:** None directly (delegates execution to `BacktestService`).
- **Dependencies:** `BacktestService`, local schemas.
- **LLM Usage:** None.
- **Tools Used:** None.
- **Failure Handling:** None explicitly within the agent (relegated to service).

### fundamental_analysis_agent.py
- **Responsibilities:** Fetches and calculates fundamental scores (revenue growth, profit margin, debt to equity, P/E ratio) for a stock using Yahoo Finance.
- **Inputs:** `symbol` (str).
- **Outputs:** `FundamentalAnalysisResult`.
- **Decision Logic:** Normalizes fundamental metrics into a score between -1.0 and 1.0, then combines them into an average fundamental score.
- **Dependencies:** `yfinance`, schemas, logger.
- **LLM Usage:** None.
- **Tools Used:** Yahoo Finance API (via `yfinance`).
- **Failure Handling:** Catches 404s and general exceptions, returning a neutral fallback result if the API fails or data is unavailable.

### news_analysis_agent.py
- **Responsibilities:** Fetches recent news for a symbol and determines its sentiment score and label.
- **Inputs:** `symbol` (str).
- **Outputs:** `tuple[list[ArticleItem], float, str, str]` (articles, score, label, summary).
- **Decision Logic:** None directly (delegates to `sentiment_service`).
- **Dependencies:** `NewsService`, `SentimentService`, schemas.
- **LLM Usage:** Delegated to `SentimentService`.
- **Tools Used:** `NewsService`, `SentimentService`.
- **Failure Handling:** If no articles are found, returns a neutral fallback tuple without crashing.

### orchestrator_agent.py
- **Responsibilities:** Coordinates the entire analysis pipeline, including full bulk analysis, screener execution, risk filtering, and recommendation generation.
- **Inputs:** `AnalysisRequest`, `ScreenerRequest`.
- **Outputs:** `FullAnalysisResponse`, `AnalysisResponse`, `ScreenerResponse`.
- **Decision Logic:** Prioritizes screening stages, deduplicates symbols, determines fallback strategies when live data fails, enforces strict buy gates, and ranks candidates.
- **Dependencies:** `FyersService`, `ScreenerService`, all other internal agents (`TechnicalAnalysisAgent`, `NewsAnalysisAgent`, `BacktestAgent`, `RecommendationAgent`, `RankingAgent`, `FundamentalAnalysisAgent`), SQLAlchemy models.
- **LLM Usage:** None directly (handled by `RecommendationAgent`).
- **Tools Used:** Multiple sub-agents, `FyersService`, `ScreenerService`, Database.
- **Failure Handling:** Uses fallback modes if OHLCV data is unavailable, intercepts API errors, handles missing bulk data, logs determinism debug info, and tracks data quality failures carefully.

### ranking_agent.py
- **Responsibilities:** Ranks analyzed stocks based on their overall scores and categorizes them into BUY/WATCH lists.
- **Inputs:** `list[StockAnalysisResult]`.
- **Outputs:** `RankingsResponse`.
- **Decision Logic:** Delegates to `RankingService`.
- **Dependencies:** `RankingService`, schemas.
- **LLM Usage:** None.
- **Tools Used:** None.
- **Failure Handling:** None explicitly.

### recommendation_agent.py
- **Responsibilities:** Generates final trade recommendations by synthesizing technical, sentiment, fundamental, and backtest data.
- **Inputs:** `symbol`, `technical_results`, `sentiment_label`, `sentiment_score`, `fundamental_result`, `backtests`, `candles_by_mode`.
- **Outputs:** `FinalRecommendation`.
- **Decision Logic:** Aggregates signals and requests LLM reasoning from `LLMService`, then uses `RecommendationService` to construct the final payload.
- **Dependencies:** `LLMService`, `RecommendationService`.
- **LLM Usage:** Calls `LLMService` to build qualitative reasoning based on the quantitative inputs.
- **Tools Used:** None.
- **Failure Handling:** Handled in downstream services.

### router_agent.py
- **Responsibilities:** Routes incoming API requests to the appropriate `OrchestratorAgent` methods.
- **Inputs:** `AnalysisRequest`, `ScreenerRequest`.
- **Outputs:** `AnalysisResponse`, `FullAnalysisResponse`, `RankingsResponse`, `ScreenerResponse`.
- **Decision Logic:** Simple delegation based on the requested endpoint/flow.
- **Dependencies:** `OrchestratorAgent`, Session (SQLAlchemy), logger.
- **LLM Usage:** None.
- **Tools Used:** None.
- **Failure Handling:** None explicitly.

### technical_analysis_agent.py
- **Responsibilities:** Runs bulk technical analysis on a dictionary of candles.
- **Inputs:** `candles_dict` (dict[str, list[OHLCVPoint]]), `mode` (AnalysisMode).
- **Outputs:** `dict[str, TechnicalAnalysisResult]`.
- **Decision Logic:** Delegates to `TechnicalAnalysisService`.
- **Dependencies:** `TechnicalAnalysisService`.
- **LLM Usage:** None.
- **Tools Used:** None.
- **Failure Handling:** None explicitly.

---

## Services (N - Z)

### news_service.py
- **Responsibilities:** Fetches recent news articles for a given symbol.
- **Public Methods:** `fetch_recent_news`
- **Internal Methods:** None
- **Dependencies:** `requests`, `datetime`, `settings`, `ArticleItem`
- **Database Access:** None
- **Transactions:** None
- **Concurrency:** None
- **Retry Logic:** None
- **Timeouts:** Uses 6-second timeout for HTTP requests.
- **Caching:** None
- **Idempotency:** Yes (read-only requests).
- **Observability:** None
- **Failure Handling:** Try-except blocks around HTTP requests. Falls back to DuckDuckGo if the primary News API fails. Returns an empty list on total failure.

### ohlcv_store.py
- **Responsibilities:** Deprecated stub file pointing to `candle_store.py`.
- **Public Methods:** None
- **Internal Methods:** None
- **Dependencies:** `warnings`
- **Database Access:** None
- **Transactions:** None
- **Concurrency:** None
- **Retry Logic:** None
- **Timeouts:** None
- **Caching:** None
- **Idempotency:** N/A
- **Observability:** Raises `DeprecationWarning`.
- **Failure Handling:** N/A

### paper_trading_service.py
- **Responsibilities:** Manages simulated paper trading accounts, order placement, modifications, position tracking, and metrics.
- **Public Methods:** `get_dashboard`, `get_positions`, `get_pending_orders`, `get_order_history`, `get_trades`, `reset_account`, `place_order`, `cancel_order`, `modify_order`, `close_position`, `update_position`, `recommendation_prefill`, `get_workspace`, `get_quote`
- **Internal Methods:** `_get_or_create_account`, `_validate_symbol`, `_position_models`, `_order_models`, `_trade_models`, `_requested_price`, `_try_fill_order`, `_record_execution_event`, `add_notification` (partially shown)
- **Dependencies:** `pandas`, `sqlalchemy`, `FyersService`, paper trading models, observability metrics.
- **Database Access:** Comprehensive read/write to `PaperTradingAccount`, `PaperPosition`, `PaperOrder`, `PaperTradeHistory`, `PaperTransaction`, `ExecutionEvent`.
- **Transactions:** Explicit `db.commit()` and `db.rollback()` blocks to ensure atomic order placement and balance updates. Uses `with_for_update` for account locking.
- **Concurrency:** Uses `threading.Lock` (`_account_creation_lock`) for account creation to prevent deadlocks.
- **Retry Logic:** Checks for idempotent requests.
- **Timeouts:** 5-second timeout on FYERS quote fetch (`asyncio.run_coroutine_threadsafe`).
- **Caching:** None explicitly shown for prices beyond standard DB querying.
- **Idempotency:** Uses `idempotency_key` during `place_order` to prevent duplicate orders.
- **Observability:** Uses `trading_logger`, logs extensively on ORDER_PLACED, FILLED, REJECTED. Updates Prometheus metrics (`DUPLICATE_EXECUTIONS`, `ORDER_EXECUTIONS`).
- **Failure Handling:** Rollbacks transactions on `IntegrityError` or exceptions. Rejects orders gracefully on insufficient funds or missing data.

### partition_manager.py
- **Responsibilities:** Auto-creates missing PostgreSQL partitions for historical candle data at startup.
- **Public Methods:** `verify_and_create_partitions`
- **Internal Methods:** None
- **Dependencies:** `sqlalchemy.text`, `datetime`
- **Database Access:** Executes raw SQL `CREATE TABLE IF NOT EXISTS ... PARTITION OF ...`.
- **Transactions:** Commits after each partition creation.
- **Concurrency:** None explicitly.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** SQL uses `IF NOT EXISTS` and checks catalog (`pg_class`).
- **Observability:** Logs missing partitions and successful creation.
- **Failure Handling:** Logs errors during creation and raises exceptions. Skips non-Postgres dialects gracefully.

### persistence_service.py
- **Responsibilities:** Upserts historical candles and scan results to the database to ensure zero-downtime updates.
- **Public Methods:** `save_latest_scan_results`, `upsert_historical_candles`
- **Internal Methods:** `_insert`
- **Dependencies:** `sqlalchemy.dialects.postgresql.insert`
- **Database Access:** Upserts into `LatestScanResult` and `HistoricalCandle`.
- **Transactions:** Relies on connection's auto-commit or caller's transaction.
- **Concurrency:** Uses Postgres `ON CONFLICT DO UPDATE` to handle concurrent inserts safely.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Yes, `ON CONFLICT DO UPDATE` guarantees idempotency for repeated data.
- **Observability:** None.
- **Failure Handling:** Returns early if lists are empty.

### ranking_service.py
- **Responsibilities:** Sorts and assigns rankings to analyzed stocks, separating them into BUY and WATCH categories.
- **Public Methods:** `rank`
- **Internal Methods:** `_best_by_mode`
- **Dependencies:** schemas.
- **Database Access:** None.
- **Transactions:** None.
- **Concurrency:** None.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Pure function, always idempotent.
- **Observability:** None.
- **Failure Handling:** None needed (standard list sorting).

### recommendation_service.py
- **Responsibilities:** Generates final recommendations, calculates dynamic weights (technical, backtest, news, fundamentals), and builds trade plans.
- **Public Methods:** `build`, `calculate_dynamic_weights`
- **Internal Methods:** `_backtest_component`, `_build_trade_plans`, `_setup_type`
- **Dependencies:** `statistics.mean`, schemas.
- **Database Access:** None.
- **Transactions:** None.
- **Concurrency:** None.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Pure function.
- **Observability:** None.
- **Failure Handling:** Caps and bounds scores safely (`min(100.0)`, `max(0.0)`); gracefully ignores empty indicator sets.

### reconciliation_framework.py
- **Responsibilities:** Claims orphaned or stalled live trading orders for reconciliation.
- **Public Methods:** `get_next_backoff`, `claim_batch_for_reconciliation`, `apply_backoff`
- **Internal Methods:** None
- **Dependencies:** `sqlalchemy`
- **Database Access:** Uses `SELECT ... FOR UPDATE SKIP LOCKED` on `LiveOrder`.
- **Transactions:** Uses caller's transaction (requires one to maintain lock).
- **Concurrency:** Safe in distributed systems via `SKIP LOCKED`.
- **Retry Logic:** Exponential backoff calculation for max 5 retries.
- **Timeouts:** None directly.
- **Caching:** None.
- **Idempotency:** Yes, claims only unlocked stale rows.
- **Observability:** Logs claimed orphaned orders and circuit breaker activations.
- **Failure Handling:** Halts reconciliation (marks `MANUAL_INTERVENTION_REQUIRED`) if max retries exceeded.

### retention_service.py
- **Responsibilities:** Cleans up old logs, events, candles, replays, and snapshots from the database.
- **Public Methods:** `cleanup`
- **Internal Methods:** None
- **Dependencies:** `sqlalchemy.delete`, `datetime`
- **Database Access:** Executes deletes across multiple tables based on age.
- **Transactions:** Single transaction for all cleanup operations (`db.commit()` at end).
- **Concurrency:** None.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Yes, deleting old rows is idempotent.
- **Observability:** None (returns counts).
- **Failure Handling:** None explicitly.

### scan_execution_service.py
- **Responsibilities:** Executes screener scans safely, managing distributed locks and background execution.
- **Public Methods:** `execute_scan`
- **Internal Methods:** `_run_scan_task`
- **Dependencies:** `DistributedLockService`, `RouterAgent`, `LatestScanService`, `asyncio`
- **Database Access:** Creates and updates `ScanSnapshot`.
- **Transactions:** Commits updates to snapshots.
- **Concurrency:** Uses `DistributedLockService` to prevent concurrent scans across workers.
- **Retry Logic:** None.
- **Timeouts:** Uses TTL on distributed lock (3600 seconds), 0-second acquire timeout.
- **Caching:** None.
- **Idempotency:** No.
- **Observability:** Extensive logging of lock acquisition, scan duration, failures, and success metrics. Updates progress via `asyncio.Queue`.
- **Failure Handling:** Catches `CancelledError` and generic Exceptions, logs them, and updates the `ScanSnapshot` status to `FAILED`. Releases lock in `finally` block.

### screener_service.py
- **Responsibilities:** Filters universes of stocks through technical rules to find trade candidates. Handles bulk fetching and pre-computation of indicators.
- **Public Methods:** `get_metrics`, `validate_startup_health`, `fallback_fetch_yfinance`, `screen_symbols_swing`
- **Internal Methods:** `_process_single_symbol`, `_log_determinism_debug`, `_passes_data_quality`, `_passes_broad_trend`, `_build_conditions`, `_weighted_score`
- **Dependencies:** `yfinance`, `pandas`, `TechnicalAnalysisService`, `MarketDataService`, `FyersService`, `psutil`.
- **Database Access:** Heavily utilizes `MarketDataService` to check cache health, upsert missing candles, and load full history.
- **Transactions:** Managed implicitly or by `MarketDataService`.
- **Concurrency:** Uses `TokenBucketRateLimiter`, runs asyncio tasks concurrently (`Semaphore(3)`) for fetching symbols, runs heavy calculations in thread pools or vectorized pandas.
- **Retry Logic:** None explicitly here, delegates to `MarketDataService`/`FyersService`.
- **Timeouts:** None directly.
- **Caching:** Heavily reliant on `MarketDataService` DB cache, forces backfills if cache is missing.
- **Idempotency:** Yes.
- **Observability:** Uses `scanner_logger`, tracks custom metrics (`scanner_metrics`), memory audits (`get_rss_mb`), and pipeline stage logs.
- **Failure Handling:** Gracefully skips symbols with insufficient data, catches exceptions during symbol processing, logs failures via diagnostics hooks.

### sentiment_service.py
- **Responsibilities:** Summarizes and calculates sentiment scores for lists of news articles.
- **Public Methods:** `summarize`
- **Internal Methods:** None
- **Dependencies:** `LLMService`
- **Database Access:** None
- **Transactions:** None
- **Concurrency:** None
- **Retry Logic:** None
- **Timeouts:** None (handled in `LLMService`).
- **Caching:** None.
- **Idempotency:** Yes.
- **Observability:** Logs errors if LLM fails.
- **Failure Handling:** Returns neutral sentiment (0.0) if the LLM fails.

### technical_analysis_service.py
- **Responsibilities:** Calculates technical indicators and scores for single or bulk datasets using Pandas and `ta` library.
- **Public Methods:** `get_required_candle_count`, `analyze_bulk`, `analyze_bulk_from_frame`
- **Internal Methods:** `_log_analysis_decision`, `_calculate_supertrend`, `_is_hammer`, `_is_gravestone_doji`
- **Dependencies:** `pandas`, `ta`, `psutil`
- **Database Access:** None.
- **Transactions:** None.
- **Concurrency:** Pandas vectorized operations.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Yes.
- **Observability:** Memory audits via `get_rss_mb()`. Extremely detailed decision logs.
- **Failure Handling:** Handles missing indicators safely (e.g. `pd.isna` checks). Skips symbols with insufficient candles silently.

### token_service.py
- **Responsibilities:** Manages FYERS API authentication tokens, handles DB persistence and memory caching.
- **Public Methods:** `has_cached_token`, `get_fyers_token_row`, `save_access_token`, `get_token_status`, `get_token_history`, `get_current_access_token`, `get_current_access_token_sync`
- **Internal Methods:** `_clear_token_cache`, `_set_token_cache`, `_mask_token`
- **Dependencies:** `sqlalchemy`, `FyersService`.
- **Database Access:** Reads/writes `FyersToken` and `FyersTokenHistory`.
- **Transactions:** Explicit `db.begin()`, `db.commit()`, and `db.rollback()` for token saving.
- **Concurrency:** Global memory cache protected by `threading.Lock()` (`_TOKEN_LOCK`) with double-checked locking in sync method.
- **Retry Logic:** None.
- **Timeouts:** 15.0 second timeout for FYERS token validation.
- **Caching:** In-memory global variable cache with TTL (`_TOKEN_CACHE_TTL`).
- **Idempotency:** Yes.
- **Observability:** Very verbose logging of cache hits/misses, DB states, and validation flows.
- **Failure Handling:** Reverts DB transaction on error, clears memory cache on invalidation or DB failures. Allows "cache fallback" if DB is unavailable.

### universe_service.py
- **Responsibilities:** Fetches active symbol lists for predefined universes (e.g. NIFTY500).
- **Public Methods:** `get_active_symbols`, `get_all_active_symbols`
- **Internal Methods:** None
- **Dependencies:** `sqlalchemy`
- **Database Access:** Queries `StockMaster`.
- **Transactions:** Auto-commit.
- **Concurrency:** None.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Yes.
- **Observability:** Logs errors on DB failure.
- **Failure Handling:** Returns empty list if DB query fails.

### workstation_service.py
- **Responsibilities:** Manages saved scans, scan history, price alerts, risk settings, and market overview endpoints for the workstation UI.
- **Public Methods:** `list_universes`, `save_scan`, `list_saved_scans`, `delete_saved_scan`, `record_scan_history`, `list_scan_history`, `compare_scan`, `market_overview`, `create_alert`, `list_alerts`, `delete_alert`, `get_risk_settings`, `update_risk_settings`, `api_health`
- **Internal Methods:** `_scan_item`, `_history_item`, `_history_symbols`, `_market_item`, `_movers_from_latest_scan`, `_evaluate_scan_entry_alerts`, `_risk_row`, `_risk_response`, `_alert_item`
- **Dependencies:** `csv`, `sqlalchemy`, `FyersService`
- **Database Access:** Manages `SavedScan`, `ScanHistorySnapshot`, `WorkstationAlert`, `RiskSettings`, `FyersToken`.
- **Transactions:** Uses `db.commit()` on modifications.
- **Concurrency:** None explicitly.
- **Retry Logic:** None.
- **Timeouts:** None.
- **Caching:** None.
- **Idempotency:** Normal CRUD behavior.
- **Observability:** None explicitly.
- **Failure Handling:** Throws `ValueError` on invalid input or missing records.
