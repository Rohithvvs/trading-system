# Tasks: Sprint 4 â€“ Admin Panel UI (Two Tabs)

**Input**: `/specs/025-admin-panel-ui/`  
**Prerequisites**: plan.md, spec.md (clarified), research.md, data-model.md, contracts/  
**Depends On**: Sprint 1â€“3 complete  

**Tests**: Vitest + Testing Library; write tests before/with implementation for US1â€“US3.

## Format: `[ID] [P?] [Story] Description`

### Constraints (clarifications)

1. Admin role gates `/admin`, `/admin/logs`, `/admin/command`  
2. Features: **allowed_roles only**; is_active read-only  
3. Users: pagination + **search** (no role filter required)  
4. URL `?tab=users|features` required  
5. Developer mode never unlocks `/admin/*`; hide toggle if unused  
6. No backend changes; no FeatureGuard  

---

## Phase 1: Setup

- [X] T001 Inspect `useAuth`, `AdminRoute`, `AppShell`, design-system Tabs/Modal/Toast in `frontend/src/hooks/useAuth.tsx`, `frontend/src/components/AdminRoute.tsx`, `frontend/src/layout/AppShell.tsx`, `frontend/src/design-system/`
- [X] T002 [P] Confirm API shapes against Sprint 2â€“3 contracts
- [X] T003 [P] Create scaffold `frontend/src/api_admin.ts`
- [X] T004 [P] Create folder `frontend/src/components/admin/`

---

## Phase 2: Foundational â€“ API Client

- [X] T005 Define admin user + feature DTO types in `frontend/src/api_admin.ts` or `frontend/src/types/admin.ts`
- [X] T006 Implement `listAdminUsers({ page, size, search })` â†’ `GET /admin/users` in `frontend/src/api_admin.ts`
- [X] T007 Implement `updateUserRole(userId, role)` â†’ `PATCH /admin/users/{id}/role` in `frontend/src/api_admin.ts`
- [X] T008 Implement `listAdminFeatures()` â†’ `GET /admin/features` in `frontend/src/api_admin.ts`
- [X] T009 Implement `updateFeaturePermission(featureKey, { allowed_roles })` â†’ `PATCH /admin/features/{key}` in `frontend/src/api_admin.ts`
- [X] T010 [P] Error message helper (API `detail`) in `frontend/src/api_admin.ts` reusing `frontend/src/utils/apiErrors.ts` if present

**Checkpoint**: Typed admin API client ready

---

## Phase 3: US1/US4 â€“ Role Guard + Nav ðŸŽ¯ MVP

**Independent Test**: Trader forbidden on `/admin*`; admin allowed without developerMode; developerMode does not help trader

### Tests

- [X] T011 [P] [US1] AdminRoute allows admin, blocks trader in `frontend/src/components/__tests__/AdminRoute.test.tsx`
- [X] T012 [P] [US4] Developer mode does not bypass role gate in `frontend/src/components/__tests__/AdminRoute.test.tsx`
- [X] T013 [P] [US1] Unauthenticated redirected/handled like other protected routes in `frontend/src/components/__tests__/AdminRoute.test.tsx`

### Implementation

- [X] T014 [US1] Refactor `frontend/src/components/AdminRoute.tsx` to require `useAuth().role === "admin"` (respect `isLoading`)
- [X] T015 [US1] Forbidden UI for authenticated non-admins in `frontend/src/components/AdminRoute.tsx` or `frontend/src/components/admin/ForbiddenAdmin.tsx`
- [X] T016 [US1] Ensure `/admin/logs` and `/admin/command` still wrap `AdminRoute` (now role-based) in `frontend/src/App.tsx`
- [X] T017 [US1] Admin nav: panel + logs/command visible only when `role === "admin"` in `frontend/src/layout/navConfig.tsx` and `frontend/src/layout/AppShell.tsx`
- [X] T018 [US4] Remove developerMode from `/admin/*` access; hide Developer mode toggle if unused in `frontend/src/layout/AppShell.tsx` / `frontend/src/hooks/useDeveloperMode.tsx`

**Checkpoint**: Role-based access for all admin routes

---

## Phase 4: Admin Panel Shell + Routing

- [X] T019 Implement `AdminPanelPage` title + Tabs (Users | Features) in `frontend/src/components/admin/AdminPanelPage.tsx`
- [X] T020 Register `path="/admin"` â†’ AdminPanelPage inside auth + AdminRoute in `frontend/src/App.tsx`
- [X] T021 [US1] URL tab sync `?tab=users|features` (invalid â†’ users) in `frontend/src/components/admin/AdminPanelPage.tsx`
- [X] T022 [P] [US1] Test panel renders both tabs + tab query behavior in `frontend/src/components/__tests__/AdminPanelPage.test.tsx`

