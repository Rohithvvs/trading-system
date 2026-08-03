# Tasks: RE-001 Trend Continuation Recommendation Engine Integration

**Input**: Design documents from `/specs/029-re001-trend-continuation/`  
**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included for production-safety gates (SC-001, FR-012, FR-025, shortlist-only). Spec independent tests and quickstart scenarios require verifiable checks; keep tests additive and non-destructive to existing suites.

**Organization**: Tasks grouped by user story for independent implementation and validation.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: User story label (`[US1]`…`[US5]`) — required only in story phases
- Every task includes an exact repository file path

## Path Conventions

- Backend: `backend/app/`
- Backend tests: `backend/tests/` or `backend/app/tests/`
- Frontend: `frontend/src/`
- Migrations: `backend/alembic/versions/`
- Feature docs: `specs/029-re001-trend-continuation/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold RE-001 package and document wiring points without enabling runtime behavior.

- [x] T001 Create RE-001 service package skeleton (`__init__.py` modules) under `backend/app/services/re001/`
- [x] T002 [P] Add RE-001 package README notes (scope, non-goals, production isolation) in `backend/app/services/re001/README.md`
- [x] T003 [P] Record regime-mapping table (platform labels → Bull/Sideways/Bear/UNKNOWN) in `backend/app/services/re001/regime_mapping.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configuration, schemas, model, migration, and registry required before any user story can run end-to-end.

**⚠️ CRITICAL**: No user-story phase starts until this phase is complete.

- [x] T004 Add RE-001 settings fields (`re001_enabled`, `re001_stage` enum `OFF|LAB_SHADOW|PAPER_LINKED`, `re001_version`, `re001_persist_decisions`, `re001_compare_with_production`, `re001_timeout_ms`, `re001_ui_enabled`) with defaults OFF in `backend/app/config/settings.py`
- [x] T005 [P] Define Recommendation Decision Object + Lab DTOs including optional `trade_guidance` (Pydantic) in `backend/app/schemas/re001.py`
- [x] T006 [P] Export new RE-001 schemas from `backend/app/schemas/__init__.py`
- [x] T007 Implement `RecommendationEngineDecision` ORM model for first-class decisions table in `backend/app/models/recommendation_engine.py`
- [x] T008 Register model exports in `backend/app/models/__init__.py`
- [x] T009 Create additive Alembic migration for `recommendation_engine_decisions` (+ indexes per data-model) in `backend/alembic/versions/`
- [x] T010 Implement engine registry helper (RE-001 identity, stage, enabled resolution from settings) in `backend/app/services/re001/registry.py`
- [x] T011 [P] Add feature permission key exactly `recommendation_lab` for Admin+Trader in feature-permission seed/bootstrap path under `backend/app/services/feature_permission_service.py` and admin bootstrap if applicable
- [x] T012 [P] Add default catalog entry for feature key `recommendation_lab` in `frontend/src/utils/featureCatalogDefaults.ts`
- [x] T013 Implement Decision Object completeness validator (FR-004/FR-025/FR-026 rules) in `backend/app/services/re001/decision_validator.py`
- [x] T013a Document `scan_run_id` mapping to existing latest-scan / scan snapshot identity in `backend/app/services/re001/scan_identity.md`
- [x] T013b [P] Define portfolio/risk snapshot resolver contract (requesting user paper/risk; unavailable → `portfolio_context_unavailable`) in `backend/app/services/re001/portfolio_context.py`

**Checkpoint**: App boots with migration applied, flags OFF, no RE-001 runtime side effects.

---

## Phase 3: User Story 1 — Lab Engine Without Touching Production (Priority: P1) 🎯 MVP

**Goal**: RE-001 evaluates shortlist/full-analysis symbols after production recommendation, persists Decision Objects, fails open, never changes production shortlist/labels.

**US1 engine scope (vs US4)**: Deliver complete Decision Objects with primary/supporting/validation and fail-closed rules (missing regime, portfolio unavailable). Baseline regime bucket is applied, but full Doc 02 priority tables / bear-only RS leaders refinements are **US4**.

