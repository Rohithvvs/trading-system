# Tasks: Fyers Refresh Token Auto-Renewal

**Input**: Design documents from `/specs/001-refresh-token-auto-renewal/`

**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Add `cryptography` library to `backend/requirements.txt` (requires approval)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T002 Generate Alembic migration script for `fyers_tokens` (columns: refresh_token, refresh_token_expires_at, last_auto_renewal_at, last_auto_renewal_status) in `backend/alembic/versions/`
- [x] T002a Add data-loss warning comment to migration `downgrade()` function per Constitution DB-002
- [x] T003 Update `FyersToken` SQLAlchemy model in `backend/app/models/fyers_token.py`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Providing Refresh Credentials (Priority: P1) 🎯 MVP

**Goal**: As a user, I want to input my FYERS refresh token securely so that the system can automatically generate access tokens.

**Independent Test**: Can be fully tested by verifying the frontend accepts the token and the backend saves it properly to the database.

### Implementation for User Story 1

- [x] T004 [US1] Update `FyersTokenCreate` and `FyersTokenResponse` schemas in `backend/app/schemas/fyers_token.py`
- [x] T005 [US1] Implement `encrypt_token` and `save_tokens` in `backend/app/services/fyers_service.py` using Fernet, and update `POST /fyers/token` in `backend/app/routes/fyers.py` to call it. The route MUST NOT encrypt the token directly.
- [x] T006 [US1] Update `api.ts` `saveAccessToken` signature and payload to include `refresh_token` in `frontend/src/api.ts`
- [x] T007 [US1] Add refresh token input field to `frontend/src/components/TokenStatus.tsx`

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Automated Daily Access Token Renewal (Priority: P1)

**Goal**: As a system, I want to automatically renew the FYERS access token every morning before the market opens, so that the trading engine is ready without user intervention.

**Independent Test**: Can be tested by manually triggering the `auto_token_refresh` job and verifying the access token is successfully updated.

### Implementation for User Story 2

- [x] T008 [US2] Implement `_compute_app_id_hash` and `auto_refresh_access_token` methods in `backend/app/services/fyers_service.py` (includes decrypting the token and using `httpx.AsyncClient`)
- [x] T008a [US2] Validate FYERS_PIN is non-empty and 4 numeric digits before HTTP call
- [x] T009 [US2] Implement error handling in `auto_refresh_access_token` to pause market engine and dispatch notification on failure in `backend/app/services/fyers_service.py`
- [x] T010 [US2] Register `job_auto_token_refresh` cron job (08:30 IST) with distributed lock in `backend/app/main.py`

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Refresh Token Expiry Warning (Priority: P2)

**Goal**: As a user, I want to see a visual indicator of my refresh token's validity, so that I know exactly when I need to manually generate a new 15-day token.

**Independent Test**: Can be tested by returning mocked expiry days in the status API and verifying the frontend badges/banners render correctly.

### Implementation for User Story 3

- [x] T011 [US3] Implement `get_token_status_with_refresh_info` in `backend/app/services/fyers_service.py` to calculate remaining days and status
- [x] T012 [US3] Update `GET /fyers/token/status` endpoint in `backend/app/routes/fyers.py` to return the new status fields
- [x] T013 [US3] Update `getTokenStatus` response types in `frontend/src/api.ts`
- [x] T014 [US3] Implement visual expiry badge/banner logic (Green/Amber/Red) in `frontend/src/components/TokenStatus.tsx` based on `refresh_token_days_remaining`

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T015 Verify `window.alert` and raw `fetch` are absent from new frontend code
- [x] T016 Write unit tests for `refresh_token_days_remaining` math and `appIdHash` generation in `backend/tests/unit/`
- [x] T017 Write integration test for auto-renewal flow in `backend/tests/integration/`
- [x] T018 Write API contract tests for `/fyers/token` and `/fyers/token/status` in `backend/tests/api/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed sequentially in priority order (P1 → P2 → P3) or in parallel if developers are available.
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2)
- **User Story 2 (P1)**: Can start after Foundational (Phase 2). Relies on UI from US1 being able to seed the database, but API implementation can be done independently.
- **User Story 3 (P2)**: Can start after Foundational (Phase 2). Relies on DB data, can be independently mocked.

### Implementation Strategy

#### MVP First (User Story 1 & 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. Complete Phase 4: User Story 2
5. **STOP and VALIDATE**: Test User Story 1 and 2 to ensure tokens are securely saved and the auto-refresh job works.
6. Complete Phase 5: User Story 3
7. Complete Polish phase.
