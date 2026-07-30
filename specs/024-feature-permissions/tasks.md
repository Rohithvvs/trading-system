# Tasks: Sprint 3 â€“ Feature Permissions System

**Input**: Design documents from `/specs/024-feature-permissions/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/, quickstart.md  
**Depends On**: Sprint 1 complete (`022-rbac-role-jwt-admin`), Sprint 2 complete (`023-admin-user-apis`)

**Tests**: Included â€” feature specification requires comprehensive automated coverage (AC-*, SC-*, quickstart). Write story tests first; ensure they FAIL before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app backend**: `backend/app/`, `backend/alembic/`, `backend/tests/`
- No frontend paths (out of scope)

### Clarification constraints (must honor)

1. **Catalog only** â€” do not wire `can_access_feature` / `require_feature` onto existing product routes or `/admin/users`
2. **No** non-admin feature discovery endpoints (e.g. no `GET /me/features`)
3. **`can_access_feature` required**; `require_feature` optional / **not DoD**
4. Critical keys: **only** `admin_panel`, `user_management`
5. Canonical `allowed_roles` order: **`trader` then `admin`** when both present

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm Sprint 1/2 foundations and create empty module scaffolds

- [X] T001 Verify Sprint 2 `get_current_admin_user` exists and `/admin` router is mounted in `backend/app/core/deps.py` and `backend/app/routes/__init__.py`
- [X] T002 Verify role constants `VALID_ROLES` and `normalize_role` in `backend/app/core/roles.py`
- [X] T003 [P] Create feature permission model scaffold with module docstring in `backend/app/models/feature_permission.py`
- [X] T004 [P] Create feature permission service scaffold with module docstring in `backend/app/services/feature_permission_service.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Table, seed, shared schemas, and constants that ALL user stories depend on

**âš ï¸ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Implement `FeaturePermission` SQLAlchemy model (`id` UUID PK, unique `feature_key`, `description`, JSONB `allowed_roles`, `is_active`, `created_at`, `updated_at`) in `backend/app/models/feature_permission.py`
- [X] T006 Export/register `FeaturePermission` in `backend/app/models/__init__.py` so Base metadata includes the table
- [X] T007 Create Alembic revision that creates `feature_permissions` table and unique constraint on `feature_key`, with reverse-friendly `downgrade()` that drops the table (NFR-015), under `backend/alembic/versions/`
- [X] T008 Seed â‰¥7 default features idempotently (insert-if-not-exists by `feature_key`; FR-005 defaults; keys match FR-003 snake_case pattern) in Alembic revision under `backend/alembic/versions/`
- [X] T009 Define `CRITICAL_FEATURE_KEYS = frozenset({"admin_panel", "user_management"})` in `backend/app/services/feature_permission_service.py`
- [X] T010 [P] Implement `FeaturePermissionResponse` and `FeatureListResponse` (`items`) in `backend/app/schemas/admin.py`
- [X] T011 [P] Implement `UpdateFeaturePermissionRequest` with optional `allowed_roles` / `is_active` / `description`, `Literal["trader","admin"]` roles, and â‰¥1 field present validator in `backend/app/schemas/admin.py`
- [X] T012 [P] Add schema smoke tests for valid/invalid update payloads in `backend/tests/test_feature_permission_schemas.py`

**Checkpoint**: Foundation ready â€” model migrated, seeds present, schemas valid; user story implementation can begin

---

## Phase 3: User Story 1 â€“ Admin Lists Feature Permissions (Priority: P1) ðŸŽ¯ MVP

**Goal**: Only live administrators can list all feature permissions; seeded catalog visible with correct fields; traders and unauthenticated callers blocked

**Independent Test**: `GET /admin/features` as admin â†’ 200 with â‰¥7 items and required fields; trader â†’ 403; unauthenticated â†’ 401; demoted admin with stale JWT â†’ 403

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T013 [P] [US1] Integration tests for unauthenticated 401 and trader 403 on `GET /admin/features` in `backend/tests/test_feature_permissions_list.py`
- [X] T014 [P] [US1] Integration test for admin 200 with â‰¥7 features, required fields, and `feature_key` ascending order in `backend/tests/test_feature_permissions_list.py`
- [X] T015 [P] [US1] Integration test for seeded keys and default `allowed_roles` matching FR-005 in `backend/tests/test_feature_permissions_list.py`
- [X] T015a [P] [US1] Integration test AC-LIST-05: after non-critical feature is set `is_active=false`, `GET /admin/features` still returns that row with `is_active=false` in `backend/tests/test_feature_permissions_list.py`
- [X] T016 [P] [US1] Integration test that stale JWT after demotion returns 403 on feature admin routes in `backend/tests/test_feature_permissions_update.py`

