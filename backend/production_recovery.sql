-- ==========================================================
-- PHASE 3 PRE-STAMP RECOVERY SCRIPT
-- Generated dynamically from Alembic schema comparison
-- ==========================================================

-- Table missing: latest_scan_results
CREATE TABLE IF NOT EXISTS latest_scan_results (
	id SERIAL NOT NULL, 
	symbol VARCHAR(50) NOT NULL, 
	signal_type VARCHAR(50) NOT NULL, 
	score NUMERIC(18, 8), 
	confidence NUMERIC(18, 8), 
	scanned_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_latest_scan_results PRIMARY KEY (id), 
	CONSTRAINT uq_latest_scan_results_symbol UNIQUE (symbol)
);

-- Index missing: ix_latest_scan_results_created_at
CREATE INDEX IF NOT EXISTS ix_latest_scan_results_created_at ON latest_scan_results (created_at);

-- Index missing: ix_latest_scan_results_id
CREATE INDEX IF NOT EXISTS ix_latest_scan_results_id ON latest_scan_results (id);

-- Index missing: ix_latest_scan_results_scanned_at
CREATE INDEX IF NOT EXISTS ix_latest_scan_results_scanned_at ON latest_scan_results (scanned_at);

-- Index missing: ix_latest_scan_results_updated_at
CREATE INDEX IF NOT EXISTS ix_latest_scan_results_updated_at ON latest_scan_results (updated_at);

-- Table missing: market_engine_sessions
CREATE TABLE IF NOT EXISTS market_engine_sessions (
	id SERIAL NOT NULL, 
	trading_date VARCHAR(10) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	requested_start_at TIMESTAMP WITH TIME ZONE, 
	started_at TIMESTAMP WITH TIME ZONE, 
	stopped_at TIMESTAMP WITH TIME ZONE, 
	last_heartbeat_at TIMESTAMP WITH TIME ZONE, 
	last_tick_at TIMESTAMP WITH TIME ZONE, 
	websocket_connected BOOLEAN DEFAULT false NOT NULL, 
	token_status VARCHAR(32) NOT NULL, 
	paused_reason VARCHAR(64), 
	monitored_symbols_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_market_engine_sessions PRIMARY KEY (id), 
	CONSTRAINT uq_market_engine_session_trading_date UNIQUE (trading_date)
);

-- Index missing: ix_market_engine_sessions_created_at
CREATE INDEX IF NOT EXISTS ix_market_engine_sessions_created_at ON market_engine_sessions (created_at);

-- Index missing: ix_market_engine_sessions_id
CREATE INDEX IF NOT EXISTS ix_market_engine_sessions_id ON market_engine_sessions (id);

-- Index missing: ix_market_engine_sessions_status
CREATE INDEX IF NOT EXISTS ix_market_engine_sessions_status ON market_engine_sessions (status);

-- Index missing: ix_market_engine_sessions_trading_date
CREATE INDEX IF NOT EXISTS ix_market_engine_sessions_trading_date ON market_engine_sessions (trading_date);

-- Index missing: ix_market_engine_sessions_updated_at
CREATE INDEX IF NOT EXISTS ix_market_engine_sessions_updated_at ON market_engine_sessions (updated_at);

-- Table missing: market_replay_sessions
CREATE TABLE IF NOT EXISTS market_replay_sessions (
	id SERIAL NOT NULL, 
	replay_key VARCHAR(160) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	gap_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	gap_end TIMESTAMP WITH TIME ZONE NOT NULL, 
	checkpoint_symbol VARCHAR(32), 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	error_message TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_market_replay_sessions PRIMARY KEY (id)
);

-- Index missing: ix_market_replay_sessions_created_at
CREATE INDEX IF NOT EXISTS ix_market_replay_sessions_created_at ON market_replay_sessions (created_at);

-- Index missing: ix_market_replay_sessions_gap_end
CREATE INDEX IF NOT EXISTS ix_market_replay_sessions_gap_end ON market_replay_sessions (gap_end);

-- Index missing: ix_market_replay_sessions_gap_start
CREATE INDEX IF NOT EXISTS ix_market_replay_sessions_gap_start ON market_replay_sessions (gap_start);

-- Index missing: ix_market_replay_sessions_id
CREATE INDEX IF NOT EXISTS ix_market_replay_sessions_id ON market_replay_sessions (id);

-- Index missing: ix_market_replay_sessions_replay_key
CREATE UNIQUE INDEX ix_market_replay_sessions_replay_key ON market_replay_sessions (replay_key);

