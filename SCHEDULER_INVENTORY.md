# Scheduler and Background Jobs Inventory

## 1. Market Engine Spin Up
* **Job Name**: `market_engine_spin_up`
* **File**: `backend/app/main.py`
* **Trigger Frequency**: Cron (Monday-Friday at 08:55 AM IST)
* **Purpose**: Spins up the core market engine immediately before the market opens to prepare for early trading activity.
* **Startup Registration Location**: `backend/app/main.py` inside the FastAPI `lifespan` context using APScheduler `scheduler.add_job`.
* **Failure Impact**: The market engine may not start automatically, resulting in missed pre-market or early morning market data, updates, and order placements.

## 2. Pre-Market Deep Scan
* **Job Name**: `pre_market_deep_scan`
* **File**: `backend/app/main.py`
* **Trigger Frequency**: Cron (Monday-Friday at 09:00 AM IST)
* **Purpose**: Executes the automated screening job (`automated_screening_job`) at market open to generate fresh technical analysis and candidate matches.
* **Startup Registration Location**: `backend/app/main.py` inside the FastAPI `lifespan` context using APScheduler `scheduler.add_job`.
* **Failure Impact**: The system will not generate daily swing candidates, leaving traders without programmatic recommendations for the day.

## 3. Intraday Engine Heartbeat 1
* **Job Name**: `intraday_heartbeat_1`
* **File**: `backend/app/main.py`
* **Trigger Frequency**: Cron (Monday-Friday, 09:00 AM to 02:45 PM IST, every 15 minutes)
* **Purpose**: Maintains an active heartbeat and performs periodic sync checks for the intraday trading engine.
* **Startup Registration Location**: `backend/app/main.py` inside the FastAPI `lifespan` context using APScheduler `scheduler.add_job`.
* **Failure Impact**: Periodic engine state checks and syncs may be missed, potentially delaying state recovery if the system drifts.

## 4. Intraday Engine Heartbeat 2
* **Job Name**: `intraday_heartbeat_2`
* **File**: `backend/app/main.py`
* **Trigger Frequency**: Cron (Monday-Friday, 03:00 PM to 03:30 PM IST, every 15 minutes)
* **Purpose**: Continues the engine heartbeat logic specifically through the final 30 minutes of the market session.
* **Startup Registration Location**: `backend/app/main.py` inside the FastAPI `lifespan` context using APScheduler `scheduler.add_job`.
* **Failure Impact**: Late-day syncs and engine sanity checks will fail to execute, posing risks to end-of-day reconciliation.

## 5. Market Engine Cool Down
* **Job Name**: `market_engine_cool_down`
* **File**: `backend/app/main.py`
* **Trigger Frequency**: Cron (Monday-Friday at 03:30 PM IST)
* **Purpose**: Shuts down the market engine precisely when the Indian stock market closes.
* **Startup Registration Location**: `backend/app/main.py` inside the FastAPI `lifespan` context using APScheduler `scheduler.add_job`.
* **Failure Impact**: The market engine remains active out-of-hours, wasting compute resources and potentially executing logic on stale/post-market data.

## 6. Strategy Performance & Drift Tracker
* **Job Name**: `track_strategy_drift_job`
* **File**: `backend/app/main.py`
* **Trigger Frequency**: Cron (Fridays at 04:00 PM IST)
* **Purpose**: Analyzes weekly strategy performance and tracks algorithmic drift after the market closes for the week.
* **Startup Registration Location**: `backend/app/main.py` inside the FastAPI `lifespan` context using APScheduler `scheduler.add_job`.
* **Failure Impact**: Strategy degradation metrics will not be compiled, eliminating automated feedback loops for algorithm tuning.

## 7. Retention Cleanup
* **Job Name**: `retention_cleanup`
* **File**: `backend/app/main.py`
* **Trigger Frequency**: Cron (Daily at 02:15 AM IST)
* **Purpose**: Cleans up old or stale data (like expired logs or ancient candles) from the database to maintain performance and storage limits.
* **Startup Registration Location**: `backend/app/main.py` inside the FastAPI `lifespan` context using APScheduler `scheduler.add_job`.
* **Failure Impact**: The database will accumulate unbounded stale data, eventually causing storage exhaustion or degraded query performance.

## 8. Legacy Alert Monitor
* **Job Name**: `legacy-alert-monitor` (`_monitor_positions_background`)
* **File**: `backend/app/main.py`
* **Trigger Frequency**: Continuous background loop (every 5 seconds)
* **Purpose**: Periodically fetches live prices to check against user-defined price alerts and triggers them when conditions are met.
* **Startup Registration Location**: `backend/app/main.py` inside the FastAPI `lifespan` via `app.state.task_supervisor.start()`.
* **Failure Impact**: Configured user price alerts will silently fail to trigger when target prices are hit.

## 9. Core Market Engine Loop
* **Job Name**: `market-engine-loop` (`_run_loop`)
* **File**: `backend/app/services/market_engine_service.py`
* **Trigger Frequency**: Continuous background loop
* **Purpose**: Manages active trading automation, continuously syncing paper/live orders, positions, and market data feeds.
* **Startup Registration Location**: `backend/app/services/market_engine_service.py` inside the `start_loop()` method via `asyncio.create_task()`.
* **Failure Impact**: All automated trading functions halt. Active positions are not monitored, stop-losses may not trigger locally, and the system loses sync with the live broker.

## 10. Lock Service Heartbeat
* **Job Name**: `_heartbeat_loop`
* **File**: `backend/app/services/lock_service.py`
* **Trigger Frequency**: Continuous background loop
* **Purpose**: Periodically renews Postgres advisory locks / application-level locks to maintain single-instance exclusivity.
* **Startup Registration Location**: `backend/app/services/lock_service.py` inside the class initialization or acquisition via `loop.create_task()`.
* **Failure Impact**: The active lock expires prematurely, potentially allowing a secondary app instance to take control, resulting in a split-brain scenario with duplicated trading executions.

## 11. Async Logger Flush Worker
* **Job Name**: `_flush_worker`
* **File**: `backend/app/services/logger_service.py`
* **Trigger Frequency**: Continuous background loop
* **Purpose**: Processes the internal log queue and flushes log entries asynchronously to the database or external sinks in batches.
* **Startup Registration Location**: `backend/app/services/logger_service.py` during initialization via `asyncio.create_task()`.
* **Failure Impact**: Log entries pile up in application memory leading to an eventual Out Of Memory (OOM) crash, or logs are entirely dropped losing system observability.

## 12. On-Demand Background Scanner
* **Job Name**: `run_scan_in_background`
* **File**: `backend/app/routes/analysis.py`
* **Trigger Frequency**: On-demand (Triggered by user HTTP requests to `/api/v1/scanner/run`)
* **Purpose**: Offloads heavy technical screening processing to the background to avoid blocking the API request cycle.
* **Startup Registration Location**: `backend/app/routes/analysis.py` inside the route handler via `asyncio.create_task()`.
* **Failure Impact**: The requested scan silently aborts in the background, generating no technical matches or reports for the user.

## 13. Market Data Background Upsert
* **Job Name**: `_upsert_chunk`
* **File**: `backend/app/services/market_data_service.py`
* **Trigger Frequency**: On-demand (Triggered during large historical data fetches)
* **Purpose**: Asynchronously inserts historical candle chunks into the database without blocking the active loop.
* **Startup Registration Location**: `backend/app/services/market_data_service.py` via `loop.create_task()`.
* **Failure Impact**: Historical market data gaps occur in the local database because fetched chunks fail to persist.
