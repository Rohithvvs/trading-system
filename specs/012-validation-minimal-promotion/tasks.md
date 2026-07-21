---

description: "Task list for Validation & Minimal Promotion feature implementation"
---

# Tasks: Validation & Minimal Promotion

**Input**: Design documents from `/specs/012-validation-minimal-promotion/`
**Prerequisites**: [plan.md](file:///D:/Work_Space/trading-system/specs/012-validation-minimal-promotion/plan.md), [spec.md](file:///D:/Work_Space/trading-system/specs/012-validation-minimal-promotion/spec.md), [research.md](file:///D:/Work_Space/trading-system/specs/012-validation-minimal-promotion/research.md), [data-model.md](file:///D:/Work_Space/trading-system/specs/012-validation-minimal-promotion/data-model.md), [contracts/](file:///D:/Work_Space/trading-system/specs/012-validation-minimal-promotion/contracts/)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create report outputs directory at `governance/reports/`
- [x] T002 Initialize default rule states configuration at `backend/app/config/rule_states.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure configuration and helper definitions

**⚠️ CRITICAL**: All foundational tasks must be complete before beginning user story implementations.

- [x] T003 [P] Add state and report directory path settings to `backend/app/config/settings.py`
- [x] T004 [P] Create RuleManager stub with state enum definitions in `backend/app/governance/rule_manager.py`
- [x] T005 [P] Create ValidationReportGenerator class skeleton in `backend/app/services/validation_report.py`

**Checkpoint**: Foundation ready - user story implementation can begin.

---

## Phase 3: User Story 1 - Challenger Validation Report (Priority: P1) 🎯 MVP

**Goal**: Generate machine-readable JSON and human-readable Markdown reports containing operational and false-positive metrics for the `news_dedup` shadow rule over a 14-day window.

**Independent Test**: Running the CLI report generation command creates [challenger_report_news_dedup.json](file:///D:/Work_Space/trading-system/specs/012-validation-minimal-promotion/data-model.md#2-challenger-validation-report-schema-challenger_report_news_dedupjson) and a Markdown summary in `governance/reports/`.

### Tests for User Story 1
- [x] T006 [P] [US1] Create unit tests verifying validation report metric calculations and outputs in `backend/tests/unit/test_validation_report.py`

### Implementation for User Story 1
- [x] T007 [US1] Implement database querying for past 14 days of shadow `AnalysisHistory` records in `backend/app/services/validation_report.py`
- [x] T008 [US1] Implement false-positive correlation query checking `LiveOrder` fills within 24 hours of signal creation in `backend/app/services/validation_report.py`
- [x] T009 [US1] Implement structured JSON/Markdown file export logic in `backend/app/services/validation_report.py`
- [x] T010 [US1] Implement CLI `report` subcommand parser and formatting output in `backend/app/governance/experiment_cli.py`
- [x] T011 [US1] Register `experiment.report` command route mapping in `backend/app/governance/router.py`

**Checkpoint**: User Story 1 is fully functional and testable independently.

---

## Phase 4: User Story 2 - Minimal Promotion Gate & Kill-Switch (Priority: P1)

**Goal**: Expose explicit promote and kill administrative commands to control rule lifecycle state (`shadow`, `production`, `disabled`).

**Independent Test**: Running promote/kill CLI subcommands updates [rule_states.json](file:///D:/Work_Space/trading-system/specs/012-validation-minimal-promotion/data-model.md#1-rule-lifecycle-state-store-rule_statesjson) and creates an event log in `logs/audit.jsonl`.

### Tests for User Story 2
- [x] T012 [P] [US2] Create unit tests verifying state transitions, validation, and caching in `backend/tests/unit/test_rule_manager.py`

### Implementation for User Story 2
- [x] T013 [US2] Implement state JSON file read/write operations with thread-safe local caching in `backend/app/governance/rule_manager.py`
- [x] T014 [US2] Implement `promote_rule` requiring `--checklist-approved` assertion validation in `backend/app/governance/rule_manager.py`
- [x] T015 [US2] Implement `kill_rule` with transition logging via `AuditTrailManager` in `backend/app/governance/rule_manager.py`
- [x] T016 [US2] Implement CLI `promote` and `kill` subcommands in `backend/app/governance/experiment_cli.py`
- [x] T017 [US2] Register command routes for `experiment.promote` and `experiment.kill` in `backend/app/governance/router.py`

**Checkpoint**: User Story 2 is fully functional and testable independently.

---

## Phase 5: User Story 3 - Controlled Promotion Path Integration (Priority: P1)

**Goal**: Wire the recommendation pipeline to use deduplicated articles in-line when the rule is in `production` state, and revert to undeduplicated articles if rule is `shadow` or `disabled`.

**Independent Test**: Seed rule state to `production`, trigger `NewsAnalysisAgent.run()`, and verify that in-line deduplication is executed. Revert state to `disabled`, run agent, and verify deduplication is bypassed.

### Tests for User Story 3
- [x] T018 [P] [US3] Create integration tests verifying dynamic pipeline routing, shadow execution fallback, and instant kill switches in `backend/tests/integration/test_promotion_flow.py`

### Implementation for User Story 3
- [x] T019 [US3] Update `NewsAnalysisAgent.run()` imports and call `RuleManager.is_active_in_production("news_dedup")` in `backend/app/agents/news_analysis_agent.py`
- [x] T020 [US3] Add branch routing to apply in-line article deduplication before sentiment scoring when promoted in `backend/app/agents/news_analysis_agent.py`
- [x] T021 [US3] Ensure background shadow task execution is bypassed when rule state is `"production"` or `"disabled"` in `backend/app/agents/news_analysis_agent.py`

**Checkpoint**: All user stories are independently functional and integrated.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup, documentation, and validation checks

- [x] T022 [P] Document rule states CLI usage instructions in `README.md`
- [x] T023 Run end-to-end validation scenarios documented in [quickstart.md](file:///D:/Work_Space/trading-system/specs/012-validation-minimal-promotion/quickstart.md)

---

## Dependencies & Execution Order

### Phase Dependencies
* **Phase 1 (Setup)**: Can start immediately.
* **Phase 2 (Foundational)**: Depends on Phase 1. Blocks all subsequent User Story phases.
* **Phase 3 (US1)**, **Phase 4 (US2)**, **Phase 5 (US3)**: Depend on Phase 2 completion. Can be worked on in parallel.
* **Phase 6 (Polish)**: Depends on completion of all user story implementations.

### Execution Plan (MVP First)
1. Complete Setup (T001-T002) and Foundational (T003-T005) phases.
2. Implement User Story 1 (T006-T011) to enable validation reporting (MVP).
3. Implement User Story 2 (T012-T017) to provide lifecycle promotion/kill gate.
4. Implement User Story 3 (T018-T021) to dynamically switch production paths.
5. Complete Polish and run quickstart verification (T022-T023).

### Parallel Opportunities
* Foundational tasks (T003, T004, T005) can be completed in parallel.
* Unit test suites (T006, T012, T018) can be developed concurrently with their corresponding implementations.