-- Index missing: ix_market_replay_sessions_started_at
CREATE INDEX IF NOT EXISTS ix_market_replay_sessions_started_at ON market_replay_sessions (started_at);

-- Index missing: ix_market_replay_sessions_status
CREATE INDEX IF NOT EXISTS ix_market_replay_sessions_status ON market_replay_sessions (status);

-- Index missing: ix_market_replay_sessions_updated_at
CREATE INDEX IF NOT EXISTS ix_market_replay_sessions_updated_at ON market_replay_sessions (updated_at);

-- Table missing: paper_trading_execution_events
CREATE TABLE IF NOT EXISTS paper_trading_execution_events (
	id SERIAL NOT NULL, 
	event_id VARCHAR(36) NOT NULL, 
	event_type VARCHAR(48) NOT NULL, 
	symbol VARCHAR(32), 
	order_id INTEGER, 
	position_id INTEGER, 
	from_state VARCHAR(32), 
	to_state VARCHAR(32), 
	price NUMERIC(18, 8), 
	message TEXT, 
	dedupe_key VARCHAR(128), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_paper_trading_execution_events PRIMARY KEY (id), 
	CONSTRAINT uq_execution_event_dedupe UNIQUE (dedupe_key)
);

-- Index missing: idx_execution_events_order_type
CREATE INDEX IF NOT EXISTS idx_execution_events_order_type ON paper_trading_execution_events (order_id, event_type);

-- Index missing: idx_execution_events_position_type
CREATE INDEX IF NOT EXISTS idx_execution_events_position_type ON paper_trading_execution_events (position_id, event_type);

-- Index missing: ix_paper_trading_execution_events_created_at
CREATE INDEX IF NOT EXISTS ix_paper_trading_execution_events_created_at ON paper_trading_execution_events (created_at);

-- Index missing: ix_paper_trading_execution_events_dedupe_key
CREATE INDEX IF NOT EXISTS ix_paper_trading_execution_events_dedupe_key ON paper_trading_execution_events (dedupe_key);

-- Index missing: ix_paper_trading_execution_events_event_id
CREATE UNIQUE INDEX ix_paper_trading_execution_events_event_id ON paper_trading_execution_events (event_id);

-- Index missing: ix_paper_trading_execution_events_event_type
CREATE INDEX IF NOT EXISTS ix_paper_trading_execution_events_event_type ON paper_trading_execution_events (event_type);

-- Index missing: ix_paper_trading_execution_events_id
CREATE INDEX IF NOT EXISTS ix_paper_trading_execution_events_id ON paper_trading_execution_events (id);

-- Index missing: ix_paper_trading_execution_events_order_id
CREATE INDEX IF NOT EXISTS ix_paper_trading_execution_events_order_id ON paper_trading_execution_events (order_id);

-- Index missing: ix_paper_trading_execution_events_position_id
CREATE INDEX IF NOT EXISTS ix_paper_trading_execution_events_position_id ON paper_trading_execution_events (position_id);

-- Index missing: ix_paper_trading_execution_events_symbol
CREATE INDEX IF NOT EXISTS ix_paper_trading_execution_events_symbol ON paper_trading_execution_events (symbol);

-- Index missing: ix_paper_trading_execution_events_updated_at
CREATE INDEX IF NOT EXISTS ix_paper_trading_execution_events_updated_at ON paper_trading_execution_events (updated_at);

-- Table missing: scan_snapshots
CREATE TABLE IF NOT EXISTS scan_snapshots (
	id SERIAL NOT NULL, 
	scan_id VARCHAR(36) NOT NULL, 
	scan_timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
	scan_duration_ms INTEGER NOT NULL, 
	total_scanned INTEGER NOT NULL, 
	valid_symbols INTEGER NOT NULL, 
	buy_count INTEGER NOT NULL, 
	watch_count INTEGER NOT NULL, 
	rejected_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_scan_snapshots PRIMARY KEY (id)
);

-- Index missing: ix_scan_snapshots_id
CREATE INDEX IF NOT EXISTS ix_scan_snapshots_id ON scan_snapshots (id);

-- Index missing: ix_scan_snapshots_scan_id
CREATE UNIQUE INDEX ix_scan_snapshots_scan_id ON scan_snapshots (scan_id);

-- Index missing: ix_scan_snapshots_scan_timestamp
CREATE INDEX IF NOT EXISTS ix_scan_snapshots_scan_timestamp ON scan_snapshots (scan_timestamp);

