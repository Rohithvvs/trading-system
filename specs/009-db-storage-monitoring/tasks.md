# Tasks: Sprint 4 – Database Storage + Basic Monitoring

**Input**: Design documents from `/specs/009-db-storage-monitoring/`
**Prerequisites**: [plan.md](file:///D:/Work_Space/trading-system/specs/009-db-storage-monitoring/plan.md) (required), [spec.md](file:///D:/Work_Space/trading-system/specs/009-db-storage-monitoring/spec.md) (required for user stories), [research.md](file:///D:/Work_Space/trading-system/specs/009-db-storage-monitoring/research.md), [data-model.md](file:///D:/Work_Space/trading-system/specs/009-db-storage-monitoring/data-model.md), [contracts/api_contracts.md](file:///D:/Work_Space/trading-system/specs/009-db-storage-monitoring/contracts/api_contracts.md)

**Tests**: Tests are requested to ensure regression safety and correct success/failure persistence states.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Paths reference the project root (e.g. `backend/app/...`, `tests/...`, `update_token.py`) per [plan.md](file:///D:/Work_Space/trading-system/specs/009-db-storage-monitoring/plan.md) structure decision.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure validation

- [x] T001 Verify existing database connection and ORM models in [backend/app/db/session.py](file:///D:/Work_Space/trading-system/backend/app/db/session.py) and [backend/app/models/fyers_token.py](file:///D:/Work_Space/trading-system/backend/app/models/fyers_token.py)
- [x] T002 Verify that Alembic migrations exist and run `alembic upgrade head` in local environment to sync development database schema

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 [P] Import and configure logger `app.token` in [backend/app/services/token_service.py](file:///D:/Work_Space/trading-system/backend/app/services/token_service.py) if not already present
- [x] T004 Confirm Fernet encryption utilities (`encrypt_secret`, `decrypt_secret`) are imported and functional in [backend/app/services/token_service.py](file:///D:/Work_Space/trading-system/backend/app/services/token_service.py)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Persist Access Token on Success (Priority: P1) 🎯 MVP

**Goal**: Automatically store the generated Fyers access token to the database with a `"Success"` status, clear previous error messages, and update the timestamp.

**Independent Test**: Mock token generation to return a valid token, run the runner, and assert that the database contains the encrypted token, status `"Success"`, `last_error` is `None`, and the updated timestamp is recent.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T005 [P] [US1] Create integration test `test_generate_and_persist_token_success` in `tests/test_token_persistence.py` to assert correct success fields update in `fyers_tokens` database table

### Implementation for User Story 1

- [x] T006 [US1] Implement `generate_and_persist_fyers_token` helper function stub in [backend/app/services/token_service.py](file:///D:/Work_Space/trading-system/backend/app/services/token_service.py)
- [x] T007 [US1] Code success flow: invoke `generate_fyers_access_token()`, encrypt token, begin transaction, retrieve or create singleton row (ID=1) in `fyers_tokens`, set columns (`access_token`, `status="Success"`, `last_error=None`, `access_token_saved_at=now`), and commit in [backend/app/services/token_service.py](file:///D:/Work_Space/trading-system/backend/app/services/token_service.py)
- [x] T008 [US1] Integrate local in-process token cache updates inside success flow in [backend/app/services/token_service.py](file:///D:/Work_Space/trading-system/backend/app/services/token_service.py)

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Record Failure and Diagnostic Info (Priority: P2)

**Goal**: Record `"Failed"` status and the caught exception error message in the database when token generation fails, without erasing the old token.

**Independent Test**: Mock token generation to raise an exception, run the runner, assert that the exception is re-raised, status is updated to `"Failed"`, `last_error` matches the exception message, and the old token value remains unchanged.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T009 [P] [US2] Create integration test `test_generate_and_persist_token_failure` in `tests/test_token_persistence.py` to assert failure updates and check that old token values are preserved

### Implementation for User Story 2

- [x] T010 [US2] Code failure handling flow inside `generate_and_persist_fyers_token()`: catch exceptions, start database transaction, set columns (`status="Failed"`, `last_error=str(exc)`, `access_token_saved_at=now`), preserve `access_token` column, commit transaction, log warning, and re-raise exception in [backend/app/services/token_service.py](file:///D:/Work_Space/trading-system/backend/app/services/token_service.py)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Environment Parity (Priority: P3)

**Goal**: Ensure token generation and storage works dynamically on both Development and Production environment databases using database connection configs.

**Independent Test**: Verify script reads configuration via Pydantic `settings` and uses `AsyncSessionLocal` to connect to the target database in both environments.

### Implementation for User Story 3

- [x] T011 [US3] Refactor the root script [update_token.py](file:///D:/Work_Space/trading-system/update_token.py) to import Pydantic config, instantiate `AsyncSessionLocal()`, run `generate_and_persist_fyers_token()`, handle CLI process exits (exit code 0 on success, exit code 1 with stderr print on exception)
- [x] T012 [US3] Verify that the CLI prints masked token string to stdout on success using `_mask_token` in [update_token.py](file:///D:/Work_Space/trading-system/update_token.py)

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup, validation, and checklist runs

- [x] T013 Update documentation links and details in [README.md](file:///D:/Work_Space/trading-system/README.md) to reference Sprint 4 database token storage capabilities
- [x] T014 Run quickstart validation steps from [quickstart.md](file:///D:/Work_Space/trading-system/specs/009-db-storage-monitoring/quickstart.md) in local environment
- [x] T015 Verify that test suite passes successfully by running `pytest tests/test_token_persistence.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User Story 1 (P1) must be implemented and tested first (MVP)
  - User Story 2 (P2) depends on User Story 1 framework (extends try-catch block)
  - User Story 3 (P3) depends on US1 & US2 completion (creates the CLI runner)
- **Polish (Final Phase)**: Depends on all user stories being complete

### Parallel Opportunities

- Setup tasks T001, T002 can run in parallel.
- Foundational tasks T003, T004 can run in parallel.
- Integration tests T005 and T009 can be written concurrently.
- Polish tasks T013 and T014 can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Developers can write success and failure tests concurrently:
Task: "Create integration test test_generate_and_persist_token_success in tests/test_token_persistence.py"
Task: "Create integration test test_generate_and_persist_token_failure in tests/test_token_persistence.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run success tests and check dev database fields.

### Incremental Delivery

1. Setup + Foundational -> Project connection verified.
2. User Story 1 (Success) -> Validate local persistence.
3. User Story 2 (Failure) -> Validate failure observability.
4. User Story 3 (CLI Integration) -> Validate environment configuration.
5. Polish -> Run quickstart and check all test runs.
