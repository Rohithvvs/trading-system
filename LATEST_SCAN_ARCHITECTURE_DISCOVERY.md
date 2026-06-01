# LATEST SCAN ARCHITECTURE DISCOVERY

## Current Scanner Execution Path
1. The scanner is triggered (e.g., via `fast_audit.py` or the scheduler `run_swing_scanner_job()`).
2. `ScreenerService.screen_symbols_swing` is called. It fetches candles, calls `TechnicalAnalysisService.analyze_bulk`, applies the Broad Trend Gate, applies Hard Filters, and determines passing conditions.
3. The matching `ScreenerConditionResult` records are passed to `OrchestratorAgent`.
4. `OrchestratorAgent._process_shortlist` wraps them with fundamental and sentiment agents, then triggers the `RecommendationAgent`.
5. The `RecommendationAgent` produces a `FinalRecommendation` (`BUY`, `WATCH`, or `REJECTED`).

## Scheduler Entry Point
The scheduler runs background jobs (e.g., `run_swing_scanner_job` in `scheduler.py`) via APScheduler. Currently, it initiates `orchestrator.run_swing_scan()`.

## Scan Persistence Path
Currently, the `latest_scan_results` table in `backend/app/models/market_data.py` persists results but does so per-symbol using `symbol` as a UNIQUE key constraint. This forcefully overwrites historical scans. It does not store indicator snapshot values (`rsi`, `macd`, `sma50`, etc.).

## Recommendation DTOs
`ScannerResult` or `FinalRecommendation` inside `backend/app/schemas/` holds the relevant payload: symbol, action/signal, score, close price, indicators (contained in `TechnicalAnalysisResult`), and reason/summary.

## Dashboard Data Flow
Currently, the UI might be calling the backend scanner API, triggering a LIVE execution that takes multiple seconds or minutes, instead of consuming a read-only persistence layer.

## Requirements vs. Existing Schema
- **Requirement**: Never destroy data, never overwrite historical scans.
- **Existing Schema**: `latest_scan_results` has `unique=True` on `symbol`. This fundamentally violates the preservation requirement. Furthermore, it lacks columns for `sma50`, `sma200`, `rsi`, `macd`, `close`, `volume`, and `reason`.
- **Conclusion**: A new schema/migration is absolutely required.

## Proposed Schema Additions
Two new tables are required:
1. `scan_snapshots`: Stores metadata (scan_timestamp, duration_ms, counts).
2. `scan_snapshot_records`: Stores the individual candidates associated with a specific scan ID, containing symbol, recommendation, score, close, sma50, sma200, rsi, macd, volume, and reason.

This will preserve all historical scans and provide a robust read-only layer for the Dashboard.