-- Table missing: scanned_candidates
CREATE TABLE IF NOT EXISTS scanned_candidates (
	id SERIAL NOT NULL, 
	symbol VARCHAR(25) NOT NULL, 
	scanned_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	screener_name VARCHAR(100) NOT NULL, 
	technical_score FLOAT, 
	technical_signal VARCHAR(20), 
	screener_score FLOAT, 
	matched BOOLEAN NOT NULL, 
	CONSTRAINT pk_scanned_candidates PRIMARY KEY (id)
);

-- Index missing: ix_scanned_candidates_id
CREATE INDEX IF NOT EXISTS ix_scanned_candidates_id ON scanned_candidates (id);

-- Index missing: ix_scanned_candidates_scanned_at
CREATE INDEX IF NOT EXISTS ix_scanned_candidates_scanned_at ON scanned_candidates (scanned_at);

-- Index missing: ix_scanned_candidates_symbol
CREATE INDEX IF NOT EXISTS ix_scanned_candidates_symbol ON scanned_candidates (symbol);

-- Table missing: scanner_sessions
CREATE TABLE IF NOT EXISTS scanner_sessions (
	session_id VARCHAR(36) NOT NULL, 
	status VARCHAR(20), 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	progress_percentage INTEGER, 
	symbols_total INTEGER, 
	symbols_completed INTEGER, 
	symbols_failed INTEGER, 
	current_symbol VARCHAR(50), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_scanner_sessions PRIMARY KEY (session_id)
);

-- Index missing: ix_scanner_sessions_created_at
CREATE INDEX IF NOT EXISTS ix_scanner_sessions_created_at ON scanner_sessions (created_at);

-- Index missing: ix_scanner_sessions_updated_at
CREATE INDEX IF NOT EXISTS ix_scanner_sessions_updated_at ON scanner_sessions (updated_at);

-- Table missing: strategy_performance_log
CREATE TABLE IF NOT EXISTS strategy_performance_log (
	id SERIAL NOT NULL, 
	symbol VARCHAR(25) NOT NULL, 
	screened_date TIMESTAMP WITH TIME ZONE NOT NULL, 
	initial_score FLOAT NOT NULL, 
	dominant_agent VARCHAR(50) NOT NULL, 
	realized_return_5d FLOAT, 
	realized_return_10d FLOAT, 
	realized_return_20d FLOAT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_strategy_performance_log PRIMARY KEY (id)
);

-- Index missing: ix_strategy_performance_log_id
CREATE INDEX IF NOT EXISTS ix_strategy_performance_log_id ON strategy_performance_log (id);

-- Index missing: ix_strategy_performance_log_screened_date
CREATE INDEX IF NOT EXISTS ix_strategy_performance_log_screened_date ON strategy_performance_log (screened_date);

-- Index missing: ix_strategy_performance_log_symbol
CREATE INDEX IF NOT EXISTS ix_strategy_performance_log_symbol ON strategy_performance_log (symbol);

-- Table missing: system_logs
CREATE TABLE IF NOT EXISTS system_logs (
	id SERIAL NOT NULL, 
	timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
	level VARCHAR, 
	source VARCHAR, 
	module VARCHAR, 
	endpoint VARCHAR, 
	message VARCHAR, 
	error_hash VARCHAR, 
	traceback TEXT, 
	structured_data JSON, 
	"correlationId" VARCHAR, 
	"userId" VARCHAR, 
	symbol VARCHAR, 
	"orderId" VARCHAR, 
	environment VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_system_logs PRIMARY KEY (id)
);

-- Index missing: ix_system_logs_correlationId
CREATE INDEX IF NOT EXISTS "ix_system_logs_correlationId" ON system_logs ("correlationId");

-- Index missing: ix_system_logs_created_at
CREATE INDEX IF NOT EXISTS ix_system_logs_created_at ON system_logs (created_at);

-- Index missing: ix_system_logs_environment
CREATE INDEX IF NOT EXISTS ix_system_logs_environment ON system_logs (environment);

-- Index missing: ix_system_logs_error_hash
CREATE INDEX IF NOT EXISTS ix_system_logs_error_hash ON system_logs (error_hash);

-- Index missing: ix_system_logs_id
CREATE INDEX IF NOT EXISTS ix_system_logs_id ON system_logs (id);

-- Index missing: ix_system_logs_level
CREATE INDEX IF NOT EXISTS ix_system_logs_level ON system_logs (level);

-- Index missing: ix_system_logs_module
CREATE INDEX IF NOT EXISTS ix_system_logs_module ON system_logs (module);

-- Index missing: ix_system_logs_orderId
CREATE INDEX IF NOT EXISTS "ix_system_logs_orderId" ON system_logs ("orderId");

