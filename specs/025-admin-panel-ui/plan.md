# Implementation Plan: Sprint 4 – Admin Panel UI (Two Tabs)

**Branch**: `025-admin-panel-ui`  
**Date**: 2026-07-30  
**Spec**: [spec.md](./spec.md)  
**Status**: Implementation-ready (post-clarify)  
**Depends On**: Sprint 1–3 (AuthContext role + `/admin/users` + `/admin/features` APIs)

---

## Summary

Deliver a React **Admin Panel** at `/admin` with **Users** and **Features** tabs, protected by **real admin role** (`user.role === "admin"`). Consume Sprint 2/3 APIs only. Unify `/admin/logs` and `/admin/command` on the same role gate. Developer mode must not unlock any `/admin/*` route.

**Technical approach**: Refactor `AdminRoute` → role gate → Admin Panel shell + design-system Tabs with URL `?tab=` → Users table (search, pagination, confirm role change) → Features table (allowed_roles only, Save) → `api_admin.ts` → Vitest/RTL tests.

---

## Technical Context

**Language/Version**: TypeScript 5.x, React 18  
**Primary Dependencies**: react-router-dom 7, Vite 5, Tailwind 3, design-system in-repo, Vitest + Testing Library  
**Storage**: N/A (server source of truth); URL query for tab  
**Testing**: `vitest run` + `@testing-library/react`  
**Target Platform**: Web SPA  
**Project Type**: Web application (frontend-only this sprint)  
**Performance Goals**: Paginated users (default size 20, max 100); features full list  
**Constraints**: No backend changes; no FeatureGuard; clarifications locked below  
**Scale/Scope**: 1 panel page, 2 tabs, role guard, nav, ~8–12 FE files  

### Clarifications locked (2026-07-30)

1. **Unify admin role** on `/admin`, `/admin/logs`, `/admin/command`  
2. Features tab: **allowed_roles only**; `is_active` read-only  
3. Users: **pagination + search**; no role filter required  
4. **URL tab sync** `?tab=users|features`  
5. Developer mode: **never unlocks `/admin/*`**; hide toggle if unused  

---

## Constitution Check

| Gate | Status | Notes |
| :--- | :--- | :--- |
| Reuse auth foundations | **Pass** | `useAuth` / AuthContext |
| No unjustified subsystems | **Pass** | Panel + thin API client |
| Testable ACs | **Pass** | AC-* in spec |
| Scope bounded | **Pass** | FE only; no FeatureGuard |
| Security UX | **Pass** | Role gate; backend authoritative |

**Post-design re-check**: **Pass**

---

## Project Structure

### Documentation

```text
specs/025-admin-panel-ui/
├── plan.md
├── spec.md
├── research.md
├── data-model.md          # FE DTOs / UI state
├── quickstart.md
├── contracts/admin-panel-ui.md
├── tasks.md
└── checklists/requirements.md
```

### Source Code

```text
frontend/src/
├── api_admin.ts                         # NEW
├── types/admin.ts                       # NEW (optional if colocated in api_admin)
├── components/
│   ├── AdminRoute.tsx                   # REFACTOR: role === admin
│   └── admin/
│       ├── AdminPanelPage.tsx           # NEW
│       ├── UsersAdminTab.tsx            # NEW
│       ├── FeaturesAdminTab.tsx         # NEW
│       ├── RoleChangeModal.tsx          # NEW
│       └── ForbiddenAdmin.tsx           # NEW (or inline in AdminRoute)
├── layout/
│   ├── AppShell.tsx                     # Admin nav by role; dev toggle hide-if-unused
│   └── navConfig.tsx                    # Admin panel + admin-only eng nav
├── App.tsx                              # /admin route
└── components/__tests__/ or tests/
    ├── AdminRoute.test.tsx
    ├── AdminPanelPage.test.tsx
    ├── UsersAdminTab.test.tsx
    └── FeaturesAdminTab.test.tsx
```

**Structure Decision**: Frontend-only extension of existing SPA. No backend files.

---

## 1. Architecture Overview

```
Browser
  │  useAuth(): { user, role, isAuthenticated, isLoading }
  ▼
ProtectedRoute (must be logged in)
  ▼
AdminRoute  ── role !== "admin" ──► ForbiddenAdmin
  │ role === "admin"
  ▼
┌─────────────────────────────────────────────────────────┐
│  /admin?tab=users|features                              │
│  AdminPanelPage                                         │
│    Tabs ── Users ── UsersAdminTab                       │
│         │            GET /admin/users                   │
│         │            PATCH /admin/users/{id}/role       │
│         └── Features ── FeaturesAdminTab                │
│                      GET /admin/features                │
│                      PATCH /admin/features/{key}        │
│                           body: { allowed_roles } only  │
└─────────────────────────────────────────────────────────┘
  Same AdminRoute wraps:
    /admin/logs → SystemLogs
    /admin/command → CentralCommand
```

---

