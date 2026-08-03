# scan_run_id mapping

RE-001 `scan_run_id` uses the platform completed-scan identity when available:

1. **Primary (FR-027)**: `ScanExecutionService` sets ContextVar `scan_run_id` to the
   platform `scan_id` (UUID used for snapshot/latest-scan lifecycle) for the scan worker task.
2. **Orchestrator**: `run_screener` / `run_full` only generate a fallback id
   (`screener-…` / `full-…`) when no ContextVar is already set.
3. **Explicit override**: `scan_run_id` argument to `run_re001_isolated_async` wins when provided.
4. **Last resort**: `build_lab_context` uses `scan-{ISO}` from analysis timestamp.
5. Lab APIs accept this id for listing decisions for a completed run.

Also bind optional authenticated `user_id` on the same scan worker task for FR-026 portfolio load.

Link optional `analysis_history_id` when the production row is known after persist.
