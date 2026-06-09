# Database Schema Export

This document provides a comprehensive export of all SQLAlchemy models, Alembic migrations, and database tables in the system.

## Table: `analysis_history`
- **Purpose**: Stores historical analysis records for watched stocks, including technical and sentiment scores.
- **Columns**: `id`, `stock_id`, `mode`, `technical_score`, `sentiment_score`, `backtest_score`, `recommendation`, `confidence`, `reasoning`, `created_at`.
- **Types**: `Integer`, `Integer`, `String(16)`, `Float`, `Float`, `Float`, `String(12)`, `Float`, `Text`, `DateTime`.
- **Indexes**: `id`, `stock_id`, `mode`, `recommendation`, `created_at`.
- **Constraints**: Primary Key on `id`, Foreign Key on `stock_id` (to `watched_stocks.id`).
- **Relationships**: `WatchedStock`.
- **Used Services**: Analysis Service.
- **Data Lifecycle**: Append-only history, created on analysis.
- **Example Records**: 
  ```json
  {"id": 1, "stock_id": 5, "mode": "swing", "recommendation": "BUY", "confidence": 0.85, "created_at": "2026-06-07T12:00:00Z"}
  ```

## Table: `backtest_history`
- **Purpose**: Stores historical backtesting results for stocks.
- **Columns**: `id`, `stock_id`, `mode`, `strategy_name`, `total_return`, `cagr`, `max_drawdown`, `win_rate`, `profit_factor`, `trade_count`, `verdict`, `created_at`.
- **Types**: `Integer`, `Integer`, `String(16)`, `String(80)`, `Float`, `Float`, `Float`, `Float`, `Float`, `Integer`, `String(20)`, `DateTime`.
- **Indexes**: `id`, `stock_id`, `mode`, `created_at`.
- **Constraints**: Primary Key on `id`, Foreign Key on `stock_id` (to `watched_stocks.id`).
- **Relationships**: `WatchedStock`.
- **Used Services**: Backtest Engine.
- **Data Lifecycle**: Append-only, created upon backtest execution.
- **Example Records**:
  ```json
  {"id": 1, "stock_id": 10, "strategy_name": "SMA Crossover", "total_return": 15.5, "win_rate": 60.5, "verdict": "PASS"}
  ```

## Table: `strategy_performance_log`
- **Purpose**: Logs strategy performance and realized returns over time.
- **Columns**: `id`, `symbol`, `screened_date`, `initial_score`, `dominant_agent`, `realized_return_5d`, `realized_return_10d`, `realized_return_20d`, `created_at`.
- **Types**: `Integer`, `String(25)`, `DateTime`, `Float`, `String(50)`, `Float`, `Float`, `Float`, `DateTime`.
- **Indexes**: `id`, `symbol`, `screened_date`.
- **Constraints**: Primary Key on `id`.
- **Relationships**: None explicitly.
- **Used Services**: Strategy Evaluator, Metrics Service.
- **Data Lifecycle**: Created initially, updated lazily when N-day realized return is calculated.
- **Example Records**:
  ```json
  {"id": 1, "symbol": "RELIANCE", "initial_score": 90.0, "realized_return_5d": 2.5, "created_at": "2026-06-07T12:00:00Z"}
  ```

## Table: `scanned_candidates`
- **Purpose**: Tracks candidates evaluated by the stock screener.
- **Columns**: `id`, `symbol`, `scanned_at`, `screener_name`, `technical_score`, `technical_signal`, `screener_score`, `matched`.
- **Types**: `Integer`, `String(25)`, `DateTime`, `String(100)`, `Float`, `String(20)`, `Float`, `Boolean`.
- **Indexes**: `id`, `symbol`, `scanned_at`.
- **Constraints**: Primary Key on `id`.
- **Relationships**: None explicitly.
- **Used Services**: Screener, Market Data pipeline.
- **Data Lifecycle**: Generated during scan, short-lived or archived.
- **Example Records**:
  ```json
  {"id": 1, "symbol": "TCS", "scanned_at": "2026-06-07T10:00:00Z", "screener_name": "Nifty500", "matched": true}
  ```

