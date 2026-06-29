# Testing Strategy

## LAYER 1 — CHARACTERIZATION TESTS

**Uncovered Services, Routes, and UI Flows Identified:**
- Services: `paper_trading_service.py`, `margin_engine.py`, `live_state_machine.py`, `scan_execution_service.py`, `screener_service.py`
- Routes: `/paper-trading` (Order Lifecycle & Idempotency), `/scanner`
- UI Flows: `PaperTradingPage.tsx` order entry and PnL rendering flow

**Characterization Tests Required Before Modification:**

- **Test name:** Characterization of `paper_trading_service.py` Order Lifecycle
  - **What it tests:** Captures existing behavior of order submission, modification, and cancellation for covered/uncovered flows.
  - **Input / setup:** Initialize database with known capital, submit a paper trading order.
  - **Expected outcome:** Order recorded in `paper_trading_orders` with exact current status fields and timestamps.
  - **Tool:** pytest
  - **Location:** backend/tests/characterization/

- **Test name:** Characterization of `margin_engine.py` Capital Reservation
  - **What it tests:** Existing logic for blocking and releasing capital based on position sizing.
  - **Input / setup:** Create mock positions with known quantities and prices.
  - **Expected outcome:** Reserved margin exactly matches current output.
  - **Tool:** pytest
  - **Location:** backend/tests/characterization/

- **Test name:** Characterization of `live_state_machine.py` Transitions
  - **What it tests:** Current enforcement of engine state transitions (e.g. PENDING -> OPEN -> CLOSED).
  - **Input / setup:** Force state transitions using existing service methods.
  - **Expected outcome:** Succeeds or fails matching current production behavior exactly.
  - **Tool:** pytest
  - **Location:** backend/tests/characterization/

- **Test name:** Characterization of `screener_service.py` Flow
  - **What it tests:** Existing pandas vectorization logic and output shape for NIFTY500 scan.
  - **Input / setup:** Mock a standard OHLCV payload.
  - **Expected outcome:** Produces exact snapshot shape currently produced in `scan_snapshots`.
  - **Tool:** pytest
  - **Location:** backend/tests/characterization/

- **Test name:** Characterization of Idempotency Paths
  - **What it tests:** Current behavior of `idempotency_records` on duplicate API calls.
  - **Input / setup:** Send identical POST request twice.
  - **Expected outcome:** Captures current exact response (e.g., error format or success format) for the duplicate call.
  - **Tool:** pytest
  - **Location:** backend/tests/characterization/

- **Test name:** Characterization of PnL Calculations
  - **What it tests:** Current math used to calculate PnL for active positions.
  - **Input / setup:** Load `paper_trading_positions` with active holdings and mock tick updates.
  - **Expected outcome:** PnL value matches existing implementation's output.
  - **Tool:** pytest
  - **Location:** backend/tests/characterization/

## LAYER 2 — UNIT TESTS

Every pure function must have unit tests. Target coverage is 80% per modified service module.

- **Test name:** PnL Calculation Unit Tests
  - **What it tests:** Pure functions computing Unrealized and Realized PnL.
  - **Input / setup:** Normal: valid price, valid quantity. Edge: zero price, negative quantity, null inputs. Determinism: fixed inputs.
  - **Expected outcome:** Accurate PnL float outputs exactly matching deterministic expectations.
  - **Tool:** pytest, pytest-asyncio
  - **Location:** backend/tests/unit/

- **Test name:** Position Sizing Unit Tests
  - **What it tests:** Pure functions determining order size based on risk parameters.
  - **Input / setup:** Normal: valid risk %, valid account balance. Edge: 0% risk, empty/negative balance. Determinism: fixed parameters.
  - **Expected outcome:** Accurate position size integer.
  - **Tool:** pytest, pytest-asyncio
  - **Location:** backend/tests/unit/