### Implementation for User Story 1

- [X] T017 [US1] Implement `list_features` returning all rows (active and inactive) ordered by `feature_key` ASC in `backend/app/services/feature_permission_service.py`
- [X] T018 [US1] Implement `GET /features` handler depending on `get_current_admin_user` returning `FeatureListResponse` in `backend/app/routes/admin.py`
- [X] T019 [US1] Map model rows to `FeaturePermissionResponse` fields without extra secrets in `backend/app/routes/admin.py`

**Checkpoint**: MVP â€” admin can list feature catalog; non-admins blocked

---

## Phase 4: User Story 2 â€“ Admin Updates Allowed Roles (Priority: P1)

**Goal**: Admins can update non-critical feature `allowed_roles` (and optional `is_active` / `description`); validation and 404s correct; no-ops clean; canonical role order enforced

**Independent Test**: Admin sets `watchlist` to `["admin"]` then restores `["trader","admin"]`; unknown key 404; invalid role 422; empty body 422; request `["admin","trader"]` returns `["trader","admin"]`; no-op 200 without audit side effects for material-change path (audit may still be incomplete until US5)

### Tests for User Story 2

- [X] T020 [P] [US2] Integration tests for successful PATCH of non-critical `allowed_roles` in `backend/tests/test_feature_permissions_update.py`
- [X] T021 [P] [US2] Integration tests for 404 unknown key, 422 invalid roles, 422 empty body in `backend/tests/test_feature_permissions_update.py`
- [X] T022 [P] [US2] Integration tests for empty `allowed_roles` on non-critical, optional `is_active` toggle, role dedupe, and canonical order traderâ†’admin in `backend/tests/test_feature_permissions_update.py`
- [X] T023 [P] [US2] Integration tests for same-value no-op 200 and trader/unauth PATCH 403/401 in `backend/tests/test_feature_permissions_update.py`

### Implementation for User Story 2

- [X] T024 [US2] Implement load-by-`feature_key` raising not-found when missing in `backend/app/services/feature_permission_service.py`
- [X] T025 [US2] Implement role list validation (exact `trader`|`admin`) plus unique normalization with **trader then admin** order in `backend/app/services/feature_permission_service.py`
- [X] T026 [US2] Implement `update_feature_permission` apply path for `allowed_roles` / `is_active` / `description` and `updated_at` touch in `backend/app/services/feature_permission_service.py`
- [X] T027 [US2] Implement no-op early return when normalized payload matches current row in `backend/app/services/feature_permission_service.py`
- [X] T028 [US2] Implement `PATCH /features/{feature_key}` with `UpdateFeaturePermissionRequest` and `get_current_admin_user` in `backend/app/routes/admin.py`
- [X] T029 [US2] Map service errors to HTTP 404/422/403/401 per contracts in `backend/app/routes/admin.py`

**Checkpoint**: Non-critical feature updates work end-to-end (critical safety still open until US3)

---

## Phase 5: User Story 3 â€“ Critical Feature Safety (Priority: P1)

**Goal**: Cannot remove `admin` from critical features; cannot deactivate critical features; non-critical remain flexible

**Independent Test**: PATCH `admin_panel` / `user_management` to drop admin or set inactive â†’ 400 and data unchanged; empty roles on `watchlist` still 200

### Tests for User Story 3

- [X] T030 [P] [US3] Integration tests for remove-admin on `admin_panel` and `user_management` â†’ 400 in `backend/tests/test_feature_permissions_update.py`
- [X] T031 [P] [US3] Integration tests for `is_active=false` on critical features â†’ 400 in `backend/tests/test_feature_permissions_update.py`
- [X] T032 [P] [US3] Integration test that non-critical empty roles / deactivate still succeed in `backend/tests/test_feature_permissions_update.py`
- [X] T033 [P] [US3] Unit tests for critical safety helpers in `backend/tests/test_feature_permission_service.py`
- [X] T033a [P] [US3] Integration test AC-SAFE-05: critical PATCH with illegal `allowed_roles` (or `is_active=false`) plus new `description` â†’ 400 and description unchanged in `backend/tests/test_feature_permissions_update.py`

### Implementation for User Story 3