## Table: `fyers_tokens`
- **Purpose**: Stores active and historical FYERS API authorization tokens.
- **Columns**: `id`, `access_token`, `refresh_token`, `created_at`, `expires_at`, `is_active`, `validated_at`, `status`, `access_token_saved_at`, `last_error`.
- **Types**: `Integer`, `Text`, `Text`, `DateTime`, `DateTime`, `Boolean`, `DateTime`, `String(32)`, `DateTime`, `Text`.
- **Indexes**: `status`.
- **Constraints**: Primary Key on `id`.
- **Relationships**: Used across trading engine.
- **Used Services**: Authentication service, Trading service.
- **Data Lifecycle**: Updated daily or when token expires. Re-validated on startup.
- **Example Records**:
  ```json
  {"id": 1, "access_token": "ey...", "is_active": true, "status": "active", "expires_at": "2026-06-08T00:00:00Z"}
  ```

## Table: `idempotency_records`
- **Purpose**: Tracks requests to ensure safe retries and avoid duplicate operations (idempotency).
- **Columns**: `id`, `idempotency_key`, `operation_type`, `entity_id`, `request_hash`, `status`, `created_at`, `completed_at`.
- **Types**: `Integer`, `String(128)`, `String(64)`, `Integer`, `String(128)`, `String(16)`, `DateTime`, `DateTime`.
- **Indexes**: `id`, `idempotency_key`, `operation_type`, `status`, `created_at`, composite(`idempotency_key`, `status`).
- **Constraints**: Primary Key on `id`, Unique on `idempotency_key`.
- **Relationships**: Can be linked to entities indirectly via `entity_id` and `operation_type`.
- **Used Services**: API Middleware, Trading Service.
- **Data Lifecycle**: Created on request, updated on completion, typically purged after TTL.
- **Example Records**:
  ```json
  {"id": 1, "idempotency_key": "req_xyz", "operation_type": "PLACE_ORDER", "status": "COMPLETED"}
  ```

## Table: `migration_checkpoints`
- **Purpose**: Safely tracks batch migration processes across the database.
- **Columns**: `table_name`, `last_processed_primary_key`, `last_processed_chunk`, `rows_migrated`, `started_at`, `updated_at`, `migration_status`, `migration_run_id`, `error_message`.
- **Types**: `String(64)`, `Integer`, `Integer`, `Integer`, `DateTime`, `DateTime`, `String(32)`, `String(128)`, `Text`.
- **Indexes**: `table_name`.
- **Constraints**: Primary Key on `table_name`.
- **Relationships**: Independent.
- **Used Services**: Database Migration Scripts.
- **Data Lifecycle**: Created and updated iteratively during background migration scripts.
- **Example Records**:
  ```json
  {"table_name": "historical_candles", "rows_migrated": 50000, "migration_status": "COMPLETED"}
  ```

## Table: `live_accounts`
- **Purpose**: Represents a user's real trading account and wallet balances.
- **Columns**: `id`, `name`, `base_currency`, `starting_balance`, `available_cash`, `reserved_cash`, `max_risk_per_trade`, `created_at`, `updated_at`.
- **Types**: `Integer`, `String(80)`, `String(8)`, `Numeric(18,2)`, `Numeric(18,2)`, `Numeric(18,2)`, `Numeric(18,8)`, `DateTime`, `DateTime`.
- **Indexes**: `id`, `created_at`, `updated_at`.
- **Constraints**: Primary Key on `id`, Check Constraints ensuring `available_cash >= 0` and `reserved_cash >= 0`.
- **Relationships**: Parent to `live_positions` and `live_orders`.
- **Used Services**: Live Trading Engine, Account Manager.
- **Data Lifecycle**: Highly durable, updated on execution events, deposits.
- **Example Records**:
  ```json
  {"id": 1, "name": "Primary Live Account", "available_cash": 100000.0, "reserved_cash": 0.0}
  ```