- **Test name:** Candle Aggregation Unit Tests
  - **What it tests:** Pure functions converting tick data (LTP) to OHLCV.
  - **Input / setup:** Normal: sequence of ticks. Edge: empty sequence, single tick, missing timestamps. Determinism: same tick sequence.
  - **Expected outcome:** Correct Open, High, Low, Close, Volume.
  - **Tool:** pytest, pytest-asyncio
  - **Location:** backend/tests/unit/

- **Test name:** Risk Rules Unit Tests
  - **What it tests:** Validation functions enforcing max loss or max position limits.
  - **Input / setup:** Normal: order within limits. Edge: order exactly at limit, order exceeding limit by 1 unit, zero value. Determinism: fixed order limits.
  - **Expected outcome:** Boolean pass/fail or specific validation exceptions.
  - **Tool:** pytest, pytest-asyncio
  - **Location:** backend/tests/unit/

- **Test name:** State Machine Transitions Unit Tests
  - **What it tests:** Pure functions determining valid next states.
  - **Input / setup:** Normal: valid transition (e.g., PENDING to OPEN). Edge: invalid transitions (CLOSED to OPEN). Determinism: static state map.
  - **Expected outcome:** Returns next state or raises state transition error.
  - **Tool:** pytest, pytest-asyncio
  - **Location:** backend/tests/unit/

- **Test name:** Backtest Calculation Unit Tests
  - **What it tests:** Math evaluating historical strategy metrics (Sharpe, drawdowns).
  - **Input / setup:** Normal: standard series of returns. Edge: zero returns, negative returns only, missing data points. Determinism: exact same returns.
  - **Expected outcome:** Accurate performance metrics.
  - **Tool:** pytest, pytest-asyncio
  - **Location:** backend/tests/unit/

- **Test name:** LLM Output Validation Unit Tests
  - **What it tests:** Parsers extracting structured data from raw LLM text (Groq/OpenAI).
  - **Input / setup:** Normal: correctly formatted JSON string. Edge: malformed JSON, empty string, unexpected keys. Determinism: identical text.
  - **Expected outcome:** Valid Pydantic object or handled parsing error.
  - **Tool:** pytest, pytest-asyncio
  - **Location:** backend/tests/unit/

## LAYER 3 — INTEGRATION TESTS

These verify full service-layer workflows from end to end using `pytest-asyncio` with transactional rollback fixtures to ensure no data persists between tests. Each workflow must test both happy path and rejection/error paths.

- **Test name:** Full Order Lifecycle Integration
  - **What it tests:** The complete progression of an order from submission to closure.
  - **Input / setup:** Create order via `paper_trading_service`, simulate market tick, simulate close.
  - **Expected outcome:** Order state updates PENDING -> ENTRY_FILLED -> OPEN -> CLOSED. Rejection paths properly retain PENDING or fail out to REJECTED.
  - **Tool:** pytest-asyncio with transactional rollback fixture
  - **Location:** backend/tests/integration/

- **Test name:** Idempotency Enforcement Integration
  - **What it tests:** That identical mutating requests do not cause double execution.
  - **Input / setup:** Submit the same POST order request twice with the same Idempotency-Key.
  - **Expected outcome:** First call succeeds and creates order, second call returns same effect/response without creating a second order. Error path handles missing keys if required.
  - **Tool:** pytest-asyncio with transactional rollback fixture
  - **Location:** backend/tests/integration/

- **Test name:** Capital Reservation and Release Integration
  - **What it tests:** Available capital is correctly reduced on PENDING and restored appropriately on CLOSED.
  - **Input / setup:** Initial capital state, place order, fill order, close position. Error path for insufficient capital.
  - **Expected outcome:** Capital blocked matches required margin, and final capital reflects PnL. Error path yields insufficient funds error.
  - **Tool:** pytest-asyncio with transactional rollback fixture
  - **Location:** backend/tests/integration/

- **Test name:** Scanner Distributed Lock Integration
  - **What it tests:** Prevents concurrent execution of the market screener.
  - **Input / setup:** Trigger `job_trigger_scans` twice concurrently.
  - **Expected outcome:** First run acquires lock and executes; second run fails to acquire lock and yields a 409 Conflict.
  - **Tool:** pytest-asyncio with transactional rollback fixture
  - **Location:** backend/tests/integration/

