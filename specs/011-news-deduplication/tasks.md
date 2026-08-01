# Tasks: News Deduplication & Research Workflows

**Input**: Design documents from `/specs/011-news-deduplication/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Tests are generated for each story phase to ensure independent validation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- All descriptions include exact file paths.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initial configurations and registration of new components.

- [X] T001 Verify news deduplication settings and shadow stage configuration parameters in `backend/app/config/settings.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema expansion and thread pool setup. These block all downstream user stories.

- [X] T002 Add `shadow_outputs` JSONB column to the `AnalysisHistory` model class in `backend/app/models/analysis.py`
- [X] T003 Create `ArticleDedupLog` database model mapping to the `news_deduplication_audit` table in `backend/app/models/analysis.py`
- [X] T004 Register the `ArticleDedupLog` model in `backend/app/models/__init__.py`
- [X] T005 [P] Create Alembic database migration file for adding `shadow_outputs` and creating `news_deduplication_audit` under `backend/alembic/versions/`
- [X] T006 Apply Alembic migration to local database
- [X] T007 Setup synchronous database session handling and base executor wrappers in `backend/app/services/shadow_executor.py`

**Checkpoint**: Foundation ready - user story implementation can now begin.

---

## Phase 3: User Story 1 - Pure News Deduplication Heuristic (Priority: P1) 🎯 MVP

**Goal**: Implement the pure heuristic matching and 4-hour window collapsing.

**Independent Test**: Execute the unit tests checking overlap thresholds, stop words filtering, and priority tie-breaking.

### Tests for User Story 1
- [X] T008 [P] [US1] Create unit tests for the pure deduplication heuristic in `backend/tests/unit/test_news_deduplication.py`

### Implementation for User Story 1
- [X] T009 [US1] Implement `deduplicate_articles` pure function inside `backend/app/services/news_deduplication.py`
- [X] T010 [US1] Run and verify that all unit tests pass in `backend/tests/unit/test_news_deduplication.py`

**Checkpoint**: Pure deduplication logic is fully functional and unit tested.

---

## Phase 4: User Story 2 - Shadow Mode Integration & Auditing (Priority: P1)

**Goal**: Run deduplication in shadow mode using ShadowThreadPool, writing decisions to the DB via SAVEPOINT.

**Independent Test**: Enable shadow mode and run a mock scan; verify production sentiment is unmodified while `news_deduplication_audit` and `shadow_outputs` are written.

### Tests for User Story 2
- [X] T011 [P] [US2] Create integration tests for the shadow runner, database logging, and exception isolation in `backend/tests/integration/test_news_dedup_shadow.py`

### Implementation for User Story 2
- [X] T012 [US2] Implement `execute_shadow_news_dedup` runner function using isolated DB sessions in `backend/app/services/shadow_executor.py`
- [X] T013 [US2] Inject the background shadow task submission into `NewsAnalysisAgent.run` in `backend/app/agents/news_analysis_agent.py`
- [X] T014 [US2] Run and verify that integration tests pass in `backend/tests/integration/test_news_dedup_shadow.py`

**Checkpoint**: Shadow pipeline and isolation boundaries are fully functional and integrated.

---

## Phase 5: User Story 3 - Reusable prompt templates (Priority: P2)

**Goal**: Establish the five reusable markdown prompts under `AI_PROMPTS/research/`.

**Independent Test**: Check template file presence and verify variable structure.

### Implementation for User Story 3
- [X] T015 [P] [US3] Create context injection template in `AI_PROMPTS/research/01_context_injection.md`
- [X] T016 [P] [US3] Create research generation template in `AI_PROMPTS/research/02_research_generation.md`
- [X] T017 [P] [US3] Create adversarial critique template in `AI_PROMPTS/research/03_adversarial_critique.md`
- [X] T018 [P] [US3] Create synthesis template in `AI_PROMPTS/research/04_synthesis.md`
- [X] T019 [P] [US3] Create implementation decision template in `AI_PROMPTS/research/05_implementation_brief.md`
- [X] T020 [US3] Manually review copy-pasteability and tag structures of all prompt templates in `AI_PROMPTS/research/`

**Checkpoint**: Prompt templates are complete and version-controlled.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final system checks and validation document updates.

- [X] T021 Run backend regression tests for news/shadow/orchestrator/analysis paths to verify zero variance in production recommendation scoring
- [X] T022 Execute verification scenarios and document results in `specs/011-news-deduplication/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (Phase 1)**: No dependencies - starts immediately.
- **Foundational (Phase 2)**: Depends on Phase 1. Blocks all downstream user stories.
- **User Stories (Phase 3+)**: All depend on Phase 2.
  - Phase 3 (US1) and Phase 4 (US2) can proceed in parallel once the foundation is ready.
  - Phase 5 (US3) can run in parallel since it is pure markdown files.
- **Polish (Phase 6)**: Depends on all user stories being complete.

---

## Parallel Opportunities
- Foundational schema tasks (T002, T003, T004, T005) can be developed concurrently.
- User Story 1 (T008, T009, T010) and User Story 3 prompt template tasks (T015, T016, T017, T018, T019) can run in parallel.
- Integration tests (T011) can be written while US1 (Phase 3) is being completed.

---

## Implementation Strategy

### MVP Scope (User Story 1 & 2)
1. Complete Setup and Foundational database migrations.
2. Implement pure deduplication heuristic and execute T008/T009 unit tests.
3. Integrate shadow task runner into the news agent and verify isolation boundaries (crashes are caught, production scoring has zero variance).
4. Verify the logging in `news_deduplication_audit` table.
5. Pause here to test E2E before completing the prompt templates (US3).
