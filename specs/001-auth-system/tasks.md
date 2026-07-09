---
description: "Task list for Production-Ready Unified Authentication & Authorization System"
---

# Tasks: Production-Ready Unified Authentication & Authorization System

**Input**: Design documents from `/specs/001-auth-system/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, database_design.md, contracts/api_design.md, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `backend/app/`, `frontend/src/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Add security dependencies (PyJWT, passlib, argon2-cffi) to backend/requirements.txt
- [x] T002 [P] Create initial database migration for Auth schemas in backend/app/alembic/versions/ (or trigger alembic revision if ready)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Create User, Session, Device, OTP, AuditLog models in backend/app/models/auth.py
- [x] T004 [P] Create Redis blocklist helper and rate limiter in backend/app/core/redis.py
- [x] T005 [P] Implement password hashing and JWT utility functions in backend/app/core/security.py
- [x] T005b [P] Implement secure audit logging service in backend/app/services/audit_service.py
- [x] T006 Setup FastAPI dependency `get_current_active_user` in backend/app/core/deps.py
- [x] T007 Create base schemas (User, Token, etc.) in backend/app/schemas/auth.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Secure User Registration (Priority: P1) 🎯 MVP

**Goal**: Support user registration with Email, strong Password, and a 4-digit PIN.

**Independent Test**: Register a user via the UI, ensure DB records exist, and receive OTP.

### Tests for User Story 1 (OPTIONAL) ⚠️

- [ ] T008 [P] [US1] Unit test for password validation rules in backend/tests/test_auth_service.py

### Implementation for User Story 1

- [x] T009 [P] [US1] Implement user registration logic, password validation, and audit logging in backend/app/services/auth_service.py
- [x] T010 [P] [US1] Implement OTP email generation in backend/app/services/email_service.py
- [x] T011 [US1] Create `/signup` and `/verify-email` endpoints in backend/app/routes/auth.py
- [x] T012 [P] [US1] Build `AuthLayout` and `AuthInput` components in frontend/src/components/AuthLayout.tsx and frontend/src/components/AuthInput.tsx
- [x] T013 [US1] Build Signup page with real-time validation in frontend/src/pages/Signup.tsx
- [x] T014 [US1] Implement `api.ts` axios interceptors and calls for signup in frontend/src/utils/api.ts

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Core Authentication & JWT Management (Priority: P1)

**Goal**: Login, Issue JWTs, track sessions, and handle rapid revocation via Redis blocklist.

**Independent Test**: Login, receive JWT, and verify Redis blocklist prevents access after logout.

### Implementation for User Story 2

- [x] T015 [P] [US2] Implement login verification, JWT issuance, and audit logging in backend/app/services/auth_service.py
- [x] T016 [US2] Create `/login` and `/logout` endpoints enforcing `HttpOnly` cookies in backend/app/routes/auth.py
- [x] T017 [US2] Create `/refresh` endpoint handling token rotation via `HttpOnly` cookies in backend/app/routes/auth.py
- [x] T018 [P] [US2] Build Login page matching `LOGIN_PAGE_VIEW.png` in frontend/src/pages/Login.tsx
- [x] T019 [US2] Implement global `AuthContext` to manage auth state (using HttpOnly cookie presence) in frontend/src/hooks/useAuth.tsx
- [x] T020 [US2] Create `ProtectedRoute` wrapper for React router in frontend/src/components/ProtectedRoute.tsx

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Biometric & PIN Login (Priority: P2)

**Goal**: Seamless subsequent logins using PIN or Biometrics.

**Independent Test**: Set a PIN, logout, and login using only the PIN.

### Implementation for User Story 3

- [x] T021 [P] [US3] Implement PIN setup logic and strict validation in backend/app/services/auth_service.py
- [x] T021b [P] [US3] Implement WebAuthn/Biometric registration and assertion logic in backend/app/services/auth_service.py
- [x] T022 [US3] Create `/pin/setup`, `/login/pin`, `/biometric/register`, and `/login/biometric` endpoints in backend/app/routes/auth.py
- [x] T023 [P] [US3] Build `PinPad` numeric keypad component in frontend/src/components/PinPad.tsx
- [x] T024 [US3] Build `PinSetup` screen in frontend/src/pages/PinSetup.tsx
- [x] T025 [US3] Add PIN and WebAuthn Biometric steps to the Login flow in frontend/src/pages/Login.tsx

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: User Story 4 - Active Sessions Management (Priority: P3)

**Goal**: Users can view and revoke sessions across different devices.

**Independent Test**: Login on two browsers, revoke browser A from browser B, ensure A receives a 401.

### Implementation for User Story 4

- [x] T026 [P] [US4] Implement get active sessions and revoke session logic in backend/app/services/auth_service.py
- [x] T027 [US4] Create `/sessions` and `/sessions/{session_id}/revoke` endpoints in backend/app/routes/auth.py
- [x] T028 [P] [US4] Build Session listing UI and Revoke buttons in frontend/src/pages/SettingsSessions.tsx
- [x] T029 [US4] Implement API calls for session management

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T029 Protect existing trading APIs by injecting `Depends(get_current_active_user)` in backend/app/main.py or relevant routers.
- [x] T030 Hook up the frontend generic Error toast system for `401`/`403` responses in frontend/src/utils/api.ts.
- [x] T031 Run quickstart.md validation to ensure end-to-end flows work securely.
- [x] T032 [P] Write E2E Playwright tests for Auth flows in frontend/e2e/auth.spec.ts.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - User stories can then proceed sequentially in priority order (P1 → P1 → P2 → P3) or in parallel if frontend/backend developers are separated.
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2)
- **User Story 2 (P1)**: May integrate with US1 models (Users, OTPs).
- **User Story 3 (P2)**: Extends US2 by adding a new authentication route.
- **User Story 4 (P3)**: Depends heavily on US2.

### Within Each User Story

- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- T004 and T005 (Redis and Security Utils) can be built concurrently.
- Frontend UI components (T012, T018, T023) can be built in parallel with backend endpoints.
- E2E testing (T032) can be written alongside frontend integration.

---

## Implementation Strategy

### MVP First (User Story 1 & 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL)
3. Complete Phase 3 & 4 (US1 & US2).
4. **STOP and VALIDATE**: Test basic registration and email/password login.
5. Proceed to UI Polish or PIN setup.
