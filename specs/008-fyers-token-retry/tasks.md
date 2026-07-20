# Tasks: Sprint 3 – Retry Logic in Token Generation

**Input**: Design documents from `/specs/008-fyers-token-retry/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api_contracts.md, quickstart.md

**Tests**: Tests are requested as part of the TDD approach for verification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- Paths assume single project: `fyers_token.py` and `tests/` at repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and environment validation

- [x] T001 Verify python testing environment and base imports in tests/test_fyers_token.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Verify base structures before implementing modifications

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T002 Verify existing generate_fyers_access_token API structure in fyers_token.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Automated Retry on Temporary Failures (Priority: P1) 🎯 MVP

**Goal**: Implement the retry loop logic for temporary connection issues.

**Independent Test**:
Run a test verifying that if attempts 1 and 2 throw connection exceptions but attempt 3 succeeds, the function returns a valid token.

### Tests for User Story 1 (TDD approach)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T003 [US1] Write test in tests/test_fyers_token.py to simulate 1st and 2nd attempt transient failures succeeding on the 3rd attempt, verifying it fails before implementation.
- [x] T004 [US1] Write test in tests/test_fyers_token.py simulating persistent failures across all 3 attempts, verifying it fails before implementation.

### Implementation for User Story 1

- [x] T005 [US1] Refactor generate_fyers_access_token in fyers_token.py to wrap login steps in a 3-attempt loop and return token immediately on success.
- [x] T006 [US1] Implement transient error interception and attempt limit logic (raise last error on 3rd failure) in fyers_token.py.
- [x] T007 [US1] Implement permanent error fail-fast checking (e.g. invalid PIN or configuration error) in fyers_token.py.

**Checkpoint**: At this point, User Story 1 is fully functional and testable independently.

---

## Phase 4: User Story 2 - Delay / Backoff Between Retries (Priority: P2)

**Goal**: Introduce the 5.0 to 10.0 seconds randomized delay between retries.

**Independent Test**:
Verify that sleep durations calculated during test execution are random and stay strictly between 5.0 and 10.0 seconds.

### Tests for User Story 2

- [x] T008 [US2] Write unit test in tests/test_fyers_token.py asserting that delay backoff sleep durations are randomized between 5.0 and 10.0 seconds.

### Implementation for User Story 2

- [x] T009 [US2] Integrate random.uniform(5.0, 10.0) delay logic and time.sleep in fyers_token.py.
- [x] T010 [US2] Update logging levels in fyers_token.py to log retry warnings at WARNING level and scheduled sleep durations at INFO level.

**Checkpoint**: At this point, both User Story 1 and User Story 2 are complete and functional.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanups, documentation, and validation before feature completion.

- [x] T011 [P] Ensure no sensitive variables are logged on warning or retry information in fyers_token.py.
- [x] T012 Run E2E validation scenarios in quickstart.md and confirm all pytest test cases pass.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Stories (Phase 3+)**: All depend on Foundational phase completion.
  - User Story 1 (P1) is the MVP and must be completed first.
  - User Story 2 (P2) depends on User Story 1 implementation.
- **Polish (Final Phase)**: Depends on all desired user stories being complete.

### Within Each User Story

- Tests MUST be written and fail before implementation.
- Core loop flow before delay logic integration.
- User Story 1 complete before moving to User Story 2.

### Parallel Opportunities

- T011 (log auditing) can run in parallel with final verification checks.

---

## Parallel Example: User Story 1

```bash
# Setup verification tasks:
Task: "Verify python testing environment and base imports in tests/test_fyers_token.py"
Task: "Verify existing generate_fyers_access_token API structure in fyers_token.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational.
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: Test User Story 1 independently using mock test cases.

### Incremental Delivery

1. Complete Setup + Foundational -> Foundation ready.
2. Add User Story 1 -> Test independently -> Deploy/Demo (MVP!).
3. Add User Story 2 -> Test independently -> Deploy/Demo.
4. Verify all scenarios pass.