**Independent Test**: Run analysis/scan with RE-001 OFF vs `LAB_SHADOW`; production BUY/WATCH/REJECT and shortlist membership identical; RE-001 rows exist for shortlisted symbols (or REJECT for missing context); RE-001 exception does not fail production path.

### Tests for User Story 1

- [x] T014 [P] [US1] Unit tests for missing market context → REJECT + `missing_market_context` in `backend/tests/unit/test_re001_missing_regime.py`
- [x] T015 [P] [US1] Unit tests for Decision Object validator and state constraints in `backend/tests/unit/test_re001_decision_validator.py`
- [x] T016 [P] [US1] Unit tests for shortlist-only evaluation filter in `backend/tests/unit/test_re001_evaluation_set.py`
- [x] T017 [US1] Integration/regression: production invariance with RE-001 on/off in `backend/tests/regression/test_re001_production_invariance.py`
- [x] T018 [US1] Integration: RE-001 timeout/exception fail-open preserves production result in `backend/tests/integration/test_re001_isolation.py`
- [x] T018a [P] [US1] Unit tests: portfolio snapshot unavailable → no BUY + `portfolio_context_unavailable` in `backend/tests/unit/test_re001_portfolio_context.py`
- [x] T018b [P] [US1] Unit tests: RecommendationState set only by deterministic engine path (LLM cannot override) in `backend/tests/unit/test_re001_determinism.py`

### Implementation for User Story 1

- [x] T019 [P] [US1] Implement LabExecutionContext builder (immutable snapshot of shared inputs + production recommendation + production trade_plans + scan_run_id) in `backend/app/services/re001/context.py`
- [x] T020 [P] [US1] Implement regime mapper (platform → Bull/Sideways/Bear/UNKNOWN; unusable → fail closed) in `backend/app/services/re001/regime.py`
- [x] T021 [US1] Implement Bull Stock Filter eligibility using existing TA/MA/RS inputs (no new market-data client) in `backend/app/services/re001/eligibility.py`
- [x] T022 [US1] Implement primary strategy orchestration (Trend/Pullback/Breakout/Momentum) + supporting strategies + validation layer (baseline; Doc 02 priority polish in US4) in `backend/app/services/re001/engine.py`
- [x] T022a [US1] Wire portfolio/risk snapshot via `portfolio_context.py` into validation (fail-closed BUY when unavailable) in `backend/app/services/re001/engine.py`
- [x] T023 [US1] Implement Decision Object builder (REDS fields + strategy trace + reason_codes + optional trade_guidance from reused plan helpers/production snapshot) in `backend/app/services/re001/decision_builder.py`
- [x] T024 [US1] Implement decision persistence service (write/query first-class table, comparison metadata, scan_run_id) in `backend/app/services/re001/persistence.py`
- [x] T025 [US1] Implement isolated RE-001 runner (`re001_enabled` + stage ∈ {LAB_SHADOW,PAPER_LINKED}, timeout, fail-open logging) in `backend/app/services/re001/runner.py`
- [x] T026 [US1] Wire runner after production recommendation in `backend/app/agents/orchestrator_agent.py` (`_analyze_symbol_post_bulk` shortlist analysis path only)
- [x] T027 [US1] Ensure evaluation set is restricted to production shortlist/full-analysis symbols (no matched-only symbols) in orchestrator hook path in `backend/app/agents/orchestrator_agent.py`
- [x] T028 [US1] Add structured logs for RE-001 start/complete/error/timeout under logger `app.re001` via `backend/app/services/re001/runner.py`
- [x] T029 [US1] Confirm production `RecommendationService` / shortlist builders remain untouched for labels in `backend/app/services/recommendation_service.py` (no production authority changes; code review guardrails only)
- [x] T029a [US1] Verify scheduler/daily-scan entrypoint that already calls analysis pipeline still invokes RE-001 when enabled (integration assertion or documented hook coverage) in `backend/tests/integration/test_re001_scheduler_path.py`