- [X] T034 [US3] Enforce critical `allowed_roles` must include `admin` before commit (reject entire update; no partial field apply) in `backend/app/services/feature_permission_service.py`
- [X] T035 [US3] Enforce critical features cannot set `is_active=false` (reject entire update; no partial field apply) in `backend/app/services/feature_permission_service.py`
- [X] T036 [US3] Return clear HTTP 400 detail messages (`Cannot remove admin from critical feature` / `Cannot deactivate critical feature`) and log warning with actor id + `feature_key` (NFR-013) from service/route mapping in `backend/app/routes/admin.py` and `backend/app/services/feature_permission_service.py`

**Checkpoint**: Critical safety invariant enforced end-to-end

---

## Phase 6: User Story 4 â€“ Access Helper (Priority: P1)

**Goal**: Reliable fail-closed `can_access_feature` service helper available for future consumers; not wired to existing routes

**Independent Test**: Unit/service matrix for allow/deny/inactive/missing; helper reflects DB updates after PATCH without process restart

### Tests for User Story 4

- [X] T037 [P] [US4] Unit/service tests for allow when role in list and active in `backend/tests/test_feature_permission_service.py`
- [X] T038 [P] [US4] Unit/service tests for deny when role missing from list, feature inactive, or feature_key unknown in `backend/tests/test_feature_permission_service.py`
- [X] T038a [P] [US4] Unit/service test AC-HELP-06: unknown/invalid role (e.g. `superuser`) â†’ false even when `allowed_roles` includes `trader` in `backend/tests/test_feature_permission_service.py`
- [X] T039 [P] [US4] Service test that helper reflects PATCH changes without restart in `backend/tests/test_feature_permission_service.py`

### Implementation for User Story 4

- [X] T040 [US4] Implement `async def can_access_feature(db, feature_key, role) -> bool` per FR-028 (strip+lower domain-only; never clamp unknown roles via `normalize_role`) in `backend/app/services/feature_permission_service.py`
- [X] T041 [US4] [P] OPTIONAL (not DoD): implement `require_feature(feature_key)` dependency factory — **SKIPPED** (not required for DoD; can add later)
- [X] T042 [US4] Document helper usage and catalog-only constraint (do not wire to product/admin-user routes) in module docstring of `backend/app/services/feature_permission_service.py`

**Checkpoint**: Helper ready for Sprint 4â€“5 consumers

---

## Phase 7: User Story 5 â€“ Audit Trail (Priority: P2)

**Goal**: Material feature permission changes write audit events; failures and no-ops do not write success feature-permission audits

**Independent Test**: Successful role change creates `admin_feature_permission_change` with actor, feature_key, previous/new roles; critical 400 and no-op do not

### Tests for User Story 5

- [X] T043 [P] [US5] Integration test for audit row on material `allowed_roles` change in `backend/tests/test_feature_permissions_update.py`
- [X] T044 [P] [US5] Integration tests that critical 400 and no-op create no success feature-permission audit in `backend/tests/test_feature_permissions_update.py`

### Implementation for User Story 5

- [X] T045 [US5] Call `AuditService.log_event` with event_type `admin_feature_permission_change` and required metadata after material commit in `backend/app/services/feature_permission_service.py`
- [X] T046 [US5] Pass request IP and user-agent from route into service for audit context in `backend/app/routes/admin.py`

**Checkpoint**: Audit accountability complete

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Regression, catalog-only verification, quickstart validation

