Read the following files before doing anything:
- `.specify/memory/constitution.md`
- `.specify/memory/project.md`
- `docs/testing-strategy.md`

Then run the full test suite in this exact order and report results layer by layer.

STEP 1 — CHARACTERIZATION TESTS
Run: pytest backend/tests/characterization/ -v
If the folder does not exist, report: [MISSING - needs to be created]

STEP 2 — UNIT TESTS
Run: pytest backend/tests/unit/ -v --cov=app/services --cov-fail-under=80
If coverage is below 80%, list exactly which modules are below threshold.

STEP 3 — INTEGRATION TESTS
Run: pytest backend/tests/integration/ -v
Report any failing lifecycle, idempotency, or capital flow tests separately.

STEP 4 — API CONTRACT TESTS
Run: pytest backend/tests/api/ -v
Flag any route that returns a stack trace in its error response.

STEP 5 — FRONTEND BEHAVIOR TESTS
Run: npx vitest run frontend/tests/
Report any window.alert, raw fetch, or polling interval violations.

STEP 6 — E2E TESTS
Run: pytest backend/tests/e2e/ -v
Run: npx playwright test frontend/e2e/
Report which of the 6 journeys passed and which failed.

STEP 7 — REGRESSION TESTS
Run: pytest backend/tests/regression/ -v
Run: npx vitest run frontend/tests/regression/
Flag any Tailwind spread, sub-5s polling, or window.alert regressions.

STEP 8 — NON-FUNCTIONAL TESTS
Run: pytest backend/tests/performance/ -v
Run: pytest backend/tests/chaos/ -v
Flag any scan exceeding 120 seconds or 512MB RSS.

STEP 9 — STATIC CHECKS
Run: ruff check .
Run: tsc --noEmit
Report every linting error and TypeScript error separately.

STEP 10 — FINAL REPORT
Produce a summary table like this:

| Layer | Status | Passed | Failed | Missing |
|---|---|---|---|---|
| L1 Characterization | | | | |
| L2 Unit | | | | |
| L3 Integration | | | | |
| L4 API Contract | | | | |
| L5 Frontend | | | | |
| L6 E2E | | | | |
| L7 Regression | | | | |
| L8 Non-Functional | | | | |
| Static Checks | | | | |

If any layer has MISSING tests that do not exist yet, 
list them as a TODO with their location from testing-strategy.md.

Do NOT auto-fix anything. Only report. 
Do NOT skip a layer even if it has no files yet.