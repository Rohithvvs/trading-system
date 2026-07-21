# Tasks: Sprint 5 – Internal API Endpoint

**Input**: Design documents from `specs/010-fyers-internal-api/`
**Prerequisites**: [plan.md](file:///D:/Work_Space/trading-system/specs/010-fyers-internal-api/plan.md) (required), [spec.md](file:///D:/Work_Space/trading-system/specs/010-fyers-internal-api/spec.md) (required), [research.md](file:///D:/Work_Space/trading-system/specs/010-fyers-internal-api/research.md), [data-model.md](file:///D:/Work_Space/trading-system/specs/010-fyers-internal-api/data-model.md), [contracts/api_contracts.md](file:///D:/Work_Space/trading-system/specs/010-fyers-internal-api/contracts/api_contracts.md)

**Tests**: Included. As per `CONVENTIONS.md`, writing corresponding testing code alongside feature code is mandatory.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `- [ ] [ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files or independent execution)
- **[Story]**: Maps to user stories (US1, US2) from `spec.md`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and environment sanity checks

- [x] T001 Verify directory structures and check active git branch `010-fyers-internal-api`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Environment and dependency validation blocking route development

- [x] T002 Verify local `.env` and `.env.template` contain `SCHEDULER_SECRET` configuration variable

---

## Phase 3: User Story 1 - Automatic Token Refresh Trigger (Priority: P1) 🎯 MVP

**Goal**: Expose endpoint `POST /internal/refresh-fyers-token` that triggers token generation and database storage.

**Independent Test**: Send an HTTP POST request to `/internal/refresh-fyers-token` (authenticated) and verify that the endpoint generates a token, updates database singleton `fyers_tokens` (id=1), and returns a 200 OK status with the success message: `{"status": "success", "message": "Access token generated and saved successfully"}`.

### Tests for User Story 1
> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T003 [P] [US1] Write integration tests for successful and failed token generation mock cases in [backend/tests/integration/test_token_refresh_route.py](file:///D:/Work_Space/trading-system/backend/tests/integration/test_token_refresh_route.py)

### Implementation for User Story 1

- [x] T004 [US1] Define secondary `internal_router = APIRouter()` in [backend/app/routes/token.py](file:///D:/Work_Space/trading-system/backend/app/routes/token.py)
- [x] T005 [US1] Implement `POST /internal/refresh-fyers-token` route logic calling `generate_and_persist_fyers_token()` in [backend/app/routes/token.py](file:///D:/Work_Space/trading-system/backend/app/routes/token.py)
- [x] T006 [US1] Catch exceptions in the route handler, log the errors, and return an HTTP 500 status with error schema in [backend/app/routes/token.py](file:///D:/Work_Space/trading-system/backend/app/routes/token.py)
- [x] T007 [US1] Include `internal_router` inside the application routing configuration in [backend/app/main.py](file:///D:/Work_Space/trading-system/backend/app/main.py)

**Checkpoint**: User Story 1 is functional (unprotected) and verifies successfully under mocked test execution.

---

## Phase 4: User Story 2 - Endpoint Protection and Access Control (Priority: P2)

**Goal**: Protect the endpoint from public internet access using header verification.

**Independent Test**: Send HTTP POST requests without the authorization header or with an invalid key, and verify that they are rejected with 401 Unauthorized or 403 Forbidden statuses respectively.

### Tests for User Story 2

- [x] T008 [P] [US2] Write integration tests verifying unauthorized (401) and forbidden (403) security failures in [backend/tests/integration/test_token_refresh_route.py](file:///D:/Work_Space/trading-system/backend/tests/integration/test_token_refresh_route.py)

### Implementation for User Story 2

- [x] T009 [US2] Integrate the `_require_scheduler_secret` dependency/helper check in the route handler function in [backend/app/routes/token.py](file:///D:/Work_Space/trading-system/backend/app/routes/token.py)

**Checkpoint**: Endpoint is fully protected. Both User Story 1 and User Story 2 pass automated tests.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup, linting, and final validation checks

- [x] T010 [P] Run code formatter and ruff linter to verify formatting standards in [backend/app/routes/token.py](file:///D:/Work_Space/trading-system/backend/app/routes/token.py) and [backend/tests/integration/test_token_refresh_route.py](file:///D:/Work_Space/trading-system/backend/tests/integration/test_token_refresh_route.py)
- [x] T011 Run the manual verification steps defined in [quickstart.md](file:///D:/Work_Space/trading-system/specs/010-fyers-internal-api/quickstart.md) locally

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion. BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion. BLOCKS Polish.
- **User Story 2 (Phase 4)**: Depends on User Story 1 implementation skeleton completion.
- **Polish (Phase 5)**: Depends on all user stories being complete.

### Parallel Opportunities

- Setup tasks (Phase 1) and Foundational tasks (Phase 2) are sequential.
- Phase 3 (US1) and Phase 4 (US2) test tasks (`T003` and `T008`) can be written in parallel as they target test coverage.
- Code validation and style cleanup (`T010`) can run in parallel with manual run guide validations (`T011`).

---

## Parallel Execution Examples

```bash
# Write test cases for US1 and US2 concurrently
Task: "Write integration tests for successful and failed token generation mock cases in backend/tests/integration/test_token_refresh_route.py"
Task: "Write integration tests verifying unauthorized (401) and forbidden (403) security failures in backend/tests/integration/test_token_refresh_route.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Write integration tests for US1 (`T003`) and verify that they fail.
3. Code the route structure, service invocation, and exception handlers (`T004`, `T005`, `T006`, `T007`).
4. **STOP and VALIDATE**: Run `pytest backend/tests/integration/test_token_refresh_route.py -k "test_refresh_token_success"` and ensure it passes.

### Incremental Delivery

1. Verify MVP (unprotected trigger works).
2. Write security tests (`T008`) verifying 401 and 403 HTTP outcomes.
3. Add the dependency check `_require_scheduler_secret` to the route (`T009`).
4. Run the full test suite and local manual checks (`T011`) to declare implementation complete.