- **Test name:** Reconciliation Gap Detection Integration
  - **What it tests:** `candle_reconciliation_service.py` identifying missing candles.
  - **Input / setup:** Insert historical candles with a known time gap.
  - **Expected outcome:** Service detects the gap and schedules a backfill task.
  - **Tool:** pytest-asyncio with transactional rollback fixture
  - **Location:** backend/tests/integration/

- **Test name:** Token Save and Replace Integration
  - **What it tests:** `token_service.py` correctly updates the active FYERS token and archives the old one.
  - **Input / setup:** Insert existing active token, trigger refresh flow with new token. Error path for invalid refresh token.
  - **Expected outcome:** New token becomes active in `fyers_tokens`, old token set to is_active=False in fyers_tokens. Error path logs auth failure.
  - **Tool:** pytest-asyncio with transactional rollback fixture
  - **Location:** backend/tests/integration/

## LAYER 4 — API CONTRACT TESTS

Testing the API boundaries ensures Constitution API-004 format compliance and Idempotency enforcement.

- **Test name:** API Contract - Paper Trading Routes
  - **What it tests:** `/paper-trading` POST/GET endpoints for expected status codes, response shapes, Pydantic schema alignment, and Idempotency-Key enforcement.
  - **Input / setup:** Valid and invalid JSON payloads mutating paper trading accounts/orders.
  - **Expected outcome:** 200/201 on success, 422 on schema mismatch. Errors match Constitution API-004. No stack traces explicitly verified.
  - **Tool:** httpx AsyncClient against FastAPI app
  - **Location:** backend/tests/api/

- **Test name:** API Contract - Scanner Routes
  - **What it tests:** `/scanner` endpoints expected response shapes.
  - **Input / setup:** GET request to scanner snapshot endpoints.
  - **Expected outcome:** Responses precisely align with Pydantic schemas, 200 OK. No stack traces.
  - **Tool:** httpx AsyncClient against FastAPI app
  - **Location:** backend/tests/api/

- **Test name:** API Contract - Error Formatting Validation
  - **What it tests:** That NO stack traces leak into any error response.
  - **Input / setup:** Force unexpected exceptions in various routes.
  - **Expected outcome:** Standardized API-004 error response format. Stack trace strictly absent.
  - **Tool:** httpx AsyncClient against FastAPI app
  - **Location:** backend/tests/api/

## LAYER 5 — FRONTEND BEHAVIOR TESTS

- **Test name:** Frontend Component State Transitions
  - **What it tests:** UI updates correctly for all page and component states (e.g., PENDING -> OPEN).
  - **Input / setup:** Mock API responses representing state changes.
  - **Expected outcome:** UI reflects the new states accurately.
  - **Tool:** Vitest + React Testing Library
  - **Location:** frontend/tests/components/

- **Test name:** Error Banner Behavior Validation
  - **What it tests:** Frontend handles API errors via banners, avoiding legacy `window.alert` in new code.
  - **Input / setup:** Mock an API failure.
  - **Expected outcome:** An error banner is displayed; `window.alert` is NOT called.
  - **Tool:** Vitest + React Testing Library
  - **Location:** frontend/tests/components/

- **Test name:** WebSocket Disconnect Banner
  - **What it tests:** UI shows a degraded warning when WebSocket connection drops.
  - **Input / setup:** Mock a WebSocket close event.
  - **Expected outcome:** Banner appears warning the user of the disconnect.
  - **Tool:** Vitest + React Testing Library
  - **Location:** frontend/tests/components/

- **Test name:** TOKEN_EXPIRED_PAUSED State Behavior
  - **What it tests:** Expiry state disables order entry but allows order exit.
  - **Input / setup:** Set application state to `TOKEN_EXPIRED_PAUSED`.
  - **Expected outcome:** Order entry is disabled; exit/closing positions remains active.
  - **Tool:** Vitest + React Testing Library
  - **Location:** frontend/tests/components/

- **Test name:** fetchWithDiagnostics Usage Enforcement
  - **What it tests:** Ensures `fetchWithDiagnostics` is used for every API call and no raw `fetch` is used.
  - **Input / setup:** Static code check or global fetch mock.
  - **Expected outcome:** Raw `fetch` usage fails the test.
  - **Tool:** ESLint custom rule or CI grep script
  - **Location:** frontend/tests/infrastructure/

## LAYER 6 — END TO END TESTS

- **Test name:** E2E - Scan and Order Entry
  - **What it tests:** Journey 1: Scan → pick candidate → place paper order → verify position created.
  - **Input / setup:** Initiate scan flow from UI, select a generated candidate, submit order.
  - **Expected outcome:** Backend position is created and reflected in UI.
  - **Tool:** pytest with mock broker (backend), Playwright (frontend)
  - **Location:**
    - Backend steps: backend/tests/e2e/
    - Frontend steps: frontend/e2e/

- **Test name:** E2E - Limit Order Lifecycle
  - **What it tests:** Journey 2: Place limit order → simulate fill → verify OPEN → close → verify CLOSED + correct PnL.
  - **Input / setup:** Place a limit order on paper trading, trigger backend fill simulation, trigger UI close.
  - **Expected outcome:** Correct state transitions and final PnL values are verified in both backend and frontend.
  - **Tool:** pytest with mock broker (backend), Playwright (frontend)
  - **Location:**
    - Backend steps: backend/tests/e2e/
    - Frontend steps: frontend/e2e/

- **Test name:** E2E - Degraded State Fallback
  - **What it tests:** Journey 3: Kill WebSocket → verify DEGRADED → verify polling fallback activates.
  - **Input / setup:** Sever mock WebSocket connection while user is on paper trading page.
  - **Expected outcome:** UI degraded banner appears and network panel shows polling fallback activating.
  - **Tool:** pytest with mock broker (backend), Playwright (frontend)
  - **Location:**
    - Backend steps: backend/tests/e2e/
    - Frontend steps: frontend/e2e/

- **Test name:** E2E - Token Expiry Handling
  - **What it tests:** Journey 4: Expire token → verify engine pauses → regenerate → verify engine resumes.
  - **Input / setup:** Expire FYERS token mid-session. Follow auth regeneration flow.
  - **Expected outcome:** Trading engine gracefully pauses and resumes without data loss or crashes.
  - **Tool:** pytest with mock broker (backend), Playwright (frontend)
  - **Location:**
    - Backend steps: backend/tests/e2e/
    - Frontend steps: frontend/e2e/

- **Test name:** E2E - Squareoff All
  - **What it tests:** Journey 5: Open 3 positions → squareoff-all → verify all CLOSED + capital restored.
  - **Input / setup:** Create 3 OPEN positions and execute bulk squareoff command.
  - **Expected outcome:** All positions move to CLOSED, capital accurately calculated and restored.
  - **Tool:** pytest with mock broker (backend), Playwright (frontend)
  - **Location:**
    - Backend steps: backend/tests/e2e/
    - Frontend steps: frontend/e2e/

- **Test name:** E2E - Idempotent Order Submission
  - **What it tests:** Journey 6: Place same order twice with same idempotency key → verify only 1 order created.
  - **Input / setup:** Rapid-fire or duplicate identical requests from the UI.
  - **Expected outcome:** Only one order exists in the backend DB and UI.
  - **Tool:** pytest with mock broker (backend), Playwright (frontend)
  - **Location:**
    - Backend steps: backend/tests/e2e/
    - Frontend steps: frontend/e2e/

## LAYER 7 — REGRESSION TESTS

- **Test name:** Regression - App.tsx / Dashboard.tsx Duplication
  - **What it tests:** Change in one must not break the other.
  - **Input / setup:** Render both core components with shared routing state.
  - **Expected outcome:** Consistent rendering without errors.
  - **Tool:** Vitest + React Testing Library
  - **Location:** frontend/tests/regression/