-- Index missing: ix_system_logs_source
CREATE INDEX IF NOT EXISTS ix_system_logs_source ON system_logs (source);

-- Index missing: ix_system_logs_symbol
CREATE INDEX IF NOT EXISTS ix_system_logs_symbol ON system_logs (symbol);

-- Index missing: ix_system_logs_timestamp
CREATE INDEX IF NOT EXISTS ix_system_logs_timestamp ON system_logs (timestamp);

-- Index missing: ix_system_logs_userId
CREATE INDEX IF NOT EXISTS "ix_system_logs_userId" ON system_logs ("userId");

-- Table missing: scan_snapshot_records
CREATE TABLE IF NOT EXISTS scan_snapshot_records (
	id SERIAL NOT NULL, 
	scan_id VARCHAR(36) NOT NULL, 
	symbol VARCHAR(50) NOT NULL, 
	recommendation VARCHAR(20) NOT NULL, 
	score NUMERIC(18, 8) NOT NULL, 
	close_price NUMERIC(18, 8) NOT NULL, 
	sma50 NUMERIC(18, 8), 
	sma200 NUMERIC(18, 8), 
	rsi NUMERIC(18, 8), 
	macd NUMERIC(18, 8), 
	volume INTEGER, 
	reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_scan_snapshot_records PRIMARY KEY (id), 
	CONSTRAINT fk_scan_snapshot_records_scan_id_scan_snapshots FOREIGN KEY(scan_id) REFERENCES scan_snapshots (scan_id) ON DELETE CASCADE
);

-- Index missing: ix_scan_snapshot_records_id
CREATE INDEX IF NOT EXISTS ix_scan_snapshot_records_id ON scan_snapshot_records (id);

-- Index missing: ix_scan_snapshot_records_scan_id
CREATE INDEX IF NOT EXISTS ix_scan_snapshot_records_scan_id ON scan_snapshot_records (scan_id);

-- Index missing: ix_scan_snapshot_records_symbol
CREATE INDEX IF NOT EXISTS ix_scan_snapshot_records_symbol ON scan_snapshot_records (symbol);

-- Table missing: scanner_symbol_tracking
CREATE TABLE IF NOT EXISTS scanner_symbol_tracking (
	id SERIAL NOT NULL, 
	session_id VARCHAR(36) NOT NULL, 
	symbol VARCHAR(50) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	retry_count INTEGER, 
	last_error TEXT, 
	worker_id VARCHAR(100), 
	processed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_scanner_symbol_tracking PRIMARY KEY (id), 
	CONSTRAINT uq_scanner_session_symbol UNIQUE (session_id, symbol), 
	CONSTRAINT fk_scanner_symbol_tracking_session_id_scanner_sessions FOREIGN KEY(session_id) REFERENCES scanner_sessions (session_id) ON DELETE CASCADE
);

-- Index missing: ix_scanner_symbol_tracking_created_at
CREATE INDEX IF NOT EXISTS ix_scanner_symbol_tracking_created_at ON scanner_symbol_tracking (created_at);

-- Index missing: ix_scanner_symbol_tracking_id
CREATE INDEX IF NOT EXISTS ix_scanner_symbol_tracking_id ON scanner_symbol_tracking (id);

-- Index missing: ix_scanner_symbol_tracking_updated_at
CREATE INDEX IF NOT EXISTS ix_scanner_symbol_tracking_updated_at ON scanner_symbol_tracking (updated_at);

-- Column missing: paper_trading_notifications.event_type
ALTER TABLE paper_trading_notifications ADD COLUMN IF NOT EXISTS event_type VARCHAR(48);

-- Column missing: paper_trading_notifications.entity_type
ALTER TABLE paper_trading_notifications ADD COLUMN IF NOT EXISTS entity_type VARCHAR(32);

-- Column missing: paper_trading_notifications.entity_id
ALTER TABLE paper_trading_notifications ADD COLUMN IF NOT EXISTS entity_id INTEGER;

-- Column missing: paper_trading_notifications.dedupe_key
ALTER TABLE paper_trading_notifications ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(128);

-- Index missing: ix_paper_trading_notifications_dedupe_key
CREATE INDEX IF NOT EXISTS ix_paper_trading_notifications_dedupe_key ON paper_trading_notifications (dedupe_key);

-- Index missing: ix_paper_trading_notifications_event_type
CREATE INDEX IF NOT EXISTS ix_paper_trading_notifications_event_type ON paper_trading_notifications (event_type);

-- Column missing: paper_trading_orders.lifecycle_state
ALTER TABLE paper_trading_orders ADD COLUMN IF NOT EXISTS lifecycle_state VARCHAR(32);

