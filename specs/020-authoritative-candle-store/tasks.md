# Tasks: Authoritative Candle Store (Sprint 4)

**Input**: Design documents from `/specs/020-authoritative-candle-store/`  
**Prerequisites**: [plan.md](file:///D:/Work_Space/trading-system/specs/020-authoritative-candle-store/plan.md), [spec.md](file:///D:/Work_Space/trading-system/specs/020-authoritative-candle-store/spec.md), [research.md](file:///D:/Work_Space/trading-system/specs/020-authoritative-candle-store/research.md), [data-model.md](file:///D:/Work_Space/trading-system/specs/020-authoritative-candle-store/data-model.md), [contracts/authoritative_candle_store_api.md](file:///D:/Work_Space/trading-system/specs/020-authoritative-candle-store/contracts/authoritative_candle_store_api.md)  

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify configuration parameters and feature flag wiring.

- [X] T001 Verify project configuration for feature flag `AUTHORITATIVE_CANDLE_STORE_ENABLED` in `backend/app/config/settings.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core validation and caching modules that MUST be complete before user stories begin.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Create candle validation engine in `backend/app/services/candle_validation_engine.py`
- [X] T003 [P] Create L1 in-memory LRU cache in `backend/app/services/l1_candle_cache.py`
- [X] T004 Create core `AuthoritativeCandleStore` service shell in `backend/app/services/authoritative_candle_store.py` (depends on T002, T003)

**Checkpoint**: Foundation ready - user story implementation can now begin.

---

## Phase 3: User Story 1 - Unified Scanner & Analysis Candle Retrieval (Priority: P1) 🎯 MVP

**Goal**: Scanner and Deep Technical Analysis retrieve byte-level identical candle arrays from Authoritative Store.

**Independent Test**: Execute scanner scan loop and trigger `POST /analysis/full` for shortlisted symbol; confirm identical candles served from Authoritative Store with L1/L2 cache hit ratio > 90%.

### Tests for User Story 1

- [X] T005 [P] [US1] Unit test for L1 cache and OHLC validation in `tests/test_l1_candle_cache.py`
- [X] T006 [P] [US1] Unit test for `AuthoritativeCandleStore` get_candles in `tests/test_authoritative_candle_store.py`

### Implementation for User Story 1

- [X] T007 [US1] Implement `get_candles()` multi-tier read routing (L1 RAM -> L2 DB -> L3 Provider) in `backend/app/services/authoritative_candle_store.py`
- [X] T008 [US1] Update `FyersService.fetch_ohlcv()` in `backend/app/services/fyers_service.py` to route candle queries through `AuthoritativeCandleStore` when feature flag is ON
- [X] T009 [US1] Update `OrchestratorAgent` pre-fetch loop in `backend/app/agents/orchestrator_agent.py` to consume `AuthoritativeCandleStore`
- [X] T010 [US1] Update Stock REST API endpoints in `backend/app/routes/stocks.py` to consume `AuthoritativeCandleStore` (via RouterAgent → Orchestrator/Fyers ACS gate; documented at REST boundary)
- [X] T011 [US1] Integration test for unified scanner and analysis candle retrieval in `tests/integration/test_candle_store_unified.py`

**Checkpoint**: At this point, User Story 1 (MVP) is fully functional and independently testable.

---

## Phase 4: User Story 2 - Instant Operational Rollback Capability (Priority: P1)

**Goal**: System administrator can instantly disable Authoritative Candle Store via feature flag with zero downtime.

**Independent Test**: Set `AUTHORITATIVE_CANDLE_STORE_ENABLED=false` at runtime; confirm system instantly reverts to legacy candle retrieval without errors or restarts.

### Tests for User Story 2

- [X] T012 [P] [US2] Unit test for feature flag toggle routing in `tests/test_candle_store_feature_flag.py`

### Implementation for User Story 2

- [X] T013 [US2] Implement dynamic feature flag evaluation wrapper in `backend/app/services/authoritative_candle_store.py`
- [X] T014 [US2] Implement non-blocking async dual-write sync handler in `backend/app/services/authoritative_candle_store.py` for Phase 1/2 dual-write operations
- [X] T015 [US2] Integration test for instant feature flag toggle and rollback recovery in `tests/integration/test_candle_store_rollback.py`

**Checkpoint**: User Story 2 rollback and dual-write capabilities are independently functional and verified.

---

## Phase 5: User Story 3 - Automatic Gap Filling & Backfill (Priority: P2)

**Goal**: Backtest and historical queries with missing date ranges automatically backfill missing head/tail windows from provider.

**Independent Test**: Query a symbol date range with partial DB coverage; confirm store fetches missing window from FYERS, persists to PostgreSQL `historical_candles`, and returns unified continuous series.

### Tests for User Story 3

- [X] T016 [P] [US3] Unit test for date gap detection and range stitching in `tests/test_candle_gap_filler.py`

### Implementation for User Story 3

- [X] T017 [US3] Implement `ingest_candles()` idempotent batch upsert (`ON CONFLICT DO UPDATE`) in `backend/app/services/authoritative_candle_store.py`
- [X] T018 [US3] Implement gap detection and provider backfill stitching in `backend/app/services/authoritative_candle_store.py`
- [X] T019 [US3] Update `BacktestAgent` in `backend/app/agents/backtest_agent.py` to query historical windows through `AuthoritativeCandleStore`
- [X] T020 [US3] Integration test for automatic gap filling and historical persistence in `tests/integration/test_candle_store_gap_fill.py`

**Checkpoint**: All user stories are now independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Observability, audit background workers, logging, and validation scenarios.

- [X] T021 [P] Implement automated `validate_consistency` background audit worker in `backend/app/services/candle_reconciliation_service.py`
- [X] T022 [P] Add Prometheus metrics counters and histograms in `backend/app/services/authoritative_candle_store.py`
- [X] T023 [P] Add structured JSON logging context across candle store operations
- [X] T024 Run quickstart.md validation scenarios in `specs/020-authoritative-candle-store/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories.
- **User Stories (Phase 3+)**: All depend on Foundational phase completion.
  - User Story 1 (P1) → MVP Target
  - User Story 2 (P1) → Dual-Write & Rollback
  - User Story 3 (P2) → Gap Filling & Backtesting
- **Polish (Phase 6)**: Depends on all user stories being complete.

### Parallel Opportunities

- Setup (T001) can run immediately.
- Foundational tasks T002 [P] and T003 [P] can run in parallel before T004.
- Unit tests T005 [P] and T006 [P] for US1 can run in parallel.
- Unit test T012 [P] for US2 can run in parallel.
- Unit test T016 [P] for US3 can run in parallel.
- Polish tasks T021 [P], T022 [P], and T023 [P] can run in parallel.
