# PHASE ROOT CAUSE AUDIT — FINDINGS

## Executive Summary
The scanner is processing exactly 65 stocks instead of 755 because the frontend is explicitly sending a list of 65 symbols in the `ScreenerRequest` payload, which forces the backend to bypass the `stocks_master` database entirely.

## Exact Execution Trace (POST /analysis/screener/full)
1. **Frontend Request Generation (`Dashboard.tsx`):**
   When the scanner is triggered, the frontend calculates the `symbols` payload. If the user loads a Saved Scan created previously, the saved scan contains the 65 symbols serialized in the database. When executed, `request.symbols` is populated with exactly 65 symbols.
2. **Analysis Route (`backend/app/routes/analysis.py`):**
   The endpoint `/analysis/screener/full` receives the `ScreenerRequest` payload containing `symbols: ["RELIANCE-EQ", "INFY-EQ", ...]` (length: 65).
3. **ScanExecutionService:**
   Passes the payload transparently to `RouterAgent(None).screener_full(payload, progress_callback)`.
4. **RouterAgent:**
   Passes the payload transparently to `OrchestratorAgent.run_screener(request)`.
5. **OrchestratorAgent (`backend/app/agents/orchestrator_agent.py`):**
   At line 162, `run_screener` checks `if request.symbols:`. Because the frontend provided 65 symbols, this evaluates to `True`.
   **CRITICAL REDUCTION POINT:** The orchestrator immediately calls `self._run_screener_stage(..., source_universe=request.symbols, ...)` and **returns**.
   Because it returned early, `await self._prioritized_universes()` is **never called**. 
6. **UniverseService (`backend/app/services/universe_service.py`):**
   **Bypassed.** The service is never queried for this request because the orchestrator honors the custom symbols passed by the frontend.
7. **Screener (`ScreenerService`):**
   Processes exactly the 65 symbols it was handed.
8. **Candidate Persistence (`ScanSnapshot`):**
   The snapshot saves `total_scanned = len(payload.symbols)` which equals 65.
9. **UI Response:**
   The `ScreenerResponse.scanned_symbols` maps directly to `len(source_universe)` (65). The UI displays `Total scanned = 65`.

## Universe Source Analysis
**Where did the 65 symbols originate?**
They originate from the `.env` file's `NIFTY500_SYMBOLS` environment variable.

1. `settings.nifty500_symbols` attempts to load the NIFTY500 CSV. If it encounters a `ModuleNotFoundError` or missing file, it degrades gracefully and falls back to `settings.nifty500_symbols_raw` (loaded from `.env`). 
2. The `.env` file contains exactly 65 comma-separated fallback stocks (from `RELIANCE-EQ` to `ZYDUSLIFE-EQ`).
3. `WorkstationService.list_universes()` serves these 65 symbols to the frontend UI as the "NIFTY500" universe.
4. If a user previously saved a scan while this fallback was active, those 65 symbols were explicitly serialized into their `SavedScan` database row. Running that saved scan today will always inject those 65 symbols into `request.symbols`.

## Conclusion
The database population (`stocks_master = 755`) is fully functional. `UniverseService` correctly returns 755 symbols when queried. The issue lies entirely in the **ScreenerRequest Payload**. As long as the frontend sends an array of 65 symbols in `request.symbols`, the backend operates in "Custom Universe" mode and bypasses the `stocks_master` table.