## Table: `live_positions`
- **Purpose**: Stores active and closed positions currently held in a live account.
- **Columns**: `id`, `account_id`, `status`, `symbol`, `qty`, `avg_entry_price`, `current_price`, `realized_pnl`, `unrealized_pnl`, `created_at`, `updated_at`.
- **Types**: `Integer`, `Integer`, `String(16)`, `String(32)`, `Numeric(18,8)`, `Numeric(18,8)`, `Numeric(18,8)`, `Numeric(18,2)`, `Numeric(18,2)`, `DateTime`, `DateTime`.
- **Indexes**: `id`, `account_id`, `status`, `symbol`, `created_at`, `updated_at`, partial unique index on open positions (`account_id`, `symbol`).
- **Constraints**: Primary Key on `id`, Foreign Key `account_id` -> `live_accounts.id`.
- **Relationships**: Belongs to `LiveAccount`.
- **Used Services**: Live Trading Engine, Risk Manager.
- **Data Lifecycle**: Created on position open, updated on market ticks and execution, status changed on exit.
- **Example Records**:
  ```json
  {"id": 1, "account_id": 1, "status": "OPEN", "symbol": "INFY", "qty": 50, "realized_pnl": 0.0}
  ```

## Table: `live_orders`
- **Purpose**: The absolute source of truth for orders sent to the live broker.
- **Columns**: `id`, `execution_id`, `account_id`, `symbol`, `side`, `order_type`, `product_type`, `requested_qty`, `filled_qty`, `order_price`, `stop_price`, `status`, `idempotency_key`, `broker_request_id`, `broker_order_id`, `reconciliation_attempts`, `next_reconcile_at`, `created_at`, `updated_at`, `filled_at`, `cancelled_at`.
- **Types**: `Integer`, `String(36)`, `Integer`, `String(32)`, `String(8)`, `String(12)`, `String(8)`, `Numeric`, `Numeric`, `Numeric`, `Numeric`, `String(32)`, `String(128)`, `String(64)`, `String(64)`, `Integer`, `DateTime`, `DateTime`, `DateTime`, `DateTime`, `DateTime`.
- **Indexes**: Includes constraints and indexing for reconciliation, unique `execution_id`, `idempotency_key`.
- **Constraints**: Primary Key on `id`, Foreign Key `account_id`, Check constraint on allowed statuses.
- **Relationships**: Belongs to `LiveAccount`, has many `OrderExecutionEvent`.
- **Used Services**: Order Management System, Broker Reconciliation.
- **Data Lifecycle**: Created, updated via broker callbacks and state machines. Retained forever.
- **Example Records**:
  ```json
  {"id": 1, "status": "FILLED", "symbol": "HDFC", "requested_qty": 100, "filled_qty": 100}
  ```

## Table: `order_execution_events`
- **Purpose**: An append-only ledger for every state transition or broker callback relating to an order.
- **Columns**: `id`, `order_id`, `event_type`, `previous_state`, `new_state`, `reason`, `metadata_json`, `correlation_id`, `created_by`, `event_timestamp`, `created_at`.
- **Types**: `Integer`, `Integer`, `String(32)`, `String(32)`, `String(32)`, `String(256)`, `JSONB`, `String(128)`, `String(64)`, `DateTime`, `DateTime`.
- **Indexes**: `id`, `order_id`, `event_type`, `correlation_id`, `event_timestamp`.
- **Constraints**: Primary Key on `id`, Foreign Key `order_id`.
- **Relationships**: `LiveOrder`.
- **Used Services**: Event Sourcing layer, Reconciliation loops.
- **Data Lifecycle**: Append only. Never updated or deleted.
- **Example Records**:
  ```json
  {"order_id": 1, "event_type": "STATE_TRANSITION", "previous_state": "CREATED", "new_state": "BROKER_ACCEPTED"}
  ```

