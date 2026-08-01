# Tasks: Shadow Candidate Features — Sentiment Time-Decay & Market Breadth

**Input**: Design documents from `/specs/014-shadow-sentiment-breadth/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- File paths are explicitly specified for every task.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Shared schema definitions and data structures for shadow candidate features.

- [X] T001 [P] Create Pydantic data schemas for sentiment decay and market breadth telemetry payloads in `backend/app/schemas/shadow_telemetry.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure and telemetry helpers that MUST be complete before user story execution.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Verify and update `AnalysisHistory` ORM model support for `shadow_outputs` dictionary normalization in `backend/app/models/analysis.py`
- [X] T003 [P] Add normalization and persistence helpers for `sentiment_decay` and `market_breadth` shadow keys in `backend/app/services/shadow_executor.py`

**Checkpoint**: Shared schemas and shadow telemetry persistence infrastructure ready.

---

## Phase 3: User Story 1 - Shadow Sentiment Time-Decay Evaluation (Priority: P1) 🎯 MVP

**Goal**: Implement pure sentiment time-decay logic (FEAT-018) with exponential decay, 72-hour hard cutoff, and shadow execution.

**Independent Test**: Supply news articles with varied publication ages to `calculate_sentiment_time_decay`, verifying exponential decay math, 72h zero cutoff, and telemetry persistence without altering live scores.

### Tasks for User Story 1

- [X] T004 [P] [US1] Write unit tests for exponential decay math, 72h cutoff, and missing timestamp edge cases in `backend/tests/unit/test_sentiment_decay.py`
- [X] T005 [P] [US1] Implement pure `calculate_sentiment_time_decay` function with exponential decay and 72h cutoff in `backend/app/services/sentiment_decay.py`
- [X] T006 [US1] Implement `execute_shadow_sentiment_decay` worker in `backend/app/services/shadow_executor.py`
- [X] T007 [US1] Submit shadow sentiment decay via `OrchestratorAgent._submit_shadow_candidate_features` **after** `AnalysisHistory` persist (independent of `news_dedup` lifecycle) in `backend/app/agents/orchestrator_agent.py`

**Checkpoint**: User Story 1 (Sentiment Time-Decay) fully testable and functional in Shadow Mode.

---

## Phase 4: User Story 2 - Shadow Market Breadth Assessment (Priority: P1)

**Goal**: Implement pure market breadth calculation (FEAT-016) measuring 200-day moving average participation, regime labeling, and small-universe guard rails in Shadow Mode.

**Independent Test**: Pass universe stock prices and 200-day moving averages to `calculate_market_breadth`, verifying regime labels (`strong` to `very_weak`), soft contribution scores, and invalidation guard rails for universes $<10$ stocks.

### Tasks for User Story 2

- [X] T008 [P] [US2] Write unit tests for 200-day MA percentage calculation, 5 regime tiers, and small universe guard rails in `backend/tests/unit/test_market_breadth.py`
- [X] T009 [P] [US2] Implement pure `calculate_market_breadth` function and regime mapping matrix in `backend/app/services/market_breadth.py`
- [X] T010 [US2] Implement `execute_shadow_market_breadth` worker in `backend/app/services/shadow_executor.py`
- [X] T011 [US2] Submit shadow market breadth via `OrchestratorAgent._submit_shadow_candidate_features` with **full bulk-universe** price/SMA200 rows after persist in `backend/app/agents/orchestrator_agent.py`

**Checkpoint**: User Story 2 (Market Breadth) fully testable and functional in Shadow Mode.

---

## Phase 5: User Story 3 - Fault-Isolated Parallel Shadow Execution (Priority: P2)

**Goal**: Verify concurrent submission, non-overwriting telemetry persistence (`shadow_outputs`), strict fault isolation, and production score identity.

**Independent Test**: Run live scan simulation where both shadow features execute simultaneously, verify all shadow keys (`news_dedup`, `sentiment_decay`, `market_breadth`) persist, crash one shadow rule to verify zero impact on the other rule or production scoring.

### Tasks for User Story 3

- [X] T012 [P] [US3] Write integration tests for concurrent execution and non-overwriting JSONB dictionary updates in `backend/tests/integration/test_parallel_shadow_features.py`
- [X] T013 [P] [US3] Write integration tests for deliberate shadow crash isolation and production score identity verification in `backend/tests/integration/test_parallel_shadow_features.py`
- [X] T014 [US3] Add `query_shadow_candidates_by_situation_tags` for Sprint 8 A/B ablation (tags + `sentiment_decay` / `market_breadth`) in `backend/app/services/analytics_service.py`

**Checkpoint**: All three user stories functional, concurrently wired, fault-isolated, and ready for analytics.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation, quickstart execution, and final quality checks.

- [X] T015 [P] Run full pytest suite for unit and integration shadow tests
- [X] T016 [P] Execute validation scenarios defined in `specs/014-shadow-sentiment-breadth/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories.
- **User Stories (Phases 3 & 4 - P1)**: Can proceed in parallel after Foundational Phase completion.
- **User Story 3 (Phase 5 - P2)**: Depends on US1 and US2 implementation for full parallel integration verification.
- **Polish (Phase 6)**: Depends on completion of all user story phases.

### Parallel Opportunities

- **T001, T002, T003**: Setup and foundational tasks can be developed in parallel across schemas and executor files.
- **User Story 1 & User Story 2**: US1 (`sentiment_decay.py`) and US2 (`market_breadth.py`) are completely independent pure functions and can be implemented in parallel by different developers.
- **Unit Tests**: `test_sentiment_decay.py` (T004) and `test_market_breadth.py` (T008) can be written in parallel.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Setup (Phase 1) and Foundational (Phase 2).
2. Implement User Story 1 (Sentiment Time-Decay).
3. Validate US1 independently with `pytest backend/tests/unit/test_sentiment_decay.py`.

### Full Incremental Delivery
1. Add User Story 2 (Market Breadth) and validate independently with `pytest backend/tests/unit/test_market_breadth.py`.
2. Add User Story 3 (Parallel Wiring & Fault Isolation) and validate end-to-end with `pytest backend/tests/integration/test_parallel_shadow_features.py`.
3. Complete Polish & Quickstart validation.
