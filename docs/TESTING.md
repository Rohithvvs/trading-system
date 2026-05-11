# Testing Architecture

This project now has a layered test foundation for the FastAPI backend, React/Vite frontend, SQLite persistence, and optional live FYERS checks.

## Current App Structure

- Backend entry point: `backend/app/main.py`
- Backend route registry: `backend/app/routes/__init__.py`
- Frontend entry point: `frontend/src/main.tsx`
- Frontend app shell: `frontend/src/App.tsx`
- Database setup: `backend/app/db/session.py`
- SQLAlchemy models: `backend/app/models/`
- Main SQLite database: `DATABASE_URL`, defaulting to `sqlite:///./trading_system.db`
- Scanner latest-result SQLite store: `backend/app/db/scan_result.db`

Important routes:

- `GET /health`
- `POST /api/token/save-access-token`
- `GET /api/token/status`
- `GET /api/token/history`
- `POST /analysis/screener/full`
- `GET /analysis/scan/latest`
- `GET /workstation/*` for universes, saved scans, scan history, alerts, risk settings, API health
- `GET/POST/PUT/PATCH/DELETE /paper-trading/*` for dashboard, orders, positions, account, alerts, analytics
- `POST /fyers/token`, `GET /fyers/token/status`, `DELETE /fyers/token`
- `GET /test-diagnostics/*` only returns data when `APP_ENV=test`

Persistence map:

- FYERS access token: SQLite table `fyers_tokens`
- FYERS token history: SQLite table `fyers_token_history`
- Paper trading: SQLite tables `paper_trading_accounts`, `paper_trading_orders`, `paper_trading_positions`, `paper_trading_trade_history`, `paper_trading_transactions`, `paper_trading_alerts`, `paper_trading_notifications`
- Saved scanner presets and scan history: SQLite tables `saved_scans`, `scan_history_snapshots`
- Latest scanner result: separate SQLite table `latest_scan` in `backend/app/db/scan_result.db`
- Browser localStorage: `scanHistory`
- Browser sessionStorage: no current usage found
- Memory-only frontend state: selected tab/view, theme, active filters, current scanner result, selected symbol, paper ticket draft, transient messages
- Memory-only backend state: app state such as `last_gap_replay`, scheduler/background task state, FYERS service in-process caches

## Test Types

Unit tests are small, deterministic checks for individual functions or simple service behavior. They should not call FYERS or depend on the browser.

Backend integration/API tests use FastAPI `TestClient`, isolated SQLite, and dependency overrides. They verify real route behavior and table writes.

Persistence verification tests directly inspect SQLite tables after actions. They answer whether data was stored in SQLite, browser storage, or only memory.

Playwright E2E tests run the UI against a test backend and verify browser workflows, screenshots, traces, and selected database checks.

Live FYERS tests are marked `live` and skipped unless credentials are present. They are for manual confidence checks, not daily or pre-push runs.

## Local Commands

Install backend test dependencies:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install frontend and Playwright dependencies:

```powershell
cd frontend
npm install
npx playwright install chromium
```

Run fast safe tests:

```powershell
.\scripts\run-tests.ps1 fast
```

Run backend unit tests:

```powershell
.\scripts\run-tests.ps1 unit
```

Run backend integration and persistence tests:

```powershell
.\scripts\run-tests.ps1 integration
```

Run E2E browser tests:

```powershell
.\scripts\run-tests.ps1 e2e
```

Run live FYERS tests manually:

```powershell
$env:FYERS_APP_ID="your-app-id"
$env:FYERS_LIVE_ACCESS_TOKEN="your-token"
.\scripts\run-tests.ps1 live
```

Run all non-live tests:

```powershell
.\scripts\run-tests.ps1 all
```

Clean artifacts:

```powershell
.\scripts\clean-test-artifacts.ps1
```

## Artifacts

Artifacts are written under `tests/artifacts/`.

- Backend pytest log: `tests/artifacts/backend/pytest.log`
- Backend JSON row dumps: `tests/artifacts/backend/*.json`
- E2E test results: `tests/artifacts/playwright/test-results/`
- Playwright HTML report: `tests/artifacts/playwright/html-report/`
- Playwright JSON summary: `tests/artifacts/playwright/results.json`
- Failure screenshots, traces, and videos: under `tests/artifacts/playwright/test-results/`

## Debugging Failures

Start with the smallest failing layer. If a unit test fails, fix that before running E2E. If an E2E test fails, open the Playwright trace from `tests/artifacts/playwright/test-results/` and compare it with backend logs in `tests/artifacts/backend/pytest.log`.

For persistence questions, use the test-only diagnostics while the backend runs with `APP_ENV=test`:

- `GET /test-diagnostics/source-of-truth`
- `GET /test-diagnostics/sqlite/tables`
- `GET /test-diagnostics/sqlite/table/{table_name}`
- `GET /test-diagnostics/token`
- `GET /test-diagnostics/scan-store`

Secrets are masked in diagnostics and database snapshots.

## Recommended Cadence

Daily: `.\scripts\run-tests.ps1 fast`

Before push: `.\scripts\run-tests.ps1 all`

Before production deployment: backend fast suite, Playwright E2E, manual review of artifacts, and then live FYERS tests with fresh credentials.

Live FYERS tests should not be automated in normal CI because real provider outages, expired tokens, rate limits, and market holidays can fail for reasons unrelated to code quality.
