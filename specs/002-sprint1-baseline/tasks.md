# Tasks: Sprint 1 – Baseline & Diagnostics (Phase 0)

**Input**: Design documents from `specs/002-sprint1-baseline/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create module directories and initial boilerplate

- [x] T001 Create `backend/app/governance/` package with `__init__.py`
- [x] T002 [P] Create `backend/app/observability/schema.py` for input validation schemas
- [x] T003 [P] Create `frontend/src/components/Diagnostics/` directory with barrel export `index.ts`
- [x] T004 Create default alert rules config at `backend/app/config/alerts.yml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure that MUST be complete before user story work begins

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 [P] Implement Experiment SQLAlchemy model in `backend/app/models/experiment.py` (id, name, status, started_at, ended_at, duration_seconds, metadata, timestamps)
- [x] T006 [P] Implement file-based JSONL storage utility in `backend/app/core/jsonl_store.py` (append, query with time-range/level/source filtering, pagination)
- [x] T007 [P] Implement append-only audit file manager in `backend/app/core/audit_store.py` (append with hash chaining, integrity verification)
- [x] T008 [P] Add API key auth dependency reusing existing JWT security in `backend/app/core/security.py` — single admin role
- [x] T009 [P] Create `backend/app/observability/__init__.py` updating exports for new modules
- [x] T009b [P] Setup test infrastructure: conftest.py with tempfile fixtures for JSONL/audit stores in `backend/app/tests/conftest.py`

**Checkpoint**: Foundation ready — file storage, auth, and DB model available; user story implementation can begin

---

## Phase 3: User Story 1 — Governance & Experiment Lifecycle (Priority: P1) 🎯 MVP

**Goal**: Governance framework with experiment tracking (create, pause, resume, complete), audit trail, and agent command routing

**Independent Test**: Run `experiment start --name "test"` → `experiment list` → `experiment complete` and verify the log contains entries with timestamps and metadata

### Implementation for User Story 1

- [x] T010 [US1] Implement ExperimentService in `backend/app/governance/experiment.py` (CRUD, state machine enforcing single-active, terminal states)
- [x] T011 [US1] Implement CLI command handler in `backend/app/governance/experiment_cli.py` (start, pause, resume, complete, list, show, metric commands with Rich output)
- [x] T012 [US1] Implement experiment log persistence (metrics to file) in `backend/app/governance/experiment_log.py`
- [x] T013 [US1] Implement audit trail manager in `backend/app/governance/audit.py` (record governance actions, SHA-256 hash chaining)
- [x] T014 [US1] Implement agent command routing activation workflow in `backend/app/governance/router.py`
- [x] T015 [US1] Implement audit export command (JSON and CSV) in `backend/app/governance/experiment_cli.py`
- [x] T016 [US1] Handle US1 edge cases: disk-full on log write, creating experiment while one is active (rejected)
- [x] T017 [US1] Add input validation for all experiment CLI commands using schema from `schema.py`

### Tests for User Story 1

- [x] T017b [P] [US1] Unit test ExperimentService state machine in `backend/app/tests/governance/test_experiment.py`
- [x] T017c [P] [US1] Unit test CLI command parsing in `backend/app/tests/governance/test_experiment_cli.py`
- [x] T017d [P] [US1] Unit test audit trail hash chain in `backend/app/tests/governance/test_audit.py`

**Checkpoint**: At this point, User Story 1 should be fully functional. Experiments can be created, metrics added, completed, and queried. Audit trail records all actions. Agent commands route correctly.

---

## Phase 4: User Story 2 — Diagnostics Dashboard & Observability (Priority: P2)

**Goal**: Real-time diagnostics dashboard with log aggregation, monitoring alerts, and resource usage tracking

**Independent Test**: Generate sample metrics and log events, verify they appear in the dashboard and alerts trigger at configured thresholds

### Backend Implementation for User Story 2

- [x] T018 [P] [US2] Implement log aggregator in `backend/app/observability/log_aggregator.py` (ingest, query with level/source/time-range filters, pagination)
- [x] T019 [P] [US2] Implement alert engine in `backend/app/observability/alert_engine.py` (load YAML rules, evaluate metric streams, trigger with dedup within 60s window)
- [x] T020 [P] [US2] Implement resource tracker in `backend/app/observability/resource_tracker.py` (psutil-based CPU/memory/I/O per experiment window)
- [x] T021 [US2] Implement dashboard data provider in `backend/app/observability/dashboard.py` (aggregate system metrics + experiment resource usage)
- [x] T022 [US2] Implement dashboard API endpoints in `backend/app/routes/diagnostics.py` (GET /api/v1/dashboard/metrics, GET /api/v1/dashboard/logs, GET /api/v1/dashboard/alerts)
- [x] T023 [US2] Implement log ingest endpoint POST /api/v1/dashboard/logs/ingest in `backend/app/routes/diagnostics.py`
- [x] T024 [US2] Add validation for metric names, log levels, and filter parameters using schema from `schema.py`

### Frontend Implementation for User Story 2