## Table: `broker_execution_logs`
- **Purpose**: Raw dumps of trade executions exactly as the broker reported them.
- **Columns**: `broker_trade_id`, `broker_order_id`, `execution_timestamp`, `side`, `qty`, `price`, `payload_hash`, `received_at`.
- **Types**: `String(128)`, `String(64)`, `DateTime`, `String(8)`, `Numeric`, `Numeric`, `String(64)`, `DateTime`.
- **Indexes**: Primary Key on `broker_trade_id`, index on `broker_order_id`.
- **Constraints**: Primary Key on `broker_trade_id`.
- **Relationships**: Connects to `LiveOrder` via `broker_order_id`.
- **Used Services**: Webhook Receiver, Broker Sync.
- **Data Lifecycle**: Append only log of incoming payloads.
- **Example Records**:
  ```json
  {"broker_trade_id": "trade123", "broker_order_id": "ord123", "qty": 10, "price": 1050.25}
  ```

## Table: `blacklisted_symbols`
- **Purpose**: Prevents the system from trading or analyzing particular instruments.
- **Columns**: `symbol`, `reason`, `created_at`.
- **Types**: `String(50)`, `Text`, `DateTime`.
- **Indexes**: Primary Key on `symbol`, index on `created_at`.
- **Constraints**: Primary Key on `symbol`.
- **Relationships**: Referenced as exclusions.
- **Used Services**: Screener, Market Engine.
- **Data Lifecycle**: Administratively managed.
- **Example Records**:
  ```json
  {"symbol": "IDEA", "reason": "Low liquidity, highly volatile.", "created_at": "2026-06-07T12:00:00Z"}
  ```

## Table: `historical_candles`
- **Purpose**: Core market data table storing OHLCV candlestick data for analytics.
- **Columns**: `id`, `symbol`, `resolution`, `timestamp`, `open`, `high`, `low`, `close`, `volume`, `source`, `created_at`, `updated_at`.
- **Types**: `Integer`, `String(50)`, `String(20)`, `DateTime`, `Numeric`, `Numeric`, `Numeric`, `Numeric`, `Numeric`, `String(20)`, `DateTime`, `DateTime`.
- **Indexes**: Unique constraints on composite `symbol`, `resolution`, `timestamp`.
- **Constraints**: Primary Key on `id`, Unique constraint `uq_historical_candle`.
- **Relationships**: Independent market data.
- **Used Services**: Backtest Engine, Charting, Analysis Engine.
- **Data Lifecycle**: Backfilled on-demand and incrementally fetched. Kept long-term.
- **Example Records**:
  ```json
  {"symbol": "NIFTY50", "resolution": "1D", "timestamp": "2026-06-07T00:00:00Z", "close": 23000.0}
  ```

## Table: `latest_scan_results`
- **Purpose**: Rapid access caching of the most recent screener outputs.
- **Columns**: `id`, `symbol`, `signal_type`, `score`, `confidence`, `scanned_at`, `created_at`, `updated_at`.
- **Types**: `Integer`, `String(50)`, `String(50)`, `Numeric`, `Numeric`, `DateTime`, `DateTime`, `DateTime`.
- **Indexes**: Unique on `symbol`, index on `scanned_at`.
- **Constraints**: Primary Key on `id`.
- **Relationships**: Overwritten per symbol.
- **Used Services**: Dashboard, Market Scanner.
- **Data Lifecycle**: Repeatedly UPSERTED on new scan cycles.
- **Example Records**:
  ```json
  {"symbol": "WIPRO", "signal_type": "BULLISH_BREAKOUT", "score": 88.5, "confidence": 0.8}
  ```