**Checkpoint**: US1 MVP — RE-001 lab decisions persist; production invariance holds; flags OFF produces zero new decisions.

---

## Phase 4: User Story 2 — Side-by-Side Operator Review (Priority: P1)

**Goal**: Operators (Admin + Trader with lab permission) review RE-001 vs production on symbol detail and compact Lab comparison view.

**Independent Test**: After a lab run, open symbol detail and Lab comparison; see states, strategy, evidence, and production comparison without DB access; permission-denied without feature key.

### Tests for User Story 2

- [x] T030 [P] [US2] API tests for lab decision list/detail + permission enforcement in `backend/tests/integration/test_re001_lab_api.py`
- [x] T031 [P] [US2] Frontend unit/component tests for RE-001 detail section empty/permission/data states in `frontend/src/components/__tests__/Re001DetailSection.test.tsx`

### Implementation for User Story 2

- [x] T032 [P] [US2] Implement lab query service (by scan_run_id / symbol / recommendation_id) in `backend/app/services/re001/lab_query.py`
- [x] T033 [US2] Add lab read routes (scan comparison list + symbol decision detail) guarded by `require_feature("recommendation_lab")` in `backend/app/routes/re001_lab.py`
- [x] T034 [US2] Register router in `backend/app/routes/__init__.py`
- [x] T035 [P] [US2] Optional non-breaking enrichment of analysis item payloads with `lab_engines.RE-001` summary in `backend/app/schemas/analysis.py` and orchestrator/response assembly path (only optional fields)
- [x] T036 [P] [US2] Add frontend API helpers for lab list/detail in `frontend/src/api.ts`
- [x] T037 [US2] Implement RE-001 section component (state, strategy, evidence, validation reasons, vs production, Lab label) in `frontend/src/components/Re001DetailSection.tsx`
- [x] T038 [US2] Embed RE-001 section into symbol/analysis detail in `frontend/src/components/StockDetailPanel.tsx`
- [x] T039 [US2] Implement compact Lab comparison view (scan-level production vs RE-001 table + mismatch + link to detail) in `frontend/src/pages/RecommendationLabPage.tsx`
- [x] T040 [US2] Add feature-gated nav entry for compact Lab view using feature key `recommendation_lab` in `frontend/src/layout/navConfig.tsx`
- [x] T041 [US2] Wire Lab route into app router in `frontend/src/App.tsx`
- [x] T042 [US2] Gate Lab nav/page with `recommendation_lab` feature permission + `re001_ui_enabled` behavior via `frontend/src/components/FeatureGuard.tsx`

**Checkpoint**: US2 — operators can complete side-by-side review under SC-002/SC-004; retail scanner cards remain production-sourced.

---

## Phase 5: User Story 3 — Paper Trade & Experiment Analytics (Priority: P2)

**Goal**: Paper tickets from RE-001 retain provenance; analytics can report RE-001 decision counts by state.

**Independent Test**: Prefill/create paper order from RE-001 BUY retains engine_id/version/recommendation_id; analytics window shows RE-001 BUY/WATCH/REJECT counts; production paper fills and production analytics aggregates still correct.

### Tests for User Story 3

- [ ] T043 [P] [US3] Integration test paper prefill provenance from RE-001 decision in `backend/tests/integration/test_re001_paper_provenance.py`
- [ ] T044 [P] [US3] Integration/API test RE-001 health counts without breaking production engine-health meaning in `backend/tests/integration/test_re001_analytics.py`

### Implementation for User Story 3