## 2. Design Decisions

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| Panel path | `/admin` | Clear deep link |
| Route guard | Refactor `AdminRoute` to `role === "admin"` | Spec + unify logs/command |
| Engineering routes | Same role gate | Clarification #1 |
| Developer mode | Never unlocks `/admin/*`; hide if unused | Clarification #5 |
| Tabs | design-system `Tabs` + `?tab=` | Clarification #4 |
| Users filters | page/size + search | Clarification #3 |
| Feature edits | `allowed_roles` only; Save per row | Clarification #2 |
| Role change | Modal confirm; no permanent optimistic UI | Safety |
| Critical features UI | Disable unchecking Admin | Reduce 400s; backend still enforces |
| API module | `api_admin.ts` | Isolate from trading `api.ts` |
| Data fetching | Local React state (+ useEffect) | No new data library |
| Error text | Parse API `detail` via existing helpers | Consistent UX |

---

## 3. Routing & Protection Strategy

| Path | Guard | Notes |
| :--- | :--- | :--- |
| `/admin` | Auth + AdminRoute | Panel shell |
| `/admin?tab=features` | same | Features tab |
| `/admin/logs` | Auth + AdminRoute | Role only (no developerMode) |
| `/admin/command` | Auth + AdminRoute | Role only |
| Trader deep link | Forbidden UI | No admin API data |
| Unauthenticated | Login redirect | Match existing ProtectedRoute |

**Nav**

- Show **Admin** → `/admin` when `role === "admin"`.  
- Show logs/command under admin-only nav (not `developerMode ? ADMIN_NAV`).  
- Trader never sees these items.

---

## 4. Implementation Phases

```
A: api_admin + types
  → B: AdminRoute + nav + developerMode cleanup
    → C: AdminPanelPage + tab URL sync
      → D: UsersAdminTab + RoleChangeModal
        → E: FeaturesAdminTab
          → F: Tests + polish
```

### Phase A — API client

- Types: `AdminUser`, `UserListResponse`, `FeaturePermission`, `FeatureListResponse`  
- Functions: list users, update role, list features, update feature  
- Credentials: same as rest of SPA (cookies/Bearer)

### Phase B — Guard & nav

- `AdminRoute`: wait `isLoading`; if !auth → login; if role !== admin → Forbidden  
- AppShell nav by role  
- Hide developerMode toggle if nothing else uses it; ensure it never gates admin routes

### Phase C — Panel shell

- Title, Tabs Users/Features  
- Read/write `searchParams` for `tab`  
- Lazy optional

### Phase D — Users

- Fetch on mount/tab focus; debounce search  
- Pagination UI  
- Role change → modal → PATCH → toast; handle 400 last-admin

### Phase E — Features

- Fetch catalog  
- Draft checkboxes; Save → PATCH `{ allowed_roles }` only  
- Critical keys: admin checkbox disabled on  
- 400 → revert draft to last server state

### Phase F — Tests & polish

- Guard matrix, users flows, features flows  
- Responsive/a11y smoke  

---

## 5. Risks & Mitigations

| ID | Risk | Mitigation |
| :--- | :--- | :--- |
| R-01 | Ops used Developer mode without real admin | Require default admin account; document |
| R-02 | Stale client role after demotion | Backend 403; show forbidden |
| R-03 | Last-admin UX confusion | Surface `detail`; no optimistic commit |
| R-04 | Scope into FeatureGuard | Explicit out of scope |
| R-05 | Engineering pages locked for non-admin staff | Intended by clarification #1 |

---

## 6. Testing Strategy

| Layer | Coverage |
| :--- | :--- |
| Unit/component | AdminRoute admin/trader/loading; modal confirm once |
| Integration (RTL + mock fetch) | Users list/change/last-admin; features save/critical 400 |
| Manual | quickstart.md |
| Regression | Trader retail nav; login/logout |

---

## 7. Definition of Done

- [ ] `/admin` panel with Users + Features tabs and URL tab sync  
- [ ] Role-based AdminRoute for panel, logs, command  
- [ ] Admin-only nav (no developerMode for `/admin/*`)  
- [ ] Users: pagination, search, confirm role change, last-admin error  
- [ ] Features: list, edit allowed_roles only, critical UI + 400 revert  
- [ ] Loading/empty/error states  
- [ ] Vitest tests for guard + primary flows  
- [ ] No backend file changes  
- [ ] Spec AC checklist markable  

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

---

## Phase 0 / Phase 1 Outputs

| Artifact | Path |
| :--- | :--- |
| Research | [research.md](./research.md) |
| Data model (FE) | [data-model.md](./data-model.md) |
| UI contracts | [contracts/admin-panel-ui.md](./contracts/admin-panel-ui.md) |
| Quickstart | [quickstart.md](./quickstart.md) |
| Tasks | [tasks.md](./tasks.md) |

---

## Next Command

`/speckit-tasks` or `/speckit-implement`
