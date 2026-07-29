# Tasks: Sprint 2 â€“ Backend Authorization + User Management APIs

**Input**: Design documents from `/specs/023-admin-user-apis/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/, quickstart.md  
**Depends On**: Sprint 1 complete (`022-rbac-role-jwt-admin`)

**Tests**: Included â€” feature specification requires comprehensive automated coverage (AC-*, SC-*, quickstart).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app backend**: `backend/app/`, `backend/tests/`
- No frontend paths (out of scope)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm Sprint 1 foundations and create empty module scaffolds

- [X] T001 Verify Sprint 1 role constants and User eligibility fields (`role`, `is_active`, `deleted_at`) in `backend/app/core/roles.py` and `backend/app/models/auth.py`
- [X] T002 [P] Create admin service module scaffold with docstring in `backend/app/services/admin_user_service.py`
- [X] T003 [P] Create admin router scaffold with `APIRouter()` in `backend/app/routes/admin.py`
- [X] T004 [P] Create admin schemas module scaffold in `backend/app/schemas/admin.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Live-store admin gate, shared DTOs, and router registration that ALL user stories depend on

**âš ï¸ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Implement `get_current_admin_user` (authenticate → load active non-deleted user → require stored `role=admin`; else 401/403) in `backend/app/core/deps.py`
- [X] T006 Document that JWT-only `require_admin` must not be the sole gate for admin user-management routes in `backend/app/core/deps.py`
- [X] T007 [P] Implement `UserAdminResponse` and `UserListResponse` in `backend/app/schemas/admin.py`
- [X] T008 [P] Implement `UpdateRoleRequest` with `role: Literal["trader", "admin"]` in `backend/app/schemas/admin.py`
- [X] T009 Register admin router with `prefix="/admin"` and tags `["Admin"]` in `backend/app/routes/__init__.py`
- [X] T010 [P] Add unit tests for `get_current_admin_user` (admin pass, trader 403, unauth 401, inactive denied) in `backend/tests/test_admin_deps.py`
- [X] T011 [P] Add schema smoke tests for valid/invalid `UpdateRoleRequest` in `backend/tests/test_admin_schemas.py`

**Checkpoint**: Foundation ready â€” user story implementation can now begin

---

## Phase 3: User Story 1 â€“ Admin Access Control for User Directory (Priority: P1) ðŸŽ¯ MVP

**Goal**: Only live administrators can call admin user-management endpoints; traders get 403; unauthenticated get 401; stale admin JWT after demotion gets 403

**Independent Test**: Call `GET /admin/users` as admin (200), trader (403), unauthenticated (401); after demoting a second admin, their old token cannot access admin APIs (403)

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T012 [P] [US1] Integration tests for unauthenticated 401 and trader 403 on `GET /admin/users` in `backend/tests/test_admin_users_list.py`
- [X] T013 [P] [US1] Integration test for admin 200 on `GET /admin/users` in `backend/tests/test_admin_users_list.py`
- [X] T014 [P] [US1] Integration test for stale JWT after demotion returns 403 on admin routes in `backend/tests/test_admin_users_role.py`

### Implementation for User Story 1

- [X] T015 [US1] Implement minimal `list_users` returning active non-deleted users with pagination defaults (page=1, size=20, max size=100) in `backend/app/services/admin_user_service.py`
- [X] T016 [US1] Implement `GET /users` handler depending on `get_current_admin_user` returning `UserListResponse` in `backend/app/routes/admin.py`
- [X] T017 [US1] Ensure admin response items map to `UserAdminResponse` fields (id, email, full_name, role, is_active, created_at) without secrets in `backend/app/routes/admin.py`

**Checkpoint**: MVP â€” admin-only access to user directory works; non-admins blocked

---

## Phase 4: User Story 2 â€“ Browse and Filter the User Directory (Priority: P1)

**Goal**: Admins can paginate, search by email/name, and filter by role; inactive/soft-deleted users excluded

**Independent Test**: Seed mixed users; verify defaults, search, role filter, exclusion of inactive/deleted, and 422 on invalid page/size/role

### Tests for User Story 2

- [X] T018 [P] [US2] Integration tests for pagination defaults and size max 100 → 422 in `backend/tests/test_admin_users_list.py`
- [X] T019 [P] [US2] Integration tests for search (email/full_name) and role filter including invalid role → 422 in `backend/tests/test_admin_users_list.py`
- [X] T020 [P] [US2] Integration test that inactive and soft-deleted users are excluded from default list in `backend/tests/test_admin_users_list.py`

### Implementation for User Story 2

- [X] T021 [US2] Extend `list_users` with case-insensitive partial `search` on email OR full_name in `backend/app/services/admin_user_service.py`
- [X] T022 [US2] Extend `list_users` with optional `role` filter (`trader`|`admin` only) in `backend/app/services/admin_user_service.py`
- [X] T023 [US2] Wire query params `page`, `size`, `search`, `role` with FastAPI Query validation on `GET /users` in `backend/app/routes/admin.py`
- [X] T024 [US2] Apply stable ordering (`created_at` DESC) and correct `total` count under filters in `backend/app/services/admin_user_service.py`