- [x] T045 [P] [US3] Extend paper prefill request/response schemas with optional `source_engine_id`, `source_engine_version`, `source_recommendation_id`, and optional RE-001 decision id in `backend/app/schemas/paper_trading.py`
- [x] T046 [US3] Accept RE-001 provenance and apply trade guidance rule (RE-001 complete plan else production trade_plans) in `recommendation_prefill` / order create path in `backend/app/services/paper_trading_service.py` (no fill-engine changes)
- [x] T047 [US3] Wire provenance + guidance through `POST /paper-trading/from-recommendation` handler in `backend/app/routes/paper_trading.py`
- [x] T048 [P] [US3] Extend frontend paper prefill/order types and display provenance badge in `frontend/src/types.ts` and `frontend/src/components/OrderDrawer.tsx`
- [ ] T049 [US3] Extend engine-health or add lab metrics response with optional RE-001 segment (counts by state, errors/timeouts, optional mismatch rate) in `backend/app/routes/analytics.py` and schema in `backend/app/schemas/re001.py`
- [x] T050 [US3] Query implementation for RE-001 metrics from decisions table in `backend/app/services/re001/analytics.py`
- [ ] T051 [P] [US3] Optional frontend metrics strip for RE-001 on Lab page in `frontend/src/pages/RecommendationLabPage.tsx`

**Checkpoint**: US3 — paper attribution (SC-005) and lab health metrics (FR-016) work; paper fills unchanged.

---

## Phase 6: User Story 4 — Regime-Adaptive Continuation Behavior (Priority: P2)

**Goal**: Full Doc 02 strategy activation/priority and participation differ for Bull / Sideways / Bear; exceptional RS leaders only in Bear; missing regime remains REJECT (US1). Completes refinements beyond US1 baseline engine.

**Independent Test**: Controlled fixtures for three regimes with comparable technical setup show participation/priority differences; bear BUY count ≤ 50% of bull BUY count on shared fixture set (SC-006); Sideways tightens pullback confirmations.

### Tests for User Story 4

- [x] T052 [P] [US4] Unit tests for strategy priority tables by regime in `backend/tests/unit/test_re001_strategy_priority.py`
- [x] T053 [P] [US4] Unit tests proving bull vs bear BUY count ratio ≤ 0.5 on shared fixtures in `backend/tests/unit/test_re001_regime_participation.py`

### Implementation for User Story 4

- [x] T054 [P] [US4] Externalize regime strategy priority/activation config (Bull/Sideways/Bear) in `backend/app/services/re001/strategy_config.py`
- [x] T055 [US4] Enforce Doc 02 priority behavior and Sideways stricter pullback validation inside `backend/app/services/re001/engine.py`
- [x] T056 [US4] Enforce Bear minimal participation / exceptional RS-leader path in `backend/app/services/re001/engine.py` and `backend/app/services/re001/eligibility.py`
- [x] T057 [US4] Ensure Decision Object evidence records regime bucket + activated/rejected strategies for explainability in `backend/app/services/re001/decision_builder.py`

**Checkpoint**: US4 — regime-adaptive behavior demonstrable without changing production labels.

---

## Phase 7: User Story 5 — Register, Configure, Disable Safely (Priority: P3)

**Goal**: Operators/admins can register/version RE-001 and disable it so no decisions/UI depend on RE-001.

**Independent Test**: Toggle OFF → subsequent scans create zero new RE-001 decisions; lab UI not required/empty; version stored on every decision when enabled.

### Tests for User Story 5

- [x] T058 [P] [US5] Integration test flag OFF creates zero new decisions in `backend/tests/integration/test_re001_flag_off.py`
- [x] T059 [P] [US5] Unit test registry metadata (engine_id/version/stage) in `backend/tests/unit/test_re001_registry.py`

### Implementation for User Story 5

- [x] T060 [P] [US5] Expose read-only engine registration/stage endpoint for ops in `backend/app/routes/re001_lab.py`
- [x] T061 [US5] Ensure every persisted decision stamps `engine_id` + `engine_version` from registry in `backend/app/services/re001/persistence.py`
- [x] T062 [US5] Document env aliases (`RE001_ENABLED`, `RE001_STAGE`=`OFF|LAB_SHADOW|PAPER_LINKED`, etc.) in `specs/029-re001-trend-continuation/quickstart.md` ops section
- [x] T063 [US5] Verify lab UI hides/disables cleanly when flag or feature permission off across `frontend/src/components/Re001DetailSection.tsx` and `frontend/src/pages/RecommendationLabPage.tsx`