- [x] T025 [P] [US2] Create MetricsPanel component in `frontend/src/components/Diagnostics/MetricsPanel.tsx` (CPU, memory, request rate, error rate with auto-refresh, error state when backend unreachable, retry button)
- [x] T026 [P] [US2] Create LogViewer component in `frontend/src/components/Diagnostics/LogViewer.tsx` (filterable log table with level/source/time-range, loading/empty/error states)
- [x] T027 [P] [US2] Create AlertsPanel component in `frontend/src/components/Diagnostics/AlertsPanel.tsx` (active alerts list with severity badges, empty state when no alerts)
- [x] T028 [P] [US2] Create ResourceUsagePanel component in `frontend/src/components/Diagnostics/ResourceUsagePanel.tsx` (per-experiment CPU/memory/I/O charts, disabled state when no active experiment)
- [x] T029 [US2] Create Diagnostics page in `frontend/src/pages/Diagnostics.tsx` composing all panels with layout and auto-refresh
- [x] T030 [US2] Add Diagnostics route to frontend router in `frontend/src/App.tsx` with 5-second auto-refresh

### Tests for User Story 2

- [x] T030b [P] [US2] Unit test log aggregator ingest+query in `backend/app/tests/observability/test_log_aggregator.py`
- [x] T030c [P] [US2] Unit test alert engine evaluation+dedup in `backend/app/tests/observability/test_alert_engine.py`
- [x] T030d [P] [US2] Unit test resource tracker in `backend/app/tests/observability/test_resource_tracker.py`
- [x] T030e [P] [US2] Unit test dashboard API endpoints in `backend/app/tests/observability/test_dashboard.py`

**Checkpoint**: At this point, User Stories 1 AND 2 should both work. Dashboard displays system metrics, logs, alerts, and experiment resource usage.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, hardening, and verification

- [x] T031 [P] Handle CPU/resource usage reporting edge case — process not found (container stopped mid-experiment)
- [x] T032 [P] Handle clock skew in audit timestamps — accept up to 5s skew, warn beyond that
- [x] T033 [P] Handle large export memory — stream CSV/JSON export instead of buffering full dataset
- [x] T034 [P] Handle out-of-order metric timestamps — sort by timestamp on query
- [x] T035 [P] Add disk-space check before writing to log/audit files — warn if <100MB free
- [x] T036 [P] Handle dashboard backend unreachable — show error state in frontend panels with retry button
- [x] T037 [P] Add rate limiting to log ingest endpoint to prevent abuse
- [x] T038 [P] Add Prometheus-style metrics endpoint for future monitoring integration in `backend/app/routes/diagnostics.py`
- [x] T038b [P] Implement log rotation: archive JSONL files older than 90 days in `backend/app/core/jsonl_store.py`
- [x] T038c Add performance verification script for SC-001–SC-007 in `specs/002-sprint1-baseline/benchmark.py`
- [ ] T039 Run `specs/002-sprint1-baseline/quickstart.md` validation scenarios and fix any failures

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 — Governance (Phase 3)**: Depends on Foundational — independent, no story dependencies
- **US2 — Diagnostics (Phase 4)**: Depends on Foundational — soft dependency on US1 (can test with sample data alone; integrates with experiments when both complete)
- **Polish (Phase 5)**: Depends on US1 and US2 being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational — no dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational — independently testable with sample metrics; full integration with US1 when both stories complete

### Within Each Phase

- Models/utilities before services
- Services before endpoints/CLI
- Backend endpoints before frontend components
- Story complete before moving to next phase

### Parallel Opportunities

- All Phase 1 tasks marked [P] can run in parallel
- All Phase 2 foundational tasks marked [P] can run in parallel
- US1 backend tasks [P] can run in parallel (experiment + audit + router)
- US2 backend tasks [P] can run in parallel (log aggregator, alert engine, resource tracker)
- US2 frontend components [P] can run in parallel (MetricsPanel, LogViewer, AlertsPanel, ResourceUsagePanel)
- US2 backend + frontend can proceed in parallel within the phase
- All Phase 5 [P] tasks can run in parallel

---

## Parallel Example

```bash
# Phase 2 — Foundational (all can be parallel):
Task: "Implement Experiment SQLAlchemy model"
Task: "Implement file-based JSONL storage utility"
Task: "Implement append-only audit file manager"
Task: "Add API key auth dependency"
Task: "Update observability init exports"

# US1 — Governance (models first, then CLI + audit in parallel):
Task: "ExperimentService" (depends on T005 Experiment model)
Task: "CLI command handler" + "Experiment log" + "Audit trail" (parallel, depend on T010)

# US2 — Backend services (all parallel):
Task: "Log aggregator" + "Alert engine" + "Resource tracker" + "Dashboard data provider"

# US2 — Frontend components (all parallel):
Task: "MetricsPanel" + "LogViewer" + "AlertsPanel" + "ResourceUsagePanel"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (Governance)
4. **STOP and VALIDATE**: Test experiment lifecycle independently
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 (Governance) → Test independently → Deploy (MVP!)
3. Add US2 (Diagnostics) → Test independently → Deploy
4. Each story adds value without breaking previous stories

### Parallel Team Strategy

1. Complete Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Governance)
   - Developer B: User Story 2 Backend (log aggregator, alert engine, resource tracker, dashboard API)
   - Developer C: User Story 2 Frontend (Diagnostics page and components)
3. Stories integrate and complete independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- File paths follow the existing project structure: `backend/app/` for Python, `frontend/src/` for TypeScript/React
