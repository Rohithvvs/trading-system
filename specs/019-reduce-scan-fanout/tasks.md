# Tasks: Reduce Scan-Result Fan-out (Sprint 3)

**Input**: Design documents from `/specs/019-reduce-scan-fanout/`  
**Prerequisites**: [plan.md](file:///D:/Work_Space/trading-system/specs/019-reduce-scan-fanout/plan.md) (required), [spec.md](file:///D:/Work_Space/trading-system/specs/019-reduce-scan-fanout/spec.md) (required for user stories), [research.md](file:///D:/Work_Space/trading-system/specs/019-reduce-scan-fanout/research.md), [data-model.md](file:///D:/Work_Space/trading-system/specs/019-reduce-scan-fanout/data-model.md), [contracts/scan-persistence.md](file:///D:/Work_Space/trading-system/specs/019-reduce-scan-fanout/contracts/scan-persistence.md), [quickstart.md](file:///D:/Work_Space/trading-system/specs/019-reduce-scan-fanout/quickstart.md)  

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `- [x] TaskID [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configure feature flag setting and test baseline structure

- [x] T001 Add setting `SCAN_RESULT_MINIMAL_WRITES: bool = False` in backend/app/config/settings.py
- [x] T002 [P] Create unit test file for feature flag resolution in backend/app/tests/test_feature_flag_minimal_writes.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core persistence prerequisites that MUST be complete before user stories execute

- [x] T003 [P] Enhance `save_latest_scan_results` in backend/app/services/persistence_service.py to ensure atomic batch upsert for canonical candidate attributes
- [x] T004 [P] Add `save_history: bool = False` parameter to scan runner methods in backend/app/services/scan_execution_service.py

**Checkpoint**: Foundational layer complete - user story implementation can begin

---

## Phase 3: User Story 1 - Live Dashboard Real-Time Scanning (Priority: P1) 🎯 MVP

**Goal**: Live dashboard scanner outputs are written ONLY to canonical `latest_scan_results`, bypassing redundant snapshot tables (`scan_snapshots`, `scan_snapshot_records`, `scan_history_snapshots`, `scanned_candidates`) when `SCAN_RESULT_MINIMAL_WRITES = ON`.

**Independent Test**: Execute scan run with `SCAN_RESULT_MINIMAL_WRITES = ON`. Verify `latest_scan_results` upserts, redundant tables receive 0 writes, and GET `/api/v1/scanner/latest` returns 200 OK with expected payload.

### Tests for User Story 1

- [x] T005 [P] [US1] Create unit and contract test file in backend/app/tests/test_minimal_write_canonical.py

### Implementation for User Story 1

- [x] T006 [US1] Refactor `persist_successful_scan` in backend/app/services/latest_scan_service.py to bypass `ScanSnapshot` and `ScanSnapshotRecord` writes when `SCAN_RESULT_MINIMAL_WRITES` is `ON`
- [x] T007 [US1] Update `ScanExecutionService` in backend/app/services/scan_execution_service.py to skip `RUNNING` snapshot row insertion when `SCAN_RESULT_MINIMAL_WRITES` is `ON`
- [x] T008 [US1] Implement virtual candidate read derivation for GET `/api/v1/scanner/latest` and `/api/v1/dashboard/candidates` in backend/app/routes/scanner.py and backend/app/routes/dashboard.py
- [x] T009 [US1] Verify real-time dashboard API response parity and zero writes to redundant tables in backend/app/tests/test_minimal_write_canonical.py

**Checkpoint**: User Story 1 MVP fully functional and independently testable

---

## Phase 4: User Story 2 - Conditional Historical Scan Archiving (Priority: P2)

**Goal**: Save historical scan data to `market_data.scan_results` only when explicitly requested (`save_history = True`) or during scheduled milestone runs.

**Independent Test**: Execute scan with `save_history = True`. Verify records inserted into `market_data.scan_results`. Execute scan with `save_history = False` and verify 0 writes to `market_data.scan_results`.

### Tests for User Story 2

- [x] T010 [P] [US2] Create integration test file for conditional history persistence in backend/app/tests/test_scanner_history_persistence.py

### Implementation for User Story 2

- [x] T011 [US2] Update `save_latest_scan` in backend/app/db/scan_store.py to bypass writing `market_data.scan_results` when `SCAN_RESULT_MINIMAL_WRITES` is `ON` and `save_history` is `False`
- [x] T012 [US2] Configure scheduled end-of-day scanner cron tasks in backend/app/services/scheduler.py to explicitly pass `save_history=True`
- [x] T013 [US2] Verify historical query retrieval from `market_data.scan_results` when `save_history=True` in backend/app/tests/test_scanner_history_persistence.py

**Checkpoint**: User Story 2 historical archiving fully functional and testable

---

## Phase 5: User Story 3 - Instant Operational Rollback via Feature Flag (Priority: P3)

**Goal**: Support seamless runtime toggling of `SCAN_RESULT_MINIMAL_WRITES` between `ON` and `OFF` without restarting application instances or dropping requests.

**Independent Test**: Dynamically toggle flag between `True` and `False` in test environment; verify instant transition between minimal write mode and legacy multi-write mode.

### Tests for User Story 3

- [x] T014 [P] [US3] Create feature flag rollback test file in backend/app/tests/test_feature_flag_rollback.py

### Implementation for User Story 3

- [x] T015 [US3] Add fallback safety check in backend/app/services/scan_execution_service.py to default to `SCAN_RESULT_MINIMAL_WRITES=False` on configuration evaluation error
- [x] T016 [US3] Verify instant operational fallback to legacy 6-table multi-write mode when flag is `OFF` in backend/app/tests/test_feature_flag_rollback.py

**Checkpoint**: Operational rollback capability verified

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Telemetry, metrics, and end-to-end verification

- [x] T017 [P] Add write operation telemetry logging and metrics counters in backend/app/services/scan_execution_service.py
- [x] T018 Run full quickstart automated validation suite per specs/019-reduce-scan-fanout/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 completion. Blocks all user stories.
- **User Stories (Phase 3+)**: Depend on Phase 2 completion.
  - User Story 1 (P1 - MVP) → User Story 2 (P2) → User Story 3 (P3)
- **Polish (Phase 6)**: Depends on completion of user stories.

### Parallel Opportunities
- T002, T003, T004 can run in parallel.
- T005, T010, T014 test files can be authored in parallel.
- T017 telemetry task can run in parallel with test verification.

---

## Implementation Strategy: MVP First

1. Complete **Phase 1 (Setup)** and **Phase 2 (Foundational)**.
2. Complete **Phase 3 (User Story 1 - MVP)**.
3. **STOP and VALIDATE**: Verify that `latest_scan_results` receives canonical writes, legacy snapshot tables receive 0 writes, and live dashboard APIs return 200 OK.
4. Proceed to **Phase 4 (User Story 2)** and **Phase 5 (User Story 3)** sequentially.
