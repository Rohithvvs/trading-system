# Tasks: Operational Governance & Analytics Layer

**Input**: Design documents from `/specs/016-operational-governance-analytics/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are included for each user story to ensure TDD and automated validation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Includes exact file paths in all descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Base configuration and governance CLI route registration

- [x] T001 Verify baseline metrics configuration in `baseline_v1.0.json`
- [x] T002 [P] Register governance report command route in `AGENTS.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schemas and database row-locking helpers required across stories

**⚠️ CRITICAL**: Must complete before user story implementation begins

- [x] T003 Create governance and analytics schemas in `backend/app/schemas/governance.py`
- [x] T004 [P] Verify `AnalysisHistory.shadow_outputs` PostgreSQL JSONB atomic merge helper in `backend/app/services/shadow_executor.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Production Rule Governance Review (Priority: P1) 🎯 MVP

**Goal**: Automated weekly governance review measuring 30-day rolling false-positive rates of promoted rules against baselines, assigning health statuses (`GREEN`, `YELLOW`, `RED`, `INSUFFICIENT_DATA`), and generating machine-readable reports.

**Independent Test**: Execute `python -m app.governance.experiment_cli governance-report` or run `pytest backend/app/tests/test_rule_governance.py -v`.

### Tests for User Story 1

- [x] T005 [P] [US1] Create unit & integration tests for rule governance evaluation in `backend/app/tests/test_rule_governance.py`

### Implementation for User Story 1

- [x] T006 [US1] Implement baseline loading and 30-day false-positive rate calculator in `backend/app/governance/rule_governance.py`
- [x] T007 [US1] Implement status assignment logic (`GREEN`/`YELLOW`/`RED`/`INSUFFICIENT_DATA`) with sample-size protection ($N_{\text{min}}=15$) in `backend/app/governance/rule_governance.py`
- [x] T008 [US1] Expose `governance-report` CLI handler and command integration in `backend/app/governance/experiment_cli.py`

**Checkpoint**: User Story 1 is fully functional and testable independently via CLI and test suite.

---

## Phase 4: User Story 2 - Passive Sector Strength Tracking in Shadow Mode (Priority: P2)

**Goal**: Passive watch-only calculation of sector performance relative to broader market benchmarks executed via `ShadowThreadPool` during market scans and persisted to `shadow_outputs["sector_strength"]` with 0% live scoring impact.

**Independent Test**: Run `pytest backend/app/tests/test_sector_strength.py -v`.

### Tests for User Story 2

- [x] T009 [P] [US2] Create unit & integration tests for sector strength calculation and shadow isolation in `backend/app/tests/test_sector_strength.py`

### Implementation for User Story 2

- [x] T010 [P] [US2] Implement pure relative sector return calculation and labeling logic in `backend/app/services/sector_strength.py`
- [x] T011 [US2] Implement shadow executor wrapper `execute_shadow_sector_strength` and `ShadowThreadPool` task submission in `backend/app/services/shadow_executor.py`
- [x] T012 [US2] Integrate passive sector strength shadow trigger into market scan execution in `backend/app/agents/orchestrator_agent.py`

**Checkpoint**: User Stories 1 and 2 work independently without interfering with live scoring.

---

## Phase 5: User Story 3 - Operational Analytics Endpoints (Priority: P3)

**Goal**: Three programmatic FastAPI dashboard endpoints (`/engine-health`, `/shadow-status`, `/rule-governance`) delivering instant visibility without manual SQL queries.

**Independent Test**: Run `pytest backend/app/tests/test_analytics_dashboard.py -v`.

### Tests for User Story 3

- [x] T013 [P] [US3] Create API contract and endpoint tests for analytics dashboard in `backend/app/tests/test_analytics_dashboard.py`

### Implementation for User Story 3

- [x] T014 [US3] Implement `GET /api/v1/analytics/engine-health` endpoint in `backend/app/routes/analytics.py`
- [x] T015 [US3] Implement `GET /api/v1/analytics/shadow-status` endpoint in `backend/app/routes/analytics.py`
- [x] T016 [US3] Implement `GET /api/v1/analytics/rule-governance` endpoint in `backend/app/routes/analytics.py`
- [x] T017 [US3] Register `analytics_router` in FastAPI router registry in `backend/app/routes/__init__.py`

**Checkpoint**: All 3 user stories are independently functional and exposed via REST API and CLI.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verification, documentation, and regression testing across all stories

- [x] T018 [P] Update OpenAPI specifications and API documentation for analytics endpoints in `docs.html`
- [x] T019 Run quickstart verification scenarios in `specs/016-operational-governance-analytics/quickstart.md`
- [x] T020 Run full backend test suite (`pytest backend/app/tests/ -v`) to verify zero regressions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories.
- **User Stories (Phase 3+)**: All depend on Foundational phase completion.
  - Can proceed sequentially (US1 → US2 → US3) or in parallel.
- **Polish (Phase 6)**: Depends on all user stories being completed.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2). No dependencies on other stories.
- **User Story 2 (P2)**: Can start after Foundational (Phase 2). Independent of US1.
- **User Story 3 (P3)**: Can start after Foundational (Phase 2). Integrates governance summary from US1 into API.

---

## Parallel Opportunities

- **Setup & Foundational**: T002 and T004 marked `[P]` can run in parallel.
- **User Story 1**: T005 test writing can run in parallel with setup.
- **User Story 2**: T009 test writing and T010 pure calculation module can run in parallel (`[P]`).
- **User Story 3**: T013 test writing can run in parallel with US1/US2 (`[P]`).

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1 (Setup) + Phase 2 (Foundational).
2. Implement Phase 3 (User Story 1).
3. Validate via `python -m app.governance.experiment_cli governance-report`.

### Full Incremental Delivery
1. Complete Foundation.
2. Deliver US1 (Rule Governance) $\rightarrow$ MVP.
3. Deliver US2 (Sector Strength Shadow Collection) $\rightarrow$ Regime dataset accumulation.
4. Deliver US3 (Analytics Dashboard) $\rightarrow$ Observability endpoints.
5. Complete Polish & Verification.
