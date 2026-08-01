# Tasks: Unify Latest-Scan APIs

**Input**: Design documents from `/specs/018-unify-latest-scan-apis/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `- [ ] [ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)
- Include exact file paths in all task descriptions.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configure feature flag and project settings for Sprint 2.

- [x] T001 Configure feature flag `SCANNER_UNIFIED_LATEST_ENABLED` in `backend/app/config/settings.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core canonical service methods and cache integration that MUST be completed before endpoint migration begins.

**⚠️ CRITICAL**: Endpoint delegation cannot begin until `LatestScanService.get_latest_scan()` is fully implemented and tested.

- [x] T002 Implement `LatestScanService.get_latest_scan(format_type: str, force: bool)` master method in `backend/app/services/latest_scan_service.py`
- [x] T003 [P] Implement `_format_dashboard_payload` adapter method in `backend/app/services/latest_scan_service.py`
- [x] T004 [P] Implement `_format_analysis_payload` adapter method in `backend/app/services/latest_scan_service.py`
- [x] T005 Integrate `scanner_cache_service.resolve_latest_scan()` into `get_latest_scan()` in `backend/app/services/latest_scan_service.py`
- [x] T006 Write unit tests for format adapters in `backend/app/tests/test_latest_scan_service_unified.py`

**Checkpoint**: Foundation ready - canonical service methods and unit tests complete. Endpoint migration can now begin.

---

## Phase 3: User Story 1 - Unified Dashboard Scan Access (Priority: P1) 🎯 MVP

**Goal**: Migrate `GET /scanner/latest` to delegate scan snapshot retrieval to `LatestScanService.get_latest_scan("dashboard")` when `SCANNER_UNIFIED_LATEST_ENABLED` is `true`.

**Independent Test**: Request `GET /scanner/latest` under `SCANNER_UNIFIED_LATEST_ENABLED=true` and verify response schema, status codes, and `buy_candidates`/`watch_candidates`/`rejected_candidates` sorting match legacy responses 100%.

### Tests for User Story 1

- [x] T007 [P] [US1] Create integration test for `GET /scanner/latest` dual-path parity in `backend/app/tests/test_unified_latest_scan_parity.py`

### Implementation for User Story 1

- [x] T008 [US1] Update `GET /scanner/latest` route handler to check `SCANNER_UNIFIED_LATEST_ENABLED` and delegate to `LatestScanService.get_latest_scan("dashboard")` in `backend/app/routes/scanner.py`
- [x] T009 [US1] Verify `X-Cache-Status` response header and diagnostic logging (`log_dashboard_request`) for `/scanner/latest` in `backend/app/routes/scanner.py`

**Checkpoint**: User Story 1 is complete and independently testable (MVP deliverable).

---

## Phase 4: User Story 2 - Unified Analysis Scan Access (Priority: P1)

**Goal**: Migrate `GET /analysis/scan/latest` to delegate scan snapshot retrieval to `LatestScanService.get_latest_scan("analysis")` when `SCANNER_UNIFIED_LATEST_ENABLED` is `true`.

**Independent Test**: Request `GET /analysis/scan/latest` under `SCANNER_UNIFIED_LATEST_ENABLED=true` and verify `available`, `timestamp`, and `items` payload matches legacy responses 100%.

### Tests for User Story 2

- [x] T010 [P] [US2] Create integration test for `GET /analysis/scan/latest` dual-path parity in `backend/app/tests/test_unified_latest_scan_parity.py`

### Implementation for User Story 2

- [x] T011 [US2] Update `GET /analysis/scan/latest` route handler to check `SCANNER_UNIFIED_LATEST_ENABLED` and delegate to `LatestScanService.get_latest_scan("analysis")` in `backend/app/routes/analysis.py`
- [x] T012 [US2] Verify `X-Cache-Status` response header and logging for `/analysis/scan/latest` in `backend/app/routes/analysis.py`

**Checkpoint**: User Stories 1 AND 2 are both complete and independently testable.

---

## Phase 5: User Story 3 - Dynamic Zero-Downtime Rollback (Priority: P2)

**Goal**: Ensure runtime toggling of `SCANNER_UNIFIED_LATEST_ENABLED` instantly switches between unified and legacy execution paths without application restarts.

**Independent Test**: Dynamically change setting from `true` to `false` during automated request execution and verify legacy code paths execute with zero errors.

### Tests for User Story 3

- [x] T013 [P] [US3] Create feature flag toggle and runtime fallback test in `backend/app/tests/test_feature_flag_toggle.py`

### Implementation for User Story 3

- [x] T014 [US3] Add fallback error handling in route handlers to revert to legacy logic on unexpected service exceptions in `backend/app/routes/scanner.py` and `backend/app/routes/analysis.py`

**Checkpoint**: All user stories complete with safe rollback mechanism verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: System-wide verification and documentation updates.

- [x] T015 Run full integration test suite in `backend/app/tests/test_scanner_routes_cached.py`
- [x] T016 Run quickstart validation scenarios defined in `specs/018-unify-latest-scan-apis/quickstart.md`
- [x] T017 [P] Update API inventory documentation in `docs/architecture/APIInventory.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - starts immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001) - BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion (T002-T006).
- **User Story 2 (Phase 4)**: Depends on Foundational phase completion (T002-T006). Can run in parallel with US1.
- **User Story 3 (Phase 5)**: Depends on US1 and US2 route handler updates (T008, T011).
- **Polish (Phase 6)**: Depends on all user stories being complete.

### Parallel Opportunities

- T003 (`_format_dashboard_payload`) and T004 (`_format_analysis_payload`) can run in parallel.
- T007 (`[US1]` parity test) and T010 (`[US2]` parity test) can run in parallel.
- Once Phase 2 completes, User Story 1 (Phase 3) and User Story 2 (Phase 4) can proceed in parallel.
- T017 (`APIInventory.md` update) can run in parallel with test verification tasks.

---

## Parallel Execution Examples

```bash
# Phase 2 Parallel Execution (Adapters):
Task: "Implement _format_dashboard_payload adapter method in backend/app/services/latest_scan_service.py" (T003)
Task: "Implement _format_analysis_payload adapter method in backend/app/services/latest_scan_service.py" (T004)

# User Story Parallel Execution (Parity Tests):
Task: "Create integration test for GET /scanner/latest dual-path parity in backend/app/tests/test_unified_latest_scan_parity.py" (T007)
Task: "Create integration test for GET /analysis/scan/latest dual-path parity in backend/app/tests/test_unified_latest_scan_parity.py" (T010)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1: Setup (T001).
2. Complete Phase 2: Foundational (T002 - T006).
3. Complete Phase 3: User Story 1 (T007 - T009).
4. **VALIDATE**: Run `pytest backend/app/tests/test_unified_latest_scan_parity.py` for `/scanner/latest`.

### Incremental Delivery
1. Foundation complete (T001-T006).
2. Add US1 (`/scanner/latest` unified) → Validate MVP.
3. Add US2 (`/analysis/scan/latest` unified) → Validate deep analysis parity.
4. Add US3 (Dynamic rollback & exception fallbacks) → Validate zero-downtime safety.
5. Complete Phase 6 (Polish & Docs).
