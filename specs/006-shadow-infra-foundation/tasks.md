# Tasks: Shadow Infrastructure Foundation

**Input**: Design documents from `/specs/006-shadow-infra-foundation/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md

**Tests**: Test tasks are included as requested by the acceptance and verification requirements.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Paths use the project structure format starting with `backend/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create services directory files for interfaces in backend/app/services/
- [x] T002 Verify backend environment compiles successfully under python 3.11

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Create the abstract interface class IShadowExecutor in backend/app/services/shadow_executor_interface.py
- [x] T004 Create the abstract interface class IShadowStore in backend/app/services/shadow_store_interface.py
- [x] T005 Define shadow mode configuration variables in backend/app/config/settings.py
- [x] T006 Define base schemas for context and result structures in backend/app/schemas/analysis.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Configure Shadow Mode (Priority: P1) 🎯 MVP

**Goal**: Load and validate shadow mode settings configurations safely at startup.

**Independent Test**: Start the app and verify settings parse defaults correctly.

### Tests for User Story 1
- [x] T007 [P] [US1] Write unit tests for configuration parsing and setting validations in backend/tests/unit/test_shadow_config.py

### Implementation for User Story 1
- [x] T008 [US1] Implement environment variable loaders and checks in backend/app/config/settings.py

**Checkpoint**: User Story 1 is fully functional and testable independently.

---

## Phase 4: User Story 2 - Shadow Context Verification (Priority: P2)

**Goal**: Instantiate and verify the ShadowExecutionContext snapshot during scans without data mutation.

**Independent Test**: Run a mock preset screener scan and check that the shadow context is populated without modifying production recommendations.

### Tests for User Story 2
- [x] T009 [P] [US2] Write unit tests for context immutability and deep-copy verification in backend/tests/unit/test_shadow_context.py

### Implementation for User Story 2
- [x] T010 [US2] Implement the shadow context builder and trigger hook inside backend/app/agents/orchestrator_agent.py
- [x] T011 [US2] Implement isolated try-except wrapper around the shadow execution block in backend/app/agents/orchestrator_agent.py

**Checkpoint**: User Stories 1 AND 2 work independently.

---

## Phase 5: User Story 3 - Telemetry Verification (Priority: P3)

**Goal**: Record comparative shadow metrics and audit logs for discrepancy analysis.

**Independent Test**: Verify audit events show custom shadow actions registered.

### Tests for User Story 3
- [x] T012 [P] [US3] Write unit tests for shadow event schema mapping in backend/tests/unit/test_shadow_telemetry.py

### Implementation for User Story 3
- [x] T013 [US3] Register shadow audit actions (start, complete, discrepancy) in backend/app/governance/audit.py

**Checkpoint**: All user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T014 [P] Update environment configuration documentation in README.md
- [x] T015 Code formatting and linting cleanup across modified files
- [x] T016 Run end-to-end verification scenario in specs/006-shadow-infra-foundation/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories proceed sequentially in priority order (P1 → P2 → P3)
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Integrates with US1
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Integrates with US1/US2

### Within Each User Story

- Tests (if included) MUST be written first
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Unit tests marked [P] for different user stories can run in parallel

---

## Parallel Example: User Story 2

```bash
# Launch validation tests:
Task: "Write unit tests for context immutability and deep-copy verification in backend/tests/unit/test_shadow_context.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 configuration independently

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test configuration → MVP!
3. Add User Story 2 → Test orchestrator hooks
4. Add User Story 3 → Verify audit logs and event triggers
