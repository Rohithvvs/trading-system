# Tasks: Sprint 5 – Frontend Feature Guards & Integration

**Input**: Design documents from `specs/026-feature-guards/`  
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Vitest + React Testing Library tests included for context, hook, guard component, and navigation filtering.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project types initialization and scaffolding for feature permissions

- [X] T001 Inspect existing auth hook `frontend/src/hooks/useAuth.tsx` and API helpers in `frontend/src/api_admin.ts`
- [X] T002 [P] Define `FeatureKey`, `FeaturePermission`, and context types in `frontend/src/types/featurePermissions.ts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core permission catalog and fallback matrix setup that MUST be completed before UI guards can be implemented

**⚠️ CRITICAL**: Foundational tasks block user story implementation

- [X] T003 [P] Define default trader permission catalog matrix in `frontend/src/utils/featureCatalogDefaults.ts`
- [X] T004 Implement `FeaturePermissionsContext` scaffold in `frontend/src/contexts/FeaturePermissionsContext.tsx`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Core Permissions Context & Hook (Priority: P1) 🎯 MVP

**Goal**: Provide a centralized `FeaturePermissionsProvider`, `useFeaturePermissions()` hook, and `canAccess(featureKey)` helper that fetch, cache, and synchronously evaluate feature access in memory.

**Independent Test**: Mount provider, invoke `useFeaturePermissions()`, and verify `canAccess("watchlist")` returns `true` while handling trader 403 fallbacks.

### Tests for User Story 1

- [X] T005 [P] [US1] Write unit tests for `useFeaturePermissions` hook and `canAccess` in `frontend/src/hooks/__tests__/useFeaturePermissions.test.tsx`

### Implementation for User Story 1

- [X] T006 [US1] Implement permission fetching and 403 trader fallback logic in `frontend/src/contexts/FeaturePermissionsContext.tsx`
- [X] T007 [P] [US1] Implement `useFeaturePermissions` hook and export `canAccess` helper in `frontend/src/hooks/useFeaturePermissions.ts`
- [X] T008 [US1] Wrap application root with `FeaturePermissionsProvider` in `frontend/src/App.tsx`

**Checkpoint**: User Story 1 fully functional and testable independently. `useFeaturePermissions` provides cached permissions in memory.

---

## Phase 4: User Story 2 - Declarative FeatureGuard & AccessDenied Fallback (Priority: P1)

**Goal**: Provide a reusable `<FeatureGuard feature="...">` component for conditional rendering and a brand-consistent `<AccessDenied />` page view for unauthorized route access.

**Independent Test**: Render `<FeatureGuard feature="watchlist">` and verify children render when access is granted and fallback renders when access is denied.

### Tests for User Story 2

- [X] T009 [P] [US2] Write component tests for `<FeatureGuard>` and `<AccessDenied>` in `frontend/src/components/__tests__/FeatureGuard.test.tsx`

### Implementation for User Story 2

- [X] T010 [P] [US2] Implement `<AccessDenied />` page component in `frontend/src/components/AccessDenied.tsx`
- [X] T011 [US2] Implement declarative `<FeatureGuard>` component supporting `children`, `fallback`, and `loadingFallback` props in `frontend/src/components/FeatureGuard.tsx`

**Checkpoint**: `<FeatureGuard>` and `<AccessDenied>` components available and tested independently.

---

## Phase 5: User Story 3 - Dynamic Navigation Filtering (Priority: P2)

**Goal**: Extend navigation configuration to filter sidebar and app shell menu items based on both user role and feature permissions.

**Independent Test**: Verify restricted menu items (`/performance`, `/admin/logs`) are automatically hidden from sidebar navigation when the user lacks feature permissions.

### Tests for User Story 3

- [X] T012 [P] [US3] Write integration tests for navigation filtering in `frontend/src/components/__tests__/navConfig.featureGuards.test.tsx`

### Implementation for User Story 3

- [X] T013 [US3] Extend `NavItem` schema with optional `featureKey?: string` and annotate `RETAIL_NAV` and `ADMIN_NAV` items in `frontend/src/layout/navConfig.tsx`
- [X] T014 [US3] Refactor `AppShell.tsx` navigation rendering to filter visible menu items using `canAccess(item.featureKey)` in `frontend/src/layout/AppShell.tsx`

**Checkpoint**: Navigation items dynamically adapt to user role and feature permissions.

---

## Phase 6: User Story 4 - Page Route & Component Feature Protection (Priority: P2)

**Goal**: Protect key existing pages (`/scanner`, `/performance`, `/admin/logs`, `/admin/command`) and UI controls (Watchlist widget, Data Export buttons) using feature guards.

**Independent Test**: Navigate directly to `/scanner` or `/performance` when feature is restricted and verify `<AccessDenied />` is rendered; verify export buttons are omitted for traders.

### Implementation for User Story 4

- [X] T015 [P] [US4] Protect Watchlist component/tab using `<FeatureGuard feature="watchlist">` in `frontend/src/App.tsx`
- [X] T016 [P] [US4] Wrap `/scanner` page route in `frontend/src/App.tsx` with `<FeatureGuard feature="advanced_scanner" fallback={<AccessDenied />}>`
- [X] T017 [P] [US4] Wrap `/performance` page route in `frontend/src/App.tsx` with `<FeatureGuard feature="portfolio_analytics" fallback={<AccessDenied />}>`
- [X] T018 [P] [US4] Wrap `/admin/logs` page route in `frontend/src/App.tsx` with `<FeatureGuard feature="system_logs" fallback={<AccessDenied />}>`
- [X] T019 [P] [US4] Wrap `/admin/command` page route in `frontend/src/App.tsx` with `<FeatureGuard feature="central_command" fallback={<AccessDenied />}>`
- [X] T020 [P] [US4] Protect data export controls in `frontend/src/components/CandidateTable.tsx` using `<FeatureGuard feature="export_data">`

**Checkpoint**: All 6 target feature surfaces fully protected by feature guards.

---

## Phase 7: User Story 5 - Fail-Closed Security & Network Error Handling (Priority: P3)

**Goal**: Ensure fail-closed security posture so that unresolvable network errors or API failures deny access to protected features by default.

**Independent Test**: Mock network failure on permission fetch and verify `canAccess` evaluates to `false` for non-essential features.

### Implementation for User Story 5

- [X] T021 [US5] Implement fail-closed error handling state in `frontend/src/contexts/FeaturePermissionsContext.tsx` ensuring `canAccess` returns `false` on unresolvable errors

**Checkpoint**: System fails closed securely under API failure conditions.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Verification, test execution, and documentation validation

- [X] T022 [P] Run full frontend test suite (`npm run test`) and verify 100% pass rate
- [X] T023 Run runnable verification scenarios from `quickstart.md` in `specs/026-feature-guards/quickstart.md`
- [X] T024 Validate complete feature readiness against checklist in `specs/026-feature-guards/checklists/requirements.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 completion - BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion.
- **User Story 2 (Phase 4)**: Depends on Phase 3 completion.
- **User Story 3 (Phase 5)**: Depends on Phase 3 completion (uses `useFeaturePermissions`).
- **User Story 4 (Phase 6)**: Depends on Phase 4 completion (uses `FeatureGuard` & `AccessDenied`).
- **User Story 5 (Phase 7)**: Depends on Phase 3 completion.
- **Polish (Phase 8)**: Depends on completion of all desired user stories.

---

## Implementation Strategy

### MVP First (User Stories 1 & 2)

1. Complete Phase 1 & 2 (Types & Context setup).
2. Complete Phase 3 (Core hook & `canAccess` helper).
3. Complete Phase 4 (`<FeatureGuard>` & `<AccessDenied />` components).
4. **VALIDATE MVP**: Test hook and guard components independently.

### Incremental Delivery

1. Deliver MVP (Core permissions engine + `<FeatureGuard>`).
2. Add Phase 5 (Dynamic navigation filtering).
3. Add Phase 6 (Page route & component protection across target surfaces).
4. Add Phase 7 (Fail-closed error hardening).
5. Complete Phase 8 (Full test validation & quickstart verification).
