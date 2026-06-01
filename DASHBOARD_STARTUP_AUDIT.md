# Phase S1: Dashboard Startup Audit

## Exact Call Chain
1. React component `Dashboard.tsx` mounts and invokes `useEffect`.
2. `loadAndApply()` is triggered locally inside the hook.
3. `loadAndApply()` performs a dynamic `import("./api")` then calls `getLatestScan()`.
4. `getLatestScan()` (in `api.ts`) invokes `fetchWithDiagnostics("/scanner/latest", "GET", ...)`.
5. The request hits `GET http://127.0.0.1:8000/scanner/latest`.
6. API Router routes request to `get_latest_completed_scan()` in `backend/app/routes/scanner.py`.
7. `LatestScanService.get_latest_completed_scan()` reads `ScanSnapshot` and `ScanSnapshotRecord` using `db.execute()`.
8. The raw snapshot data and candidates are successfully returned to the frontend.
9. `Dashboard.tsx` receives the JSON payload, dynamically generates a valid `ScreenerResponse` mock payload inside memory.
10. `applyScanResult()` parses the mock and hydrates all `AllAnalyzedStocksTable`, `SummaryRow`, and candidate components.

## Verification
- **Scanner Execute triggered?**: No.
- **Analysis Agent triggered?**: No.
- **Orchestrator Agent triggered?**: No.
- **Market Data Fetch triggered?**: No.
- **FYERS API triggered?**: No.

**PASS**: Opening the dashboard solely triggers `GET /scanner/latest` and retrieves static database footprints, eliminating massive load bursts.
