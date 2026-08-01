# Phase 0 Research: Sprint 4 – Admin Panel UI

All Technical Context decisions resolved. Clarification session 2026-07-30 is authoritative.

---

## Research Topic 1: Client Admin Gate — Role vs Developer Mode

### Decision
Gate all `/admin/*` routes currently under `AdminRoute` (panel, logs, command) with **`user.role === "admin"`** from AuthContext. Developer mode must not unlock these routes.

### Rationale
Developer mode is a local toggle any user can enable—unsafe for privilege UX. Backend already enforces admin; client must match product intent.

### Alternatives Considered
* **Keep developerMode for logs/command**: *Rejected* (clarification #1).  
* **Admin role OR developerMode**: *Rejected* — traders could still open ops pages.

---

## Research Topic 2: Feature Edit Surface

### Decision
Features tab edits **`allowed_roles` only**. Display `is_active` read-only. PATCH body contains only `allowed_roles`.

### Rationale
Matches Feature Visibility goal; avoids accidental critical deactivate; smaller UI.

### Alternatives Considered
* Edit is_active / description: Deferred (clarification #2).

---

## Research Topic 3: Users Directory Filters

### Decision
**Pagination + search** required. Role filter not required in Sprint 4.

### Rationale
Search covers “find user by email/name”; role filter adds chrome without blocking MVP.

### Alternatives Considered
* Pagination only: Weaker admin UX.  
* Full filters: Extra scope.

---

## Research Topic 4: Tab Persistence

### Decision
**Required** URL sync: `?tab=users|features`. Invalid/missing → Users.

### Rationale
Refresh and shareable links; low cost with `useSearchParams`.

### Alternatives Considered
* Client-only state: *Rejected* (clarification #4).  
* Nested routes: Fine later; not required.

---

## Research Topic 5: Developer Mode Toggle Fate

### Decision
Never unlocks `/admin/*`. **Hide** sidebar toggle if no remaining non-route consumers; otherwise keep only for non-admin-route UI.

### Rationale
Avoids a control that looks like admin elevation.

### Alternatives Considered
* Remove entirely always: OK if unused; clarification prefers hide-if-unused.  
* Keep visible as “debug extras”: Acceptable only with clear labeling and no route power.

---

## Research Topic 6: Data Fetching Library

### Decision
Local React state + `useEffect` / event handlers. No React Query introduction this sprint.

### Rationale
Project does not standardize on RQ; two endpoints keep state simple.

### Alternatives Considered
* React Query: Better cache; scope expansion.

---

## Research Topic 7: Optimistic Updates

### Decision
No permanent optimistic role/feature commits. Pending disables controls; apply server response on success; revert on error.

### Rationale
Last-admin and critical-feature 400s must not leave wrong UI state.

---

## Research Topic 8: API Client Placement

### Decision
New module `frontend/src/api_admin.ts` (types colocated or `types/admin.ts`).

### Rationale
Keeps admin HTTP away from large trading `api.ts`; easier mocks in tests.

---

## Research Topic 9: Critical Feature UI Constraint

### Decision
For `admin_panel` and `user_management`, UI disables unchecking **Admin**. Backend still enforces 400.

### Rationale
Defense-in-depth UX; matches Sprint 3 critical set.

---

## Research Topic 10: Test Stack

### Decision
Vitest + Testing Library (already in `frontend/package.json`). Mock `fetch` / `api_admin` functions.

### Rationale
Matches existing frontend test setup.

---

## Resolved NEEDS CLARIFICATION

None remaining.