**Checkpoint**: Full directory browsing matches contracts/admin-api.md list endpoint

---

## Phase 5: User Story 3 â€“ Promote and Demote User Roles (Priority: P1)

**Goal**: Admins can change eligible users between `trader` and `admin`; invalid/missing/inactive targets handled; same-role no-op succeeds without side effects

**Independent Test**: Promote trader→admin; demote non-last admin→trader; unknown id 404; inactive 404; invalid role 422; no-op 200; trader caller 403

### Tests for User Story 3

- [X] T025 [P] [US3] Integration tests for promote trader→admin and demote non-last admin→trader in `backend/tests/test_admin_users_role.py`
- [X] T026 [P] [US3] Integration tests for 404 missing/inactive/soft-deleted target and 422 invalid role in `backend/tests/test_admin_users_role.py`
- [X] T027 [P] [US3] Integration tests for same-role no-op 200 and trader/unauth PATCH 403/401 in `backend/tests/test_admin_users_role.py`

### Implementation for User Story 3

- [X] T028 [US3] Implement `update_user_role` load target (404 if missing/inactive/soft-deleted) in `backend/app/services/admin_user_service.py`
- [X] T029 [US3] Implement role normalize + same-role no-op early return in `backend/app/services/admin_user_service.py`
- [X] T030 [US3] Apply promote/demote persist for eligible targets (last-admin hook point left for US4) in `backend/app/services/admin_user_service.py`
- [X] T031 [US3] Implement `PATCH /users/{user_id}/role` with `UpdateRoleRequest` and `get_current_admin_user` in `backend/app/routes/admin.py`
- [X] T032 [US3] Map service HTTP errors to 404/422/403/401 per contracts in `backend/app/routes/admin.py`

**Checkpoint**: Role changes work for happy path and standard error cases (last-admin still open until US4)

---

## Phase 6: User Story 4 â€“ Last-Admin Protection (Priority: P1)

**Goal**: Cannot demote the last **active, non-deleted** admin (self or other); inactive admins do not count as surviving admins

**Independent Test**: With one active admin, demotion (self/other) → 400 and role unchanged; with two active admins, demotion succeeds; inactive admin does not unlock demotion of last active admin

### Tests for User Story 4

- [X] T033 [P] [US4] Integration tests for sole active admin demotion self and other → 400 in `backend/tests/test_admin_users_role.py`
- [X] T034 [P] [US4] Integration test for demotion allowed when two or more active admins exist in `backend/tests/test_admin_users_role.py`
- [X] T035 [P] [US4] Integration test that inactive/soft-deleted admin rows do not satisfy last-admin survival in `backend/tests/test_admin_users_role.py`
- [X] T036 [P] [US4] Unit tests for `count_active_admins` eligibility predicate in `backend/tests/test_admin_user_service.py`

### Implementation for User Story 4

- [X] T037 [US4] Implement `count_active_admins` (role=admin AND is_active AND deleted_at IS NULL) in `backend/app/services/admin_user_service.py`
- [X] T038 [US4] Enforce last-admin protection before demotion commit (self and other) raising 400 in `backend/app/services/admin_user_service.py`
- [X] T039 [US4] Re-validate active admin count at write time to reduce concurrent dual-demotion lockout risk in `backend/app/services/admin_user_service.py`
- [X] T040 [US4] Return clear detail message `Cannot demote the last active admin` from route/service in `backend/app/routes/admin.py`

**Checkpoint**: Last-admin safety invariant enforced end-to-end

---

## Phase 7: User Story 5 â€“ Audit Trail for Role Changes (Priority: P2)

**Goal**: Every real privilege change writes an audit event; failures and no-ops do not write success role-change audits

**Independent Test**: Promote/demote creates `admin_role_change` with actor, target, previous_role, new_role; last-admin failure and no-op create no such success audit

### Tests for User Story 5

- [X] T041 [P] [US5] Integration test that real role change creates audit log with actor/target/previous/new roles in `backend/tests/test_admin_users_role.py`
- [X] T042 [P] [US5] Integration tests that last-admin failure and same-role no-op do not create role-change audit in `backend/tests/test_admin_users_role.py`

### Implementation for User Story 5

- [X] T043 [US5] On previous_role â‰  new_role success path, call `AuditService.log_event` with event_type `admin_role_change` in `backend/app/services/admin_user_service.py`
- [X] T044 [US5] Include metadata `actor_user_id`, `target_user_id`, `previous_role`, `new_role`, optional `target_email` in `backend/app/services/admin_user_service.py`
- [X] T045 [US5] Pass optional `ip_address` / `user_agent` from route into service for audit context in `backend/app/routes/admin.py`

**Checkpoint**: Accountability complete for privilege mutations

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Regression, security review, and quickstart validation across all stories