-- Column missing: paper_trading_orders.requested_entry_price
ALTER TABLE paper_trading_orders ADD COLUMN IF NOT EXISTS requested_entry_price NUMERIC(18, 8);

-- Column missing: paper_trading_orders.monitor_enabled
ALTER TABLE paper_trading_orders ADD COLUMN IF NOT EXISTS monitor_enabled BOOLEAN DEFAULT true;

-- Column missing: paper_trading_orders.paused_reason
ALTER TABLE paper_trading_orders ADD COLUMN IF NOT EXISTS paused_reason VARCHAR(64);

-- Column missing: paper_trading_orders.last_evaluated_at
ALTER TABLE paper_trading_orders ADD COLUMN IF NOT EXISTS last_evaluated_at TIMESTAMP WITH TIME ZONE;

-- Column missing: paper_trading_orders.last_seen_ltp
ALTER TABLE paper_trading_orders ADD COLUMN IF NOT EXISTS last_seen_ltp NUMERIC(18, 8);

-- Column missing: paper_trading_orders.idempotency_key
ALTER TABLE paper_trading_orders ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128);

-- Column missing: paper_trading_orders.updated_at
ALTER TABLE paper_trading_orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE;

-- Index missing: idx_orders_account_status_created
CREATE INDEX IF NOT EXISTS idx_orders_account_status_created ON paper_trading_orders (account_id, status, created_at);

-- Index missing: idx_orders_active_symbol
CREATE INDEX IF NOT EXISTS idx_orders_active_symbol ON paper_trading_orders (symbol, status, lifecycle_state, monitor_enabled);

-- Index missing: ix_paper_trading_orders_idempotency_key
CREATE UNIQUE INDEX ix_paper_trading_orders_idempotency_key ON paper_trading_orders (idempotency_key);

-- Index missing: ix_paper_trading_orders_lifecycle_state
CREATE INDEX IF NOT EXISTS ix_paper_trading_orders_lifecycle_state ON paper_trading_orders (lifecycle_state);

-- Index missing: ix_paper_trading_orders_updated_at
CREATE INDEX IF NOT EXISTS ix_paper_trading_orders_updated_at ON paper_trading_orders (updated_at);

-- Column missing: paper_trading_positions.lifecycle_state
ALTER TABLE paper_trading_positions ADD COLUMN IF NOT EXISTS lifecycle_state VARCHAR(32);

-- Column missing: paper_trading_positions.realized_pnl
ALTER TABLE paper_trading_positions ADD COLUMN IF NOT EXISTS realized_pnl NUMERIC(18, 2);

-- Column missing: paper_trading_positions.unrealized_pnl
ALTER TABLE paper_trading_positions ADD COLUMN IF NOT EXISTS unrealized_pnl NUMERIC(18, 2);

-- Column missing: paper_trading_positions.monitor_enabled
ALTER TABLE paper_trading_positions ADD COLUMN IF NOT EXISTS monitor_enabled BOOLEAN DEFAULT true;

-- Column missing: paper_trading_positions.paused_reason
ALTER TABLE paper_trading_positions ADD COLUMN IF NOT EXISTS paused_reason VARCHAR(64);

-- Index missing: idx_positions_active_symbol
CREATE INDEX IF NOT EXISTS idx_positions_active_symbol ON paper_trading_positions (symbol, status, lifecycle_state, monitor_enabled);

-- Index missing: idx_unique_open_position
CREATE UNIQUE INDEX idx_unique_open_position ON paper_trading_positions (account_id, symbol) WHERE status = 'OPEN';

-- Index missing: ix_paper_trading_positions_lifecycle_state
CREATE INDEX IF NOT EXISTS ix_paper_trading_positions_lifecycle_state ON paper_trading_positions (lifecycle_state);

-- Column missing: paper_trading_trade_history.created_at
ALTER TABLE paper_trading_trade_history ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE;

-- Column missing: paper_trading_trade_history.updated_at
ALTER TABLE paper_trading_trade_history ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE;

-- Index missing: ix_paper_trading_trade_history_created_at
CREATE INDEX IF NOT EXISTS ix_paper_trading_trade_history_created_at ON paper_trading_trade_history (created_at);

-- Index missing: ix_paper_trading_trade_history_updated_at
CREATE INDEX IF NOT EXISTS ix_paper_trading_trade_history_updated_at ON paper_trading_trade_history (updated_at);

-- ==========================================================
-- END OF RECOVERY SCRIPT
-- ==========================================================