## Table: `scan_snapshots` & `scan_snapshot_records`
- **Purpose**: Preserves full historical point-in-time outputs of the market screener for auditing.
- **Columns (`scan_snapshots`)**: `id`, `scan_id`, `scan_timestamp`, `scan_duration_ms`, `total_scanned`, `valid_symbols`, `buy_count`, `watch_count`, `rejected_count`, `created_at`.
- **Columns (`scan_snapshot_records`)**: `id`, `scan_id`, `symbol`, `recommendation`, `score`, `close_price`, `sma50`, `sma200`, `rsi`, `macd`, `volume`, `reason`, `created_at`.
- **Types**: Standard Int, String, Numeric mappings.
- **Indexes**: `scan_id` (Unique and Indexed).
- **Constraints**: `scan_id` references `scan_snapshots.scan_id` via Cascade.
- **Relationships**: 1:N between Snapshot and Records.
- **Used Services**: Audit, Replay systems, Screener.
- **Data Lifecycle**: Append only.
- **Example Records**:
  ```json
  {"scan_id": "scan_abc123", "total_scanned": 500, "buy_count": 15}
  ```

## Table: `scanner_sessions` & `scanner_symbol_tracking`
- **Purpose**: Tracks long-running background processes scanning the market.
- **Columns (`scanner_sessions`)**: `session_id`, `status`, `started_at`, `completed_at`, `progress_percentage`, `symbols_total`, `symbols_completed`, `symbols_failed`, `current_symbol`, `created_at`, `updated_at`.
- **Columns (`scanner_symbol_tracking`)**: `id`, `session_id`, `symbol`, `status`, `retry_count`, `last_error`, `worker_id`, `processed_at`, `created_at`, `updated_at`.
- **Constraints**: FK session_id -> scanner_sessions. Unique (session_id, symbol).
- **Data Lifecycle**: Updated incrementally by workers in real-time. Archived/Cleaned over time.
- **Example Records**:
  ```json
  {"session_id": "sesh123", "status": "IN_PROGRESS", "progress_percentage": 45}
  ```

## Table: `system_locks`
- **Purpose**: Provides distributed locking for system chron jobs and workers.
- **Columns**: `lock_name`, `locked_by`, `locked_at`, `expires_at`, `heartbeat_at`.
- **Types**: `String`, `String`, `DateTime`, `DateTime`, `DateTime`.
- **Indexes**: Primary Key on `lock_name`.
- **Data Lifecycle**: High churn. Acquired, updated, released aggressively.
- **Example Records**:
  ```json
  {"lock_name": "market_sync", "locked_by": "worker-1", "expires_at": "2026-06-07T12:05:00Z"}
  ```

## Table: `paper_trading_accounts`, `paper_trading_positions`, `paper_trading_orders`, `paper_trading_trade_history`, `paper_trading_transactions`, `paper_trading_execution_events`
- **Purpose**: Provide a risk-free simulated environment exactly matching the schema of live trading.
- **Columns**: Identical mirror to their `live_*` equivalents, with additions like `monitor_enabled`, `lifecycle_state`, `source_signal`, `source_score`.
- **Types**: Similar Integer, String, Numeric setups as live.
- **Constraints**: FK mapping identical to live. Events table enforces append-only via SQLAlchemy event listeners.
- **Used Services**: Paper Trading Engine, Market Engine Session.
- **Data Lifecycle**: Controlled entirely by simulated ticking and internal matching engine.
- **Example Records**:
  ```json
  {"id": 1, "account_id": 1, "symbol": "RELIANCE", "qty": 10, "status": "OPEN", "unrealized_pnl": 55.0}
  ```

## Table: `market_engine_sessions` & `market_replay_sessions`
- **Purpose**: Represents active market data consumption periods (realtime streaming or backtest replay).
- **Columns (`market_engine_sessions`)**: `id`, `trading_date`, `status`, `started_at`, `websocket_connected`, `monitored_symbols_count`, etc.
- **Constraints**: Unique constraint on `trading_date`.
- **Used Services**: Ticker Stream, Scheduler.
- **Data Lifecycle**: Represents a trading day lifecycle.
- **Example Records**:
  ```json
  {"trading_date": "2026-06-07", "status": "RUNNING", "websocket_connected": true}
  ```