- [X] T047 [P] Add optional comprehensive matrix suite in `backend/tests/test_sprint3_feature_permissions_comprehensive.py`
- [X] T048 Run Sprint 1 RBAC regression suite and fix any breakages from model/metadata imports under `backend/tests/`
- [X] T049 Run Sprint 2 admin user suite and confirm `GET /admin/users` still role-only (no feature-key gate) under `backend/tests/`
- [X] T050 Execute quickstart scenarios from `specs/024-feature-permissions/quickstart.md` (or automate equivalent assertions)
- [X] T051 Confirm no frontend file changes and no product-route / `/admin/users` feature wiring in git diff for this sprint
- [X] T052 [P] Update feature status notes when AC-* completed during implement/verify in `specs/024-feature-permissions/spec.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies â€” start immediately
- **Foundational (Phase 2)**: Depends on Setup â€” **BLOCKS** all user stories
- **User Stories (Phases 3â€“7)**: All depend on Foundational completion
  - Preferred sequential order: US1 â†’ US2 â†’ US3 â†’ US4 â†’ US5 (shared service/route file)
  - US4 can start once load-by-key exists (after US2 service foundation)
  - US5 hooks into US2 update path
- **Polish (Phase 8)**: Depends on desired user stories complete (recommend all US1â€“US5)

### User Story Dependencies

| Story | Priority | Depends on | Independently testable? |
| :--- | :--- | :--- | :--- |
| **US1** List features | P1 MVP | Phase 2 | Yes â€” list + authz only |
| **US2** Update roles | P1 | Phase 2 (+ benefits from US1 route file) | Yes â€” PATCH happy/error paths |
| **US3** Critical safety | P1 | US2 update path | Yes â€” 400 safety matrix |
| **US4** Access helper | P1 | Phase 2 (+ DB rows); better after US2 | Yes â€” service unit tests only |
| **US5** Audit trail | P2 | US2 material update path | Yes â€” audit presence/absence |

### Within Each User Story

1. Tests written and failing first  
2. Service logic before/with route wiring  
3. Story checkpoint before next priority  

### Parallel Opportunities

- T003 / T004 scaffolds in parallel  
- T010 / T011 / T012 schemas + schema tests in parallel after model exists  
- Within a story: all `[P]` test tasks in parallel  
- After Phase 2: US1 tests and early US4 unit scaffolding can overlap if staffing allows  
- **Caution**: US1â€“US3/US5 share `backend/app/routes/admin.py` and `feature_permission_service.py` â€” serialize writes to those files  

---

## Parallel Example: User Story 1

```text
# After Phase 2 complete, launch US1 tests together:
T013 Integration tests unauth 401 + trader 403 in backend/tests/test_feature_permissions_list.py
T014 Integration test admin 200 + order + fields in backend/tests/test_feature_permissions_list.py
T015 Integration test seeded keys/roles in backend/tests/test_feature_permissions_list.py
T016 Integration test stale JWT 403 in backend/tests/test_feature_permissions_update.py

# Then implement sequentially (same service/route files):
T017 list_features in backend/app/services/feature_permission_service.py
T018 GET /features in backend/app/routes/admin.py
T019 response mapping in backend/app/routes/admin.py
```

## Parallel Example: User Story 2

```text
# Tests in parallel:
T020 PATCH success tests in backend/tests/test_feature_permissions_update.py
T021 404/422 tests in backend/tests/test_feature_permissions_update.py
T022 empty roles / is_active / order tests in backend/tests/test_feature_permissions_update.py
T023 no-op + authz tests in backend/tests/test_feature_permissions_update.py

# Implementation sequential on service then route:
T024 â†’ T025 â†’ T026 â†’ T027 â†’ T028 â†’ T029
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup  
2. Complete Phase 2: Foundational (model + migration + seed + schemas)  
3. Complete Phase 3: User Story 1 (list features)  
4. **STOP and VALIDATE**: admin list works; non-admins blocked  
5. Demo catalog readiness for Admin UI tab later  

### Incremental Delivery

1. Setup + Foundational â†’ foundation ready  
2. US1 List â†’ MVP demo  
3. US2 Update â†’ operators can change visibility rules  
4. US3 Safety â†’ lockout prevention  
5. US4 Helper â†’ ready for future FeatureGuard  
6. US5 Audit â†’ accountability  
7. Polish â†’ regression + quickstart green  

### Parallel Team Strategy

1. Team completes Setup + Foundational together  
2. After foundation:
   - Dev A: US1 list (route + list tests)  
   - Dev B: US4 helper unit tests + implementation (service file coordination)  
   - Then serialize US2/US3/US5 on shared update path  

---

## Task Summary

| Phase | Tasks | Story | Count |
| :--- | :--- | :--- | ---: |
| Setup | T001â€“T004 | â€” | 4 |
| Foundational | T005â€“T012 | â€” | 8 |
| US1 List | T013â€“T019 (+ T015a) | US1 P1 MVP | 8 |
| US2 Update | T020â€“T029 | US2 P1 | 10 |
| US3 Safety | T030â€“T036 (+ T033a) | US3 P1 | 8 |
| US4 Helper | T037â€“T042 (+ T038a) | US4 P1 | 7 (1 optional) |
| US5 Audit | T043â€“T046 | US5 P2 | 4 |
| Polish | T047â€“T052 | â€” | 6 |
| **Total** | **T001â€“T052 + T015a/T033a/T038a** | | **55** |

**Required for DoD**: T001â€“T040, T042â€“T052, T015a, T033a, T038a (T041 optional; T047 optional suite)

---

## Notes

- [P] tasks = different files, no incomplete dependencies  
- [USn] label maps task to user story for traceability  
- Each user story is independently completable and testable at its checkpoint  
- Verify tests fail before implementing  
- Commit after each task or logical group  
- Stop at any checkpoint to validate the story independently  
- Avoid wiring feature checks onto trading/scanner or Sprint 2 user APIs  
- Avoid inventing non-admin discovery endpoints  
