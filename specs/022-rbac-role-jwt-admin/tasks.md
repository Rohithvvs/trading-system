# Tasks: Sprint 1 – Role Normalization + JWT + Default Admin

**Input**: Design documents from `/specs/022-rbac-role-jwt-admin/`
**Prerequisites**: [plan.md](file:///D:/Work_Space/trading-system/specs/022-rbac-role-jwt-admin/plan.md), [spec.md](file:///D:/Work_Space/trading-system/specs/022-rbac-role-jwt-admin/spec.md), [data-model.md](file:///D:/Work_Space/trading-system/specs/022-rbac-role-jwt-admin/data-model.md), [auth-api.md](file:///D:/Work_Space/trading-system/specs/022-rbac-role-jwt-admin/contracts/auth-api.md), [quickstart.md](file:///D:/Work_Space/trading-system/specs/022-rbac-role-jwt-admin/quickstart.md)

---

## Format: `[ID] [P?] [Story?] Description with file path`

- **[P]**: Parallelizable (different files, independent scope)
- **[Story]**: User story label (`[US1]`, `[US2]`, `[US3]`, `[US4]`) for traceability to spec.md
- Every task includes an explicit target file path.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Environment verification and shared role constant definitions.

- [X] T001 Initialize role constants and valid role whitelist enum in `backend/app/core/roles.py`
- [X] T002 [P] Create frontend role types and constants in `frontend/src/types/auth.ts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database migration and schema constraints. MUST be completed before user story implementation.

- [X] T003 Create Alembic database migration script to normalize legacy role values, set column default to `'trader'`, and add CHECK constraint `(role IN ('trader', 'admin'))` in `backend/alembic/versions/20260728_001_rbac_role_normalization.py`
- [X] T004 Update User SQLAlchemy model definition to include role column default `'trader'` and check constraint in `backend/app/models/auth.py`
- [X] T005 Create database migration test suite to verify case normalization and check constraint enforcement in `backend/tests/test_role_migration.py`

**Checkpoint**: Database schema & foundation complete — user story work can proceed.

---

## Phase 3: User Story 1 – Role Normalization & Privilege Escalation Prevention on Registration (Priority: P1) 🎯 MVP

**Goal**: Ensure self-service registration unconditionally assigns `role = "trader"`, ignoring and stripping any client-supplied `role` parameter.

**Independent Test**: Register a user with payload `{"role": "admin"}`; verify response and DB record hold `role: "trader"`.

- [X] T006 [P] [US1] Create registration request and response DTO schemas stripping `role` from request inputs in `backend/app/schemas/auth.py`
- [X] T007 [US1] Implement user registration logic in `backend/app/services/auth_service.py` explicitly forcing `role = "trader"`
- [X] T008 [US1] Update registration API controller route handler in `backend/app/routes/auth.py`
- [X] T009 [P] [US1] Add integration test for registration privilege escalation prevention in `backend/tests/test_auth_register.py`

**Checkpoint**: Registration security verified — new accounts are guaranteed `role = "trader"`.

---

## Phase 4: User Story 2 – JWT Access Token Claims & Auth API Updates (Priority: P1)

**Goal**: Embed `sub`, `role`, and `exp` claims in signed JWT tokens, and return `id`, `email`, `full_name`, and `role` in `/auth/login` and `GET /auth/me`.

**Independent Test**: Authenticate via login or `/auth/me`; decode token to verify `role` claim; confirm response JSON contains normalized role string.

- [X] T010 [P] [US2] Update JWT token generation service to embed `sub`, `role`, and `exp` claims in `backend/app/core/jwt.py` (and `backend/app/core/security.py`)
- [X] T011 [P] [US2] Update login and `/auth/me` response schemas in `backend/app/schemas/auth.py` to include `role`
- [X] T012 [US2] Update login service and `/auth/me` handler in `backend/app/services/auth_service.py` to populate role metadata
- [X] T013 [US2] Update API route controllers for `POST /auth/login` and `GET /auth/me` in `backend/app/routes/auth.py`
- [X] T014 [P] [US2] Add unit & integration tests for JWT role claims and auth response schemas in `backend/tests/test_auth_jwt_login.py`

**Checkpoint**: JWT claims and Auth APIs return complete role identity statelessly.

---

## Phase 5: User Story 3 – Automated Default Administrator Initialization on Application Startup (Priority: P2)

**Goal**: Automatically create default administrator `admin@example.com` (`Admin@123` / `admin`) on backend startup if 0 admins exist.

**Independent Test**: Boot backend on empty database; attempt login with default admin credentials; verify `role: "admin"` returned.

- [X] T015 [P] [US3] Create default admin bootstrapper service to check admin presence and seed account in `backend/app/services/admin_bootstrap_service.py`
- [X] T016 [US3] Attach startup event hook in application lifecycle entrypoint `backend/app/main.py`
- [X] T017 [P] [US3] Add unit and idempotency tests for default admin startup seeding in `backend/tests/test_admin_bootstrap.py`

**Checkpoint**: Application automatically seeds default admin cleanly on boot.

---

## Phase 6: User Story 4 – Client-Side Frontend Role Context & Storage Persistence (Priority: P2)

**Goal**: Store `user.role` in frontend auth context and persist state to local/session storage for role awareness.

**Independent Test**: Log in on frontend; verify `user.role` present in state store and storage; refresh page and verify state rehydrates.

- [X] T018 [P] [US4] Update frontend client storage utility to read/write `user.role` in `frontend/src/utils/storage.ts`
- [X] T019 [US4] Update frontend authentication API client service in `frontend/src/services/authService.ts` to parse role metadata
- [X] T020 [US4] Update frontend AuthContext provider state store to hold `user.role` in `frontend/src/contexts/AuthContext.tsx`
- [X] T021 [P] [US4] Add frontend unit tests for AuthContext state management and storage rehydration in `frontend/src/tests/AuthStorage.test.ts`

**Checkpoint**: Frontend is fully role-aware and rehydrates role state on boot.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Quickstart scenario validation, regression testing, and security hardening.

- [X] T022 Execute end-to-end quickstart validation scenarios defined in `specs/022-rbac-role-jwt-admin/quickstart.md`
- [X] T023 Run full regression test suite across backend and frontend services
- [X] T024 Perform security audit confirming zero role leakage or unauthorized administrative access

---

## Dependencies & Execution Order

```
[Phase 1: Setup]
       │
       ▼
[Phase 2: Foundational DB Migration]  <--- BLOCKING ALL USER STORIES
       │
       ├────────────────────────────────────────┐
       ▼                                        ▼
[Phase 3: User Story 1 (Registration)]   [Phase 4: User Story 2 (JWT & Auth APIs)]
       │                                        │
       └──────────────────┬─────────────────────┘
                          ▼
         [Phase 5: User Story 3 (Default Admin)]
                          │
                          ▼
         [Phase 6: User Story 4 (Frontend Auth)]
                          │
                          ▼
         [Phase 7: Polish & E2E Validation]
```