- [X] T046 [P] Add comprehensive AC matrix suite mapping AC-AUTH/LIST/ROLE/LAST/AUD ids in `backend/tests/test_sprint2_admin_comprehensive.py`
- [X] T047 Run Sprint 1 auth regression suites (`backend/tests/test_sprint1_rbac_comprehensive.py`, register/jwt/bootstrap tests) and fix any breakages
- [X] T048 Execute validation scenarios from `specs/023-admin-user-apis/quickstart.md`
- [X] T049 Confirm git diff contains no frontend changes for this feature (backend-only scope)
- [X] T050 Security pass: verify 401/403/404/400/422 mapping and no `password_hash` leakage in admin responses via tests in `backend/tests/test_admin_users_list.py` and `backend/tests/test_admin_users_role.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies â€” start immediately
- **Foundational (Phase 2)**: Depends on Setup â€” **BLOCKS** all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational â€” **MVP**
- **User Story 2 (Phase 4)**: Depends on US1 list endpoint existing (extends `list_users` / GET)
- **User Story 3 (Phase 5)**: Depends on Foundational + admin router; can start after US1 MVP for shared auth patterns
- **User Story 4 (Phase 6)**: Depends on US3 `update_user_role` path
- **User Story 5 (Phase 7)**: Depends on US3 success path (adds audit)
- **Polish (Phase 8)**: Depends on US1â€“US5 complete

### User Story Dependencies

```
[Setup] → [Foundational: gate + schemas + router]
                â”‚
                â–¼
         [US1 Access Control + minimal list]  ðŸŽ¯ MVP
                â”‚
                â–¼
         [US2 Search / filter / pagination polish]
                â”‚
                â–¼
         [US3 Role promote / demote]
                â”‚
        â”Œâ”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”
        â–¼               â–¼
 [US4 Last-admin]  [US5 Audit]  (US5 can follow US3; US4 before production demote)
        â”‚               â”‚
        â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜
                â–¼
            [Polish]
```

- **US1**: No dependency on other stories after Foundational
- **US2**: Builds on US1 list endpoint
- **US3**: Independent of US2 filters; needs Foundational + router
- **US4**: Requires US3 demotion path
- **US5**: Requires US3 success mutation path

### Within Each User Story

- Tests (if included) written to fail before implementation
- Service before (or with) route wiring
- Story complete before next priority when sequencing solo

### Parallel Opportunities

- T002, T003, T004 in parallel after T001
- T007, T008, T010, T011 in parallel after T005/T006
- T012â€“T014 tests in parallel before US1 implementation
- T018â€“T020 in parallel for US2 tests
- T025â€“T027 in parallel for US3 tests
- T033â€“T036 in parallel for US4 tests
- T041â€“T042 in parallel for US5 tests
- After Foundational, US2 work can proceed while US3 tests are drafted on separate files

---

## Parallel Example: User Story 1

```text
# Launch US1 tests together:
Task: T012 Integration tests for unauthenticated 401 and trader 403 on GET /admin/users in backend/tests/test_admin_users_list.py
Task: T013 Integration test for admin 200 on GET /admin/users in backend/tests/test_admin_users_list.py
Task: T014 Integration test for stale JWT after demotion returns 403 in backend/tests/test_admin_users_role.py

# Then implement:
Task: T015 Minimal list_users in backend/app/services/admin_user_service.py
Task: T016 GET /users handler in backend/app/routes/admin.py
```

---

## Parallel Example: User Story 3

```text
# Launch US3 tests together:
Task: T025 Promote/demote success tests in backend/tests/test_admin_users_role.py
Task: T026 404/422 tests in backend/tests/test_admin_users_role.py
Task: T027 No-op and authz tests in backend/tests/test_admin_users_role.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup  
2. Complete Phase 2: Foundational (CRITICAL)  
3. Complete Phase 3: User Story 1  
4. **STOP and VALIDATE**: Admin can list; trader/anon blocked  
5. Demo/secure baseline before filters and mutations  

### Incremental Delivery

1. Setup + Foundational → gates and DTOs ready  
2. US1 → Admin-only directory (MVP)  
3. US2 → Search/filter/pagination complete  
4. US3 → Role changes  
5. US4 → Last-admin safety  
6. US5 → Audit trail  
7. Polish → Regression + quickstart  

### Suggested MVP Scope

**US1 only** (T001â€“T017): production-ready admin gate + minimal `GET /admin/users`.  
Do not ship demotion (US3â€“US4) without last-admin protection.

### Parallel Team Strategy

1. Team completes Setup + Foundational together  
2. Dev A: US1 → US2 (list path)  
3. Dev B: US3 tests + service draft (after Foundational), then US4/US5  
4. Integrate on shared `admin_user_service.py` / `routes/admin.py` carefully (avoid dual edits)

---

## Notes

- [P] tasks = different files, no incomplete-task dependencies  
- [USn] label maps to spec user stories for traceability  
- Reuse Sprint 1: `UserRole`, `normalize_role`, `get_current_active_user`, `AuditService`  
- Do **not** modify frontend or trading/scanner/paper-trading modules  
- Contract source of truth: `specs/023-admin-user-apis/contracts/admin-api.md`  
- Commit after each task or logical group  
- Stop at any checkpoint to validate the story independently  