## Table: `watched_stocks`
- **Purpose**: Core catalogue mapping internal representation to exchange symbols.
- **Columns**: `id`, `symbol`, `display_name`, `created_at`.
- **Indexes**: Unique on `symbol`.
- **Constraints**: Primary Key on `id`.
- **Relationships**: Connected to `analysis_history`, `backtest_history`.
- **Data Lifecycle**: Slowly changing dimension.
- **Example Records**:
  ```json
  {"id": 1, "symbol": "INFY", "display_name": "Infosys Ltd."}
  ```

## Table: `system_logs`
- **Purpose**: Persisted application, audit, and error logs directly queryable in DB.
- **Columns**: `id`, `timestamp`, `level`, `source`, `module`, `endpoint`, `message`, `error_hash`, `traceback`, `structured_data` (JSON), `correlationId`, `userId`, `symbol`, `orderId`, `environment`, `created_at`.
- **Indexes**: Extensive indexing on correlation factors (`correlationId`, `symbol`, `level`).
- **Used Services**: Observability, Admin UI.
- **Data Lifecycle**: Append-only. Periodically truncated via TTL jobs.
- **Example Records**:
  ```json
  {"level": "ERROR", "module": "live_trading.execution", "message": "Connection timeout", "environment": "PROD"}
  ```

## Table: `dead_letter_jobs`
- **Purpose**: Stores failed asynchronous background tasks for manual intervention.
- **Columns**: `id`, `job_name`, `payload`, `error_message`, `retry_count`, `failed_at`, `created_at`.
- **Types**: Payload is JSON type.
- **Used Services**: Background Job Processor.
- **Data Lifecycle**: Retried and deleted, or manual inspection.
- **Example Records**:
  ```json
  {"job_name": "SEND_WEBHOOK", "retry_count": 3, "failed_at": "2026-06-07T12:00:00Z"}
  ```

## Table: `api_request_logs`
- **Purpose**: Logs external provider requests (latency, status codes).
- **Columns**: `id`, `provider`, `endpoint`, `status_code`, `latency_ms`, `error_message`, `created_at`.
- **Used Services**: HTTP Interceptors.
- **Data Lifecycle**: Append only.
- **Example Records**:
  ```json
  {"provider": "FYERS", "endpoint": "/orders", "latency_ms": 150, "status_code": 200}
  ```

## Table: `service_health`
- **Purpose**: Sub-component heartbeat table.
- **Columns**: `service_name`, `status`, `last_heartbeat`, `metadata_json`, `created_at`, `updated_at`.
- **Constraints**: Primary Key on `service_name`.
- **Data Lifecycle**: Heartbeat updated continuously.
- **Example Records**:
  ```json
  {"service_name": "worker_node_1", "status": "HEALTHY", "last_heartbeat": "2026-06-07T12:00:00Z"}
  ```

## Table: `saved_scans`, `scan_history_snapshots`, `workstation_alerts`, `risk_settings`
- **Purpose**: User-facing configurations (workstation presets, UI settings, alerts).
- **Columns**: E.g. `saved_scans` contains `name`, `mode`, `timeframe`, `universe`, `filters_json`.
- **Used Services**: Workstation / Frontend UI.
- **Data Lifecycle**: User controlled configurations (CRUD).
- **Example Records**:
  ```json
  {"name": "Bullish Reversal", "mode": "swing", "timeframe": "1d", "universe": "NIFTY500"}
  ```

## Table: `alembic_version`
- **Purpose**: Tracks the database migration state natively via Alembic.
- **Columns**: `version_num` (String, Primary Key).
- **Used Services**: Alembic.
- **Data Lifecycle**: Changed on DB migrate.
- **Example Records**:
  ```json
  {"version_num": "6650a54dd6aa"}
  ```
