# Tasks: Phase 1 — Remove Multi-User & Single-User Application Simplification

**Input**: Design documents from `specs/026-remove-multi-user/`  
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/, quickstart.md  

## Format: `[ID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Maps task to user story (US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Environment and project initialization

- [X] T001 Update environment configuration in `backend/app/config.py` to deprecate JWT secret requirements while preserving FYERS broker app settings
- [X] T002 Update environment template `.env.template` to remove user auth keys and keep FYERS broker variables

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database migration and static owner context foundation required before UI removal

- [X] T003 Create Alembic migration script `backend/alembic/versions/026_remove_multi_user.py` to drop FK constraints on `broker_tokens` and `paper_trading_accounts`, set `user_id = '00000000-0000-0000-0000-000000000001'`, and drop tables `user_profiles`, `otps`, `audit_logs`, `devices`, `user_sessions`, `users`
- [X] T004 Modify `backend/app/models/broker_token.py` to remove Foreign Key constraint to `users.id` and default `user_id` to static owner UUID `'00000000-0000-0000-0000-000000000001'`
- [X] T005 Modify `backend/app/models/paper_trading.py` to remove Foreign Key constraint from `PaperTradingAccount.user_id` to `users.id`
- [X] T006 Delete obsolete auth model `backend/app/models/auth.py`
- [X] T007 Delete obsolete user profile model `backend/app/models/user_profile.py`
- [X] T008 Update `backend/app/models/__init__.py` to clean up exports of removed auth and profile models
- [X] T009 Update `backend/app/core/deps.py` to remove `get_current_user`, `_extract_user_id_from_request`, and `get_current_active_user`, introducing static application owner context `SYSTEM_OWNER_ID = UUID('00000000-0000-0000-0000-000000000001')`
- [X] T010 [P] Refactor `backend/app/core/security.py` to remove JWT encoding/decoding and password hashing while retaining Fernet encryption for broker tokens

**Checkpoint**: Core data model decoupled and static owner context established.

---

## Phase 3: User Story 1 - Instant Application Launch without Authentication (Priority: P1) 🎯 MVP

**Goal**: Open application directly to Central Command dashboard without login prompts or auth guards.

**Independent Test**: Navigate to `http://localhost:5173/` in a fresh browser session; dashboard renders immediately without redirecting to `/login`.

### Implementation for User Story 1

- [X] T011 [P] [US1] Delete backend auth router `backend/app/routes/auth.py`
- [X] T012 [P] [US1] Delete backend auth service `backend/app/services/auth_service.py`
- [X] T013 [P] [US1] Delete backend user profile service `backend/app/services/user_profile_service.py`
- [X] T014 [P] [US1] Delete backend email service `backend/app/services/email_service.py`
- [X] T015 [P] [US1] Delete backend auth schemas `backend/app/schemas/auth.py`
- [X] T016 [P] [US1] Delete backend profile schemas `backend/app/schemas/user_profile.py`
- [X] T017 [US1] Update `backend/app/routes/__init__.py` to remove `auth_router` inclusion
- [X] T018 [P] [US1] Delete frontend auth page `frontend/src/pages/Login.tsx`
- [X] T019 [P] [US1] Delete frontend auth page `frontend/src/pages/Signup.tsx`
- [X] T020 [P] [US1] Delete frontend auth page `frontend/src/pages/ForgotPassword.tsx`
- [X] T021 [P] [US1] Delete frontend auth page `frontend/src/pages/ResetPassword.tsx`
- [X] T022 [P] [US1] Delete frontend settings page `frontend/src/pages/SettingsSessions.tsx`
- [X] T023 [P] [US1] Delete frontend auth component `frontend/src/components/ProtectedRoute.tsx`
- [X] T024 [P] [US1] Delete frontend auth component `frontend/src/components/AdminRoute.tsx`
- [X] T025 [P] [US1] Delete frontend auth component `frontend/src/components/AuthInput.tsx`
- [X] T026 [P] [US1] Delete frontend auth component `frontend/src/components/AuthLayout.tsx`
- [X] T027 [P] [US1] Delete frontend auth component `frontend/src/components/GoogleSignInButton.tsx`
- [X] T028 [P] [US1] Delete frontend auth component `frontend/src/components/PasswordInput.tsx`
- [X] T029 [P] [US1] Delete frontend auth component `frontend/src/components/PasswordStrength.tsx`
- [X] T030 [P] [US1] Delete frontend profile component `frontend/src/components/profile/UserProfilePage.tsx`
- [X] T031 [P] [US1] Delete frontend profile component `frontend/src/components/profile/ProfileCharts.tsx`
- [X] T032 [P] [US1] Delete frontend hook `frontend/src/hooks/useAuth.tsx`
- [X] T033 [P] [US1] Delete obsolete frontend API auth helpers `frontend/src/api_auth.ts` and `frontend/src/api_auth_login.ts`
- [X] T034 [US1] Modify `frontend/src/main.tsx` to render `<App />` directly without `AuthProvider`, `GoogleOAuthProvider`, or `ProtectedRoute`
- [X] T035 [US1] Modify `frontend/src/App.tsx` to remove `useAuth` hook, `prefetchAppData` user check, profile page routes, and auth state

