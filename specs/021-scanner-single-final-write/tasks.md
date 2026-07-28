# Tasks: Scanner Single Final Write (Sprint 5)

**Input**: Design documents from `/specs/021-scanner-single-final-write/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md  

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project configuration and monitoring setup for Single Final Write architecture.

- [X] T001 Configure `SCANNER_SINGLE_FINAL_WRITE_ENABLED` environment setting in `backend/app/config/settings.py`
- [X] T002 [P] Register Prometheus metrics (`scanner_single_write_duration_seconds`, `scanner_transactions_total`, `scanner_feature_flag_status`) in `backend/app/observability/metrics.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core DTOs and repository interfaces required before user story implementation.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [X] T003 [P] Create in-memory aggregate DTOs (`ScanAggregateResult`, `ScanCandidateDTO`, `SingleWriteResult`) in `backend/app/schemas/scan_aggregate.py`
- [X] T004 [P] Create persistence repository interface for single final write in `backend/app/services/scanner_single_write_service.py`

**Checkpoint**: Foundation ready - user story implementation can now begin.

---

## Phase 3: User Story 1 - Live Dashboard Real-Time Setup Monitoring (Priority: P1) 🎯 MVP

**Goal**: Perform 100% in-memory universe scan calculation with 30s timeout guard and persist final aggregated candidates atomically to `latest_scan_results` in exactly 1 database transaction.

**Independent Test**: Execute intraday scan with `SCANNER_SINGLE_FINAL_WRITE_ENABLED=ON`. Verify 0 intermediate write queries occur during analysis, 1 transaction commits to `latest_scan_results`, and `GET /api/v1/scanner/latest` returns identical candidate data.

### Tests for User Story 1

- [X] T005 [P] [US1] Create unit test for `ScanAggregateResult` construction in `backend/app/tests/test_scan_aggregate_dto.py`
- [X] T006 [P] [US1] Create integration test for atomic single final write persistence in `backend/app/tests/test_scanner_single_final_write.py`

### Implementation for User Story 1

- [X] T007 [US1] Implement 30s execution timeout wrapper for in-memory scan calculation in `backend/app/services/scan_execution_service.py`
- [X] T008 [US1] Implement atomic single transaction upsert handler for `latest_scan_results` in `backend/app/services/scanner_single_write_service.py`
- [X] T009 [US1] Integrate `ScanAggregateResult` in-memory accumulation and single final write dispatch in `backend/app/services/scan_execution_service.py`
- [X] T010 [US1] Add single final write latency and transaction count telemetry in `backend/app/observability/metrics.py`

**Checkpoint**: User Story 1 (MVP) complete and testable independently.

---

## Phase 4: User Story 2 - Conditional Historical Archiving in Single Transaction (Priority: P2)

**Goal**: Batch insert historical scan candidate records into `market_data.scan_results` using parameterised 500-row chunking within the single atomic transaction when `save_history=true`.

**Independent Test**: Execute scan with `save_history=true` and `SCANNER_SINGLE_FINAL_WRITE_ENABLED=ON`. Confirm `latest_scan_results` and `market_data.scan_results` are updated atomically within 1 transaction block.

### Tests for User Story 2

- [X] T011 [P] [US2] Create integration test for conditional history batch persistence in `backend/app/tests/test_scanner_history_persistence.py`

### Implementation for User Story 2

- [X] T012 [US2] Implement parameterised 500-row chunked bulk insert for `market_data.scan_results` in `backend/app/services/scanner_single_write_service.py`
- [X] T013 [US2] Connect `save_history` flag evaluation in `backend/app/services/scan_execution_service.py` to route history inserts inside the single final transaction

**Checkpoint**: User Stories 1 AND 2 complete and independently testable.

---

## Phase 5: User Story 3 - Immediate Zero-Downtime Operational Rollback (Priority: P3)

**Goal**: Instantly revert scanner execution to legacy progressive persistence paths when `SCANNER_SINGLE_FINAL_WRITE_ENABLED` is set to `OFF`.

**Independent Test**: Toggle `SCANNER_SINGLE_FINAL_WRITE_ENABLED` from `ON` to `OFF` while backend service is running; verify next scan cycle uses legacy persistence without error.

### Tests for User Story 3

- [X] T014 [P] [US3] Create rollback test suite for dynamic feature flag toggle in `backend/app/tests/test_single_write_rollback.py`
- [X] T015 [US3] Implement dynamic feature flag evaluation and fail-safe fallback branching in `backend/app/services/scan_execution_service.py`
- [X] T016 [US3] Create API response parity test verifying identical payload across flag states in `backend/app/tests/test_latest_scan_service_unified.py`

**Checkpoint**: All user stories complete and testable independently.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, validation, and final operational readiness.

- [X] T017 [P] Update technical architecture documentation in `docs/SCANNER_SINGLE_FINAL_WRITE.md`
- [X] T018 Run complete validation suite per `specs/021-scanner-single-final-write/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - starts immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Stories (Phases 3-5)**: Depend on Foundational completion.
  - User Story 1 (P1 - MVP) -> User Story 2 (P2) -> User Story 3 (P3)
- **Polish (Phase 6)**: Depends on all user stories being complete.

### Parallel Opportunities

- T002 [P] and T003 [P], T004 [P] can run in parallel.
- Test creation tasks T005 [P], T006 [P], T011 [P], T014 [P] can run in parallel prior to story implementation.
- Documentation T017 [P] can run in parallel during polish phase.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1).
3. Test User Story 1 independently against PostgreSQL.
4. Validate that `latest_scan_results` updates in 1 transaction and dashboard APIs return 100% byte parity.

### Incremental Delivery
1. Add User Story 2 (History Retention) -> Validate 1-transaction multi-table commit.
2. Add User Story 3 (Feature Flag Rollback) -> Validate dynamic `ON`/`OFF` fallback.
3. Complete Phase 6 (Polish & Quickstart validation).