**Checkpoint**: Admin sees shell with URL-backed tabs

---

## Phase 5: US2 â€“ Users Tab

**Independent Test**: Search users; promote with confirm; last-admin 400 keeps role

### Tests

- [X] T023 [P] [US2] List renders mocked users in `frontend/src/components/__tests__/UsersAdminTab.test.tsx`
- [X] T024 [P] [US2] Search triggers listAdminUsers with search param in `frontend/src/components/__tests__/UsersAdminTab.test.tsx`
- [X] T025 [P] [US2] Confirm role change PATCHes and updates UI in `frontend/src/components/__tests__/UsersAdminTab.test.tsx`
- [X] T026 [P] [US2] Last-admin 400 shows error, role unchanged in `frontend/src/components/__tests__/UsersAdminTab.test.tsx`

### Implementation

- [X] T027 [US2] Fetch + loading/error/empty in `frontend/src/components/admin/UsersAdminTab.tsx`
- [X] T028 [US2] Table columns email, name, role, active, created in `frontend/src/components/admin/UsersAdminTab.tsx`
- [X] T029 [US2] Pagination controls (page, size default 20) in `frontend/src/components/admin/UsersAdminTab.tsx`
- [X] T030 [US2] Search input bound to API `search` (optional debounce) in `frontend/src/components/admin/UsersAdminTab.tsx`
- [X] T031 [US2] `RoleChangeModal` in `frontend/src/components/admin/RoleChangeModal.tsx`
- [X] T032 [US2] Wire promote/demote + pending disable + toast in `frontend/src/components/admin/UsersAdminTab.tsx`
- [X] T033 [US2] Handle 400/401/403/5xx without permanent optimistic role in `frontend/src/components/admin/UsersAdminTab.tsx`
- [X] T034 [US2] Mount Users tab in `frontend/src/components/admin/AdminPanelPage.tsx`

**Checkpoint**: Users management usable end-to-end

---

## Phase 6: US3 â€“ Features Tab

**Independent Test**: Edit allowed_roles + save; critical 400 reverts; is_active not editable

### Tests

- [X] T035 [P] [US3] List renders mocked features in `frontend/src/components/__tests__/FeaturesAdminTab.test.tsx`
- [X] T036 [P] [US3] Save PATCHes allowed_roles only and updates UI in `frontend/src/components/__tests__/FeaturesAdminTab.test.tsx`
- [X] T037 [P] [US3] Critical 400 reverts draft roles in `frontend/src/components/__tests__/FeaturesAdminTab.test.tsx`
- [X] T038 [P] [US3] is_active has no edit control / admin checkbox locked on critical keys in `frontend/src/components/__tests__/FeaturesAdminTab.test.tsx`

### Implementation

- [X] T039 [US3] Fetch + loading/error/empty in `frontend/src/components/admin/FeaturesAdminTab.tsx`
- [X] T040 [US3] Render key, description, read-only is_active, role checkboxes in `frontend/src/components/admin/FeaturesAdminTab.tsx`
- [X] T041 [US3] Draft roles + Save per row in `frontend/src/components/admin/FeaturesAdminTab.tsx`
- [X] T042 [US3] Disable unchecking Admin for `admin_panel` / `user_management` in `frontend/src/components/admin/FeaturesAdminTab.tsx`
- [X] T043 [US3] PATCH `{ allowed_roles }` only + success toast + 400 revert in `frontend/src/components/admin/FeaturesAdminTab.tsx`
- [X] T044 [US3] Mount Features tab in `frontend/src/components/admin/AdminPanelPage.tsx`

**Checkpoint**: Feature visibility editable from UI

---

## Phase 7: Polish

- [X] T045 [P] Responsive table/card layout polish in admin tab components
- [X] T046 [P] A11y: labels for tabs, modal, disabled buttons
- [X] T047 Verify trader nav has no admin destinations; scanner still works
- [X] T048 Confirm git diff has no `backend/` changes
- [X] T049 [P] Mark verification notes in `specs/025-admin-panel-ui/spec.md` when ACs done

---

## Dependencies

```text
Setup â†’ API client â†’ Guard/Nav â†’ Panel shell â†’ (Users âˆ¥ Features) â†’ Polish
```

---

## Task Summary

| Phase | Tasks | Count |
| :--- | :--- | ---: |
| Setup | T001â€“T004 | 4 |
| API | T005â€“T010 | 6 |
| Guard/Nav | T011â€“T018 | 8 |
| Shell | T019â€“T022 | 4 |
| Users | T023â€“T034 | 12 |
| Features | T035â€“T044 | 10 |
| Polish | T045â€“T049 | 5 |
| **Total** | **T001â€“T049** | **49** |

### MVP slice

T001â€“T022 + Users read-only list (partial US2) demonstrates role gate + shell; complete US2/US3 for full DoD.