**Checkpoint**: User Story 1 complete. Application launches directly into Central Command without auth screens.

---

## Phase 4: User Story 2 - Seamless Single-Owner Paper Trading & Broker Connectivity (Priority: P2)

**Goal**: Execute paper trades and manage FYERS broker API settings under static application owner context without session constraints.

**Independent Test**: Submit a paper trade order from Central Command; order completes under owner context without auth headers.

### Implementation for User Story 2

- [X] T036 [P] [US2] Modify `backend/app/routes/broker_tokens.py` to use static application owner context instead of `get_current_user`
- [X] T037 [P] [US2] Modify `backend/app/routes/paper_trading.py` to use static application owner context instead of `get_current_user_id_sync`
- [X] T038 [P] [US2] Modify `backend/app/services/broker_token_service.py` to operate on static application owner context
- [X] T039 [P] [US2] Modify `backend/app/services/paper_trading_service.py` to operate on static application owner context
- [X] T040 [US2] Update `frontend/src/api.ts` to remove auth/profile/session helpers while preserving paper trading & FYERS broker endpoints

**Checkpoint**: User Story 2 complete. Paper trading and FYERS broker connectivity operate seamlessly.

---

## Phase 5: User Story 3 - Simplified UI Shell without User Profile Overhead (Priority: P3)

**Goal**: Clean header and navigation shell of user avatars, profile menus, and logout buttons.

**Independent Test**: Inspect AppShell header; verify only health badges, theme toggles, and trading navigation tabs display.

### Implementation for User Story 3

- [X] T041 [P] [US3] Modify `frontend/src/layout/AppShell.tsx` to remove profile avatar and user dropdown menu
- [X] T042 [P] [US3] Modify `frontend/src/components/DashboardHeader.tsx` to remove profile menu and logout action
- [X] T043 [P] [US3] Modify `frontend/src/components/WatchlistTab.tsx` to remove `user.id` dependency
- [X] T044 [P] [US3] Modify `frontend/src/pages/MarketsPage.tsx` to remove user context check
- [X] T045 [P] [US3] Modify `frontend/src/pages/WatchlistPage.tsx` to remove user context check

**Checkpoint**: User Story 3 complete. UI shell simplified and refactored.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup dependencies, execute regression suite, and run quickstart validation.

- [X] T046 Remove `@react-oauth/google` dependency from `frontend/package.json`
- [X] T047 Run backend test suite `pytest backend/app/tests` to confirm zero regression on Scanner, Recommendations, AI Agents, and `MarketPermissionService`
- [X] T048 Execute full quickstart validation scenarios defined in `specs/026-remove-multi-user/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion (Phase 2).
- **User Story 2 (Phase 4)**: Depends on Foundational completion (Phase 2).
- **User Story 3 (Phase 5)**: Depends on User Story 1 completion (Phase 3).
- **Polish (Phase 6)**: Depends on completion of User Stories 1, 2, and 3.

---

## Parallel Opportunities

- **Phase 2 Foundational**: T010 can run in parallel with T004-T009.
- **Phase 3 US1**: T011-T016 (Backend files deletion) and T018-T033 (Frontend files deletion) can run in parallel across separate files.
- **Phase 4 US2**: T036, T037, T038, T039 can run in parallel across separate backend modules.
- **Phase 5 US3**: T041, T042, T043, T044, T045 can run in parallel across separate frontend components.

---

## Implementation Strategy

### MVP Scope (User Story 1)
1. Complete Phase 1 (Setup) + Phase 2 (Foundational DB & Owner Context).
2. Complete Phase 3 (User Story 1).
3. **Validate MVP**: Confirm application opens directly to Central Command (`/`) without auth prompts.