- **Test name:** Regression - PaperTradingPage Aggressive Polling
  - **What it tests:** New code must not add polling under 5 seconds.
  - **Input / setup:** Inspect timers and network intervals during component lifecycle.
  - **Expected outcome:** No sub-5-second intervals are observed.
  - **Tool:** Vitest + React Testing Library
  - **Location:** frontend/tests/regression/

- **Test name:** Regression - window.alert Removal
  - **What it tests:** No new alert calls introduced.
  - **Input / setup:** Codebase static analysis or mocked global functions.
  - **Expected outcome:** No executions or definitions of `window.alert`.
  - **Tool:** Vitest
  - **Location:** frontend/tests/regression/

- **Test name:** Regression - CentralCommand Tailwind Confinement
  - **What it tests:** Tailwind must not spread to new component files.
  - **Input / setup:** Regex parsing of new `.tsx` files.
  - **Expected outcome:** Tailwind class structures are constrained strictly to `CentralCommand.tsx`.
  - **Tool:** CI script (grep or ESLint)
  - **Location:** frontend/tests/regression/

- **Test name:** Regression - nightly_candle_sync Orphan
  - **What it tests:** No feature may depend on it having run.
  - **Input / setup:** Run all primary trading and scanning workflows without the nightly job state.
  - **Expected outcome:** Everything succeeds independent of the nightly job.
  - **Tool:** pytest
  - **Location:** backend/tests/regression/

## LAYER 8 — NON FUNCTIONAL TESTS

- **Test name:** NFT - Broker Timeout Resilience
  - **What it tests:** Fallback activates, no crash, no 500 with stack trace when Groq or FYERS time out.
  - **Input / setup:** Mock external API delays beyond threshold.
  - **Expected outcome:** System handles timeout gracefully and returns standard 503/504 to client without stack trace.
  - **Tool:** pytest, httpx
  - **Location:** backend/tests/performance/

- **Test name:** NFT - DB Connection Loss
  - **What it tests:** API returns 503 not 500 on database disconnection.
  - **Input / setup:** Sever Postgres connection mid-request.
  - **Expected outcome:** 503 Service Unavailable returned.
  - **Tool:** pytest, chaos toolkit or custom fixture
  - **Location:** backend/tests/chaos/

- **Test name:** NFT - Concurrent Fills
  - **What it tests:** Only one fill recorded on concurrent fills on same position.
  - **Input / setup:** Send multiple parallel simulated fill requests for the same order.
  - **Expected outcome:** Only one fill succeeds, others are cleanly ignored or rejected via locking/idempotency.
  - **Tool:** pytest-asyncio
  - **Location:** backend/tests/performance/

- **Test name:** NFT - 500-symbol scan Execution
  - **What it tests:** Completes within acceptable memory and time.
  - **Input / setup:** Trigger a full NIFTY500 scan in the background.
  - **Expected outcome:** Process finishes successfully. Time limit: must complete within 120 seconds. Memory limit: process must not exceed 512MB peak RSS.
  - **Tool:** pytest with profiling
  - **Location:** backend/tests/performance/

- **Test name:** NFT - Token Expiry Mid-Scan
  - **What it tests:** Scanner degrades cleanly, does not hang on token expiry.
  - **Input / setup:** Invalidate auth token halfway through active scan.
  - **Expected outcome:** Scanner aborts or degrades cleanly, logging the failure without a thread freeze.
  - **Tool:** pytest-asyncio
  - **Location:** backend/tests/chaos/

---

## PRE-PUSH CHECKLIST

```bash
pytest backend/tests/unit/ --cov=app/services --cov-fail-under=80
pytest backend/tests/integration/
pytest backend/tests/api/
pytest backend/tests/characterization/
pytest backend/tests/regression/
pytest backend/tests/performance/
pytest backend/tests/chaos/
npx vitest run frontend/tests/
npx playwright test frontend/e2e/
alembic upgrade head # (only if schema changed)
ruff check .
tsc --noEmit
```