**Checkpoint**: US5 — safe enable/disable; versioned engine identity on all decisions.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Hardening, full quickstart validation, and regression protection across stories.

- [ ] T064 [P] Add regression guard that other `shadow_outputs` features remain intact when RE-001 enabled in `backend/tests/regression/test_re001_shadow_outputs_untouched.py`
- [ ] T065 [P] Add scanner smoke/regression note or test ensuring stage-stop/shortlist ownership unchanged in `backend/tests/regression/test_re001_scanner_unchanged.py` (or extend existing scanner regression)
- [ ] T066 Run full quickstart scenarios A–H and record evidence checklist in `specs/029-re001-trend-continuation/quickstart.md` (results section)
- [ ] T067 [P] Performance sanity: confirm RE-001 not invoked for non-shortlist symbols and timeout path logged in diagnostics (extend `backend/tests/integration/test_re001_isolation.py` if needed)
- [ ] T068 Code review pass: no production shortlist writes, no TA/scanner formula edits, no paper fill changes — verify diffs against `backend/app/services/screener_service.py`, `backend/app/services/technical_analysis_service.py`, `backend/app/services/recommendation_service.py`, paper fill paths
- [ ] T069 [P] Update feature inventory/docs pointer for RE-001 lab mode in `docs/FEATURE_INVENTORY.md` or architecture note under `docs/architecture/`
- [ ] T070 Final Definition of Done review against `specs/029-re001-trend-continuation/spec.md` §14–18 and plan §17

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 Setup
    → Phase 2 Foundational (BLOCKS all stories)
        → Phase 3 US1 (MVP) ──┬→ Phase 4 US2
                              ├→ Phase 5 US3
                              ├→ Phase 6 US4 (extends engine behavior from US1)
                              └→ Phase 7 US5 (ops hardening; uses flags from Phase 2)
        → Phase 8 Polish (after desired stories)
```

### User Story Dependencies

| Story | Depends on | Notes |
| ----- | ---------- | ----- |
| **US1** | Phase 2 only | MVP; no other stories |
| **US2** | US1 (data + APIs need decisions) | UI can stub earlier but E2E needs US1 |
| **US3** | US1 | Paper provenance + analytics queries decisions |
| **US4** | US1 engine modules | Refines orchestration; can parallelize after T022 exists |
| **US5** | Phase 2 + US1 persist path | OFF/zero-artefact proof needs US1 runner |

### Within Each Story

1. Tests (where listed) → fail first where practical  
2. Core modules/services  
3. Integration hooks/routes  
4. UI (if any)  
5. Story checkpoint validation  

### Parallel Opportunities

- **Phase 1**: T002, T003 parallel with T001 after package dir exists  
- **Phase 2**: T005/T006 parallel; T011/T012 parallel; model+migration sequential (T007→T008→T009)  
- **US1**: T014–T016 parallel; T019–T020 parallel; engine stack sequential T021→T025→T026  
- **US2**: T030–T031 parallel; T032–T036 parallel after backend contracts; UI T037–T042 after APIs  
- **US3**: T043–T044 parallel; schema/frontend provenance parallel with analytics service  
- **US4**: T052–T053 parallel; config then engine refinements  
- **US5**: T058–T059 parallel  
- **Polish**: T064/T065/T069 parallel  

---

## Parallel Example: User Story 1

```text
# After Foundational complete, launch unit tests in parallel:
T014 backend/tests/unit/test_re001_missing_regime.py
T015 backend/tests/unit/test_re001_decision_validator.py
T016 backend/tests/unit/test_re001_evaluation_set.py

# Launch independent builders in parallel:
T019 backend/app/services/re001/context.py
T020 backend/app/services/re001/regime.py

