# Tasks: Validation, Interaction Analysis, Point-Budget Rebalancing & Controlled Promotion

**Input**: Design documents from `/specs/015-shadow-promotion-rebalance/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- File paths are explicitly specified for every task.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Shared schemas and data structures for attribution telemetry and scoring configuration.

- [ ] T001 [P] Create Pydantic telemetry models (`AttributionReport`, `InteractionAnalysis`, `PromotionStateRecord`) in `backend/app/schemas/shadow_telemetry.py`
- [ ] T002 [P] Create `ScoringMatrixConfig` schema with `sum == 100.0` `@model_validator` in `backend/app/schemas/scoring_config.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core matrix and governance helper infrastructure required before user story implementation.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 [P] Implement base matrix validation and weight normalization helpers in `backend/app/services/scoring_matrix_service.py`

**Checkpoint**: Shared schemas and scoring matrix foundational infrastructure ready.

---

## Phase 3: User Story 1 - A/B Attribution & Interaction Analysis (Priority: P1) 🎯 MVP

**Goal**: Implement pure 4-way A/B ablation analysis (Baseline, Decay-Only, Breadth-Only, Combined) and Pearson/Spearman feature correlation analysis to generate decision-ready promotion reports.

**Independent Test**: Execute `AttributionValidationService` against historical shadow datasets, verifying 4-way ablation metrics, sample size safeguards ($<30 \to \text{INSUFFICIENT\_DATA}$), and correlation decision recommendations ($r < 0.70 \to \text{COMPLEMENTARY}$).

### Tasks for User Story 1

- [ ] T004 [P] [US1] Write unit tests for 4-way ablation math, sample size safeguards, and Pearson/Spearman correlation in `backend/tests/unit/test_attribution_validation.py`
- [ ] T005 [P] [US1] Implement pure `AttributionValidationService` with 4-way synthetic replay and feature correlation check in `backend/app/services/attribution_validation_service.py`
- [ ] T006 [US1] Add CLI governance command `experiment.report` in `backend/app/governance/experiment_cli.py`
- [ ] T007 [US1] Expose REST endpoints `GET /api/v1/governance/attribution-report` and `GET /api/v1/governance/interaction-check` in `backend/app/routes/governance.py`

**Checkpoint**: User Story 1 (Attribution & Interaction Analysis) fully testable and functional.

---

## Phase 4: User Story 2 - Point-Budget Matrix Rebalancing (Priority: P1)

**Goal**: Implement the 100-point rebalanced composite scoring matrix (Technical: 35, Sentiment: 25, Fundamental: 15, Volume: 15, Market Breadth: 10 = 100.0 Total) with strict mathematical sum invariant checks.

**Independent Test**: Pass proposed rebalanced scoring matrices to `ScoringMatrixService`, verifying total sum strictly equals 100.0 points, minimal disruption constraint (Fundamental reduced by 10), and bounds $[0, 100]$.

### Tasks for User Story 2

- [ ] T008 [P] [US2] Write unit tests for 100-point rebalanced matrix weights and sum invariant enforcement in `backend/tests/unit/test_scoring_matrix_rebalance.py`
- [ ] T009 [P] [US2] Implement `ScoringMatrixService` with default 100-point baseline and rebalanced matrix configs in `backend/app/services/scoring_matrix_service.py`
- [ ] T010 [US2] Integrate `ScoringMatrixService` weight resolution into composite recommendation calculation in `backend/app/services/recommendation_service.py`

**Checkpoint**: User Story 2 (Matrix Rebalancing) fully testable and functional.

---

## Phase 5: User Story 3 - Controlled Sequential Promotion & Kill-Switch Governance (Priority: P2)

**Goal**: Implement two-stage sequential promotion (Stage 1 Sentiment Time-Decay, Stage 2 Market Breadth) via `RuleManager` with instant kill-switch capabilities for both features.

**Independent Test**: Trigger Stage 1 promotion (`sentiment_decay`), verify live sentiment calculation updates while Market Breadth stays in shadow mode; trigger Stage 2 promotion (`market_breadth`), verify rebalanced matrix scoring; activate kill-switch, verify immediate fallback to baseline scoring in $<1\text{ms}$.

### Tasks for User Story 3

- [ ] T011 [P] [US3] Write integration tests for Stage 1 promotion, Stage 2 promotion, and instant Kill-Switch fallback in `backend/tests/integration/test_sequential_promotion.py`
- [ ] T012 [US3] Wire Stage 1 live Sentiment Time-Decay promotion check (`RuleManager().is_active_in_production("sentiment_decay")`) in `backend/app/services/recommendation_service.py` and `backend/app/agents/news_analysis_agent.py`
- [ ] T013 [US3] Wire Stage 2 live Market Breadth promotion check (`RuleManager().is_active_in_production("market_breadth")`) in `backend/app/services/recommendation_service.py` and `backend/app/agents/orchestrator_agent.py`
- [ ] T014 [US3] Expose REST endpoints `POST /api/v1/governance/rules/{rule_id}/promote` and `POST /api/v1/governance/rules/{rule_id}/kill` in `backend/app/routes/governance.py`

**Checkpoint**: All three user stories functional, sequentially wired, gated by RuleManager, and fully reversible via kill-switch.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation, quickstart execution, and final quality checks.

- [ ] T015 [P] Run full pytest suite for unit, integration, and promotion safety tests
- [ ] T016 [P] Execute validation scenarios defined in `specs/015-shadow-promotion-rebalance/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories.
- **User Stories (Phases 3 & 4 - P1)**: Can proceed in parallel after Foundational Phase completion.
- **User Story 3 (Phase 5 - P2)**: Depends on US1 and US2 implementation for full sequential promotion and rebalanced matrix integration.
- **Polish (Phase 6)**: Depends on completion of all user story phases.

### Parallel Opportunities

- **T001, T002, T003**: Setup and foundational tasks can be developed in parallel across schema files.
- **User Story 1 & User Story 2**: US1 (`attribution_validation_service.py`) and US2 (`scoring_matrix_service.py`) are independent services and can be implemented in parallel.
- **Unit Tests**: `test_attribution_validation.py` (T004) and `test_scoring_matrix_rebalance.py` (T008) can be written in parallel.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Setup (Phase 1) and Foundational (Phase 2).
2. Implement User Story 1 (A/B Attribution & Correlation Analysis).
3. Validate US1 independently with `pytest backend/tests/unit/test_attribution_validation.py`.

### Full Incremental Delivery
1. Add User Story 2 (100-Point Rebalanced Matrix) and validate independently with `pytest backend/tests/unit/test_scoring_matrix_rebalance.py`.
2. Add User Story 3 (Sequential Promotion & Kill-Switch Governance) and validate end-to-end with `pytest backend/tests/integration/test_sequential_promotion.py`.
3. Complete Polish & Quickstart validation.
