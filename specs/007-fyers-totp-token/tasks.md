# Tasks: Sprint 2 – Core TOTP Token Generation Function

**Input**: Design documents from `/specs/007-fyers-totp-token/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api_contracts.md, quickstart.md

**Tests**: Tests are requested as part of the TDD approach and exception validation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- Paths assume single project: `fyers_token.py` and `tests/` at repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Initialize the core module file fyers_token.py and test folder tests/
- [x] T002 [P] Create the env configuration template file .env.template

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Implement custom exceptions FyersAuthError, FyersConfigError, and FyersConnectionError in fyers_token.py
- [x] T004 Implement load_fyers_config function to fetch and validate environment variables in fyers_token.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Headless Token Generation via Environment Variables (Priority: P1) 🎯 MVP

**Goal**: Create the core API-based login flow with TOTP generation and token exchange.

**Independent Test**:
Run python verification script fetching token E2E using `.env` credentials, and execute `python fyers_token.py` directly to output the raw token to stdout.

### Tests for User Story 1 (TDD approach)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T005 [US1] Write base test file tests/test_fyers_token.py with mocked responses for API endpoints and verify that the test suite fails when run with pytest.

### Implementation for User Story 1

- [x] T006 [P] [US1] Implement get_base64_string helper in fyers_token.py
- [x] T007 [US1] Implement Step 1: send_login_otp_v2 API POST call in fyers_token.py
- [x] T008 [US1] Implement Step 2: verify_otp API POST call in fyers_token.py
- [x] T009 [US1] Implement Step 3: verify_pin_v2 API POST call in fyers_token.py
- [x] T010 [US1] Implement Step 4: generate-authcode GET call to extract auth_code from Location redirect header in fyers_token.py
- [x] T011 [US1] Implement Step 5: SDK-based authorization code token exchange in fyers_token.py
- [x] T012 [US1] Implement CLI execution entry point with sys.exit and stdout/stderr writing in fyers_token.py

**Checkpoint**: At this point, User Story 1 is fully functional and testable independently.

---

## Phase 4: User Story 2 - Error Handling and Fault Diagnostics (Priority: P2)

**Goal**: Implement comprehensive error catching, input sanitization, structural logging, and TOTP window retry timing logic.

**Independent Test**:
Run mocked tests verifying that invalid PINs, network failures, and missing variables raise correct custom exceptions, and that TOTP retry is triggered.

### Tests for User Story 2

- [x] T013 [US2] Implement unit tests in tests/test_fyers_token.py for invalid inputs, API failure responses, and network timeouts

### Implementation for User Story 2

- [x] T014 [US2] Implement TOTP verification retry logic (wait for next window) on failure in fyers_token.py
- [x] T015 [US2] Implement strict input sanitization (whitespace stripping) in fyers_token.py
- [x] T016 [US2] Add INFO level logging statements without leaking credentials in fyers_token.py

**Checkpoint**: At this point, both User Story 1 and User Story 2 are complete and functional.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanups, documentation, and validation before feature completion.

- [x] T017 [P] Update dependency documentation in requirements.txt and run ruff or black linters on fyers_token.py
- [x] T018 Run end-to-end scenarios from quickstart.md using live credentials and verify successful completion

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
- Core HTTP requests/helpers before higher-level methods.
- SDK integration before CLI wrapper endpoints.
- User Story 1 complete before moving to User Story 2.

### Parallel Opportunities

- T002 (Setup template) and T001 can run in parallel.
- T006 (Base64 helper) can run in parallel with tests.
- T017 (Documentation/linting) can run in parallel with final verification steps.

---

## Parallel Example: User Story 1

```bash
# Launch get_base64_string helper and test file setup in parallel:
Task: "Implement get_base64_string helper in fyers_token.py"
Task: "Write base test file tests/test_fyers_token.py with mocked responses for API endpoints"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational.
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: Test User Story 1 independently using the quickstart.md validation steps.

### Incremental Delivery

1. Complete Setup + Foundational -> Foundation ready.
2. Add User Story 1 -> Test independently -> Deploy/Demo (MVP!).
3. Add User Story 2 -> Test independently -> Deploy/Demo.
4. Verify all scenarios pass.