# Then sequential engine → persist → orchestrator:
T021 → T022 → T023 → T024 → T025 → T026 → T027
```

---

## Parallel Example: User Story 2

```text
T032 lab_query.py
T036 frontend/src/api.ts helpers
T037 Re001DetailSection.tsx  (mock data until API ready)

# After T033/T034:
T038 StockDetailPanel.tsx
T039 RecommendationLabPage
T040 navConfig + T041 App routes
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 Setup  
2. Complete Phase 2 Foundational  
3. Complete Phase 3 US1 (engine + persist + isolation + production invariance)  
4. **STOP and VALIDATE** quickstart scenarios A, B, C, D, H  
5. Demo lab decisions without UI if needed (DB/API inspect)

### Incremental Delivery

1. US1 → safe lab engine  
2. US2 → human review surfaces  
3. US3 → paper + analytics  
4. US4 → regime quality  
5. US5 → ops polish  
6. Phase 8 → release readiness  

### Suggested Team Split (after Foundational)

| Track | Owner focus |
| ----- | ----------- |
| A | US1 engine + orchestrator + tests |
| B | US2 lab API + frontend (after US1 persist or with mocks) |
| C | US3 paper provenance + analytics |

---

## Independent Test Criteria (Summary)

| Story | Independent test |
| ----- | ---------------- |
| US1 | Production invariance on/off; decisions for shortlist only; fail-open; missing regime REJECT |
| US2 | Detail + Lab comparison visible with permission; denied without; production cards unchanged |
| US3 | Paper provenance 100% for RE-001-originated tickets; RE-001 counts queryable |
| US4 | Bull/Sideways/Bear priority/participation differences on fixtures |
| US5 | Flag OFF → zero new decisions; version stamped when on |

---

## Notes

- **Do not** change production recommendation thresholds, scanner formulas, TA calculations, paper fill engine, or scheduler job semantics.  
- **Do not** auto-promote RE-001 to production shortlist.  
- Default runtime remains **OFF**.  
- [P] = different files / no incomplete deps; re-check before parallelizing orchestrator edits.  
- Commit after each task or cohesive group.  
- Stop at any story checkpoint to validate independently.  

---

## Task Count Summary

| Phase | Tasks | IDs |
| ----- | ----- | --- |
| Phase 1 Setup | 3 | T001–T003 |
| Phase 2 Foundational | 12 | T004–T013b |
| Phase 3 US1 (P1 MVP) | 21 | T014–T029a |
| Phase 4 US2 (P1) | 13 | T030–T042 |
| Phase 5 US3 (P2) | 9 | T043–T051 |
| Phase 6 US4 (P2) | 6 | T052–T057 |
| Phase 7 US5 (P3) | 6 | T058–T063 |
| Phase 8 Polish | 7 | T064–T070 |
| **Total** | **77** | T001–T070 (+ T013a/b, T018a/b, T022a, T029a) |

| Story | Task count (approx) |
| ----- | ------------------- |
| US1 | 21 |
| US2 | 13 |
| US3 | 9 |
| US4 | 6 |
| US5 | 6 |
| Setup/Foundational/Polish | 22 |

**MVP scope**: Phase 1 + Phase 2 + Phase 3 (US1 only) → **T001–T029a**.

### Analysis remediation (applied 2026-08-03)

Resolved across spec/plan/tasks/contracts/data-model/research/quickstart:
- Stage enum `OFF|LAB_SHADOW|PAPER_LINKED`
- Feature key `recommendation_lab` only
- Paper plan: RE-001 complete guidance else production trade_plans + provenance
- Portfolio: user snapshot or fail-closed BUY + `portfolio_context_unavailable`
- `scan_run_id` → completed-scan / latest-scan identity
- SC-006 ≤50% bear/bull BUY ratio; SC-003 engineering vs soak
- US1 vs US4 engine scope boundary
- Dual path cleanup; tasks T013a/b, T018a/b, T022a, T029a added
