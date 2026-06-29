# Phase F.0 Shadow Run Plan

## Objective
Execute a comprehensive, production-grade Shadow Run phase to validate the robustness, stability, and correctness of the entire trading system operating in a simulated live environment under real market conditions.

## System Analysis & Identified Risks

1. **Scheduler Jobs & Background Workers**
   - *Architecture:* Handled by `APScheduler` alongside `market_engine` loops. Multiple nodes are restricted via `acquire_singleton_lease`.
   - *Scheduler Duplication Risk:* Mitigated by the singleton lease, but must validate that lease handover operates flawlessly if a pod dies.
   - *Silent Failure Risk:* If `TaskSupervisor` drops a critical background task (like `market_engine` loop) without crashing the application, it could lead to silent data stagnation.

2. **Scanner & FYERS Data Flow**
   - *Architecture:* Orchestrator pulls from Fyers, computes technicals, requests LLM recommendations, and persists the final response.
   - *Retry Storm Risk:* If FYERS rate limits are hit during a 500-symbol backfill, aggressive parallel retries could trigger an extended API block.
   - *Stale Data Risk:* Network drops during early morning initialization could leave the scanner operating on previous-day data.

3. **Paper Trading Flow**
   - *Architecture:* Order executions track against real-time market LTP. Offline gap fills are processed via `gap_replay` upon startup.
   - *Risk:* Slippage models might misbehave if LTP spikes drastically in a single tick.

4. **Dashboard & WebSockets**
   - *Architecture:* React frontend loads snapshot via `GET /scanner/latest` instantly, then subscribes to `ws://.../ws/ticks` for live pricing.
   - *WebSocket Risk:* High tick volume causing frontend rendering freezes, or silent connection drops failing to re-establish.

5. **Database & Cache Flow**
   - *Architecture:* PostgreSQL handles system logs, candidate records, order tickets, and scan snapshots.
   - *Database Growth Risk:* Generating ~150-300 records daily per scan plus heavy `system_logs` will bloat the database if `job_retention_cleanup` does not explicitly prune `scan_snapshots` and `scan_snapshot_records`.
   - *Memory Leak Risk:* Cache dictionaries unbounded growth in `market_engine`.

---

## F0.1 Shadow Run Preparation
- Initialize clean shadow database.
- Rotate and validate fresh FYERS API access token.
- Validate configuration secrets and environment variables (`app_env=production`).
- Ensure no real capital is tied to the FYERS account (verify API strictly isolates read vs order logic).
- Deploy the system in a containerized or persistent environment (e.g. systemd/Docker) to test actual restart conditions.

## F0.2 Observability Validation
- Inject intentional HTTP failure and verify it propagates to `system_logs` table.
- Verify `request_logger` tracks `GET /scanner/latest` response times.
- Ensure task supervisor publishes crash notifications if a loop fails.

## F0.3 Scheduler Validation
- Verify `pre_market_deep_scan` fires exactly at 09:00 IST.
- Verify `job_market_engine_spin_up` fires precisely at 08:55 IST.
- Simulate an app crash at 08:59 IST and restart at 09:01 IST; verify gap replay mechanisms and evaluate if the scan was skipped or backfilled.
- Verify the Singleton lease prevents a secondary test instance from firing the scheduler.

## F0.4 Scanner Validation
- Audit the exact execution time of the 09:00 scan for NIFTY 500.
- Ensure execution does not exceed the target threshold (e.g., 10 minutes).
- Monitor memory spikes during `ScreenerService` Pandas DataFrame manipulations.
- Verify DB persistence seamlessly stores all candidates post-scan.

## F0.5 Paper Trading Validation
- Create simulated BUY/SELL orders before market open.
- Verify `gap_replay` triggers them correctly if they hit target on the opening tick.
- Verify target/stop-loss executions handle tick streams accurately without race conditions across the `market_engine`.

## F0.6 Dashboard Validation
- Open the dashboard mid-scan and verify it still instantly loads the *previous* day's snapshot without blocking.
- Leave dashboard open for 4+ hours; verify WebSocket reconnects seamlessly if the network drops.
- Ensure CPU/Memory footprint of the browser tab remains stable.

## F0.7 Database Validation
- Trigger `RetentionService` manually.
- Verify `scan_snapshots`, `scan_snapshot_records`, and `system_logs` older than the retention threshold (e.g., 30 days) are purged successfully.
- Verify PostgreSQL index hit-rates using `pg_stat_user_indexes` after 24 hours of operation.

## F0.8 Shadow Run Exit Criteria
- System operates for 3 consecutive market days with ZERO manual intervention.
- Zero missed schedules.
- Zero silent application crashes.
- Database retention jobs execute and successfully delete target rows.
- Scan logic completely matches historical baseline accuracy.
- Dashboard renders instantly (< 100ms) with zero scanner regression.

---

**Final Status**:
**READY_FOR_PHASE_F**
