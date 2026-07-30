# Feature Specification: Sprint 4 – Admin Panel UI (Two Tabs)

**Feature Directory**: `specs/025-admin-panel-ui`  
**Feature Branch**: `025-admin-panel-ui`  
**Created**: 2026-07-30  
**Status**: Implemented (Sprint 4 Admin Panel UI complete)  
**Target Sprint**: Sprint 4 (Admin Panel Frontend)  
**Depends On**:
- Sprint 1 – RBAC + JWT + Default Admin (`specs/022-rbac-role-jwt-admin`)
- Sprint 2 – Admin User Management APIs (`specs/023-admin-user-apis`)
- Sprint 3 – Feature Permissions System (`specs/024-feature-permissions`)

---

## Clarifications

### Session 2026-07-30

- Q: When AdminRoute becomes role-based, what about `/admin/logs` and `/admin/command`? → A: **Unify on admin role** — Admin Panel + logs + command all require `role === "admin"`; Developer mode no longer unlocks these routes
- Q: On Features tab, which fields may an admin edit? → A: **Roles only** — edit/save `allowed_roles`; show `is_active` read-only
- Q: On Users tab, which list filters are required? → A: **Pagination + search** — search maps to API `search`; role filter not required
- Q: Should the active Admin Panel tab be reflected in the URL? → A: **URL sync required** — query `?tab=users|features`; invalid values fall back to Users
- Q: What should happen to the sidebar Developer mode toggle? → A: **Keep only if still needed for non-admin-route UI** — never unlocks `/admin/*`; hide if unused

---

## 1. Overview

Sprint 4 delivers a **production-ready Admin Panel** in the React frontend. Only authenticated users with **role `admin`** may open it. The panel has **exactly two tabs**:

1. **Users** — list users and change roles via Sprint 2 APIs.  
2. **Features** — manage feature visibility (`allowed_roles`) via Sprint 3 APIs.

Client-side access currently relies on a **Developer mode** toggle (`useDeveloperMode` / `AdminRoute`). This sprint replaces that gate for administrative access with **real role checks** (`user.role === "admin"`), while keeping the panel simple, consistent with the existing design system, and free of backend changes.

---

## 2. Background / Context

| Sprint | Capability | Status |
| :--- | :--- | :--- |
| Sprint 1 | Roles `trader` \| `admin`; JWT + AuthContext `user.role` | Done |
| Sprint 2 | `GET /admin/users`, `PATCH /admin/users/{id}/role`, last-admin protection | Done |
| Sprint 3 | `GET /admin/features`, `PATCH /admin/features/{feature_key}` | Done |
| Sprint 4 | Admin Panel UI (Users + Features tabs) | **This sprint** |
| Sprint 5 | Frontend FeatureGuard for product surfaces | Deferred |

**Gap this sprint closes**: Operators must use APIs or DB tools to manage roles and feature visibility. Engineering pages are gated by a local “Developer mode” toggle, not by real admin role—traders can enable it; demoted admins may still appear to have “dev” access until reloaded.

---

## 3. Business Objective

1. **Operational self-service** — admins manage users and feature visibility from the product UI.  
2. **Real authorization UX** — only role `admin` sees Admin entry points and can open admin routes.  
3. **Safe privilege changes** — last-admin and critical-feature backend errors are shown clearly; no silent failures.  
4. **Foundation for Sprint 5** — stable admin UI without yet enforcing FeatureGuard on retail pages.

---

## 4. Scope

### In Scope

- Role-based **Admin route guard** (`user.role === "admin"`) for the Admin Panel **and** existing engineering routes currently wrapped by `AdminRoute` (`/admin/logs`, `/admin/command`).
- **Admin Panel** page with layout and **two tabs only**: Users | Features.
- **Users tab**:
  - Load paginated user directory from `GET /admin/users`.
  - **Required** search control mapped to API `search` (email/name); role filter not required this sprint.
  - Change role between `trader` and `admin` via `PATCH /admin/users/{id}/role`.
  - Confirmation before role change.
  - Success and error feedback (including last-admin **400** messages).
- **Features tab**:
  - Load catalog from `GET /admin/features`.
  - Edit **only** `allowed_roles` for each feature (checkboxes for `trader` and `admin`); `is_active` is display-only.
  - Save via `PATCH /admin/features/{feature_key}` with `allowed_roles` only (not `is_active` / `description`).
  - Surface critical-feature **400** errors without corrupting UI state.
- Navigation: show **Admin** entry only to admins.
- Loading, empty, and error states; responsive layout; design-system consistency.
- Frontend automated tests for guard, tab rendering, and key user flows (mock API).

### Out of Scope (Explicitly Deferred)

- Backend API changes (contracts fixed in Sprint 2–3).
- Frontend **FeatureGuard** on scanner/watchlist/etc. (Sprint 5).
- Creating/deleting users or feature keys from UI.
- Bulk role changes; CSV export; audit log browser.
- Changes to trading, scanner, paper-trading business logic.
- Complex permission hierarchies or multi-tenant admin.
- Retaining Developer mode as a route unlock for `/admin/*` engineering pages (clarified: those routes use admin role only).
- Building new engineering features inside Central Command / System Logs (only access-gate alignment).

### Assumptions

- AuthContext already exposes authenticated `user` with `role: "trader" | "admin"`.
- Admin APIs require live backend admin; UI must handle **401/403** (session expired / not admin).
- Client role check is UX protection only; backend remains authoritative.
- Existing design system components (Button, Card, Tabs, Modal, Toast, EmptyState, Badge) are preferred over new visual systems.

---

## 5. Functional Requirements

### Access Control & Routing

- **FR-001**: Unauthenticated users MUST NOT access the Admin Panel; they MUST be sent to the login flow (same pattern as other protected routes).
- **FR-002**: Authenticated users with `role !== "admin"` MUST NOT access the Admin Panel. The product MUST show a clear **forbidden** experience (dedicated message and navigation away) and MUST NOT render admin data.
- **FR-003**: Authenticated users with `role === "admin"` MUST be able to open the Admin Panel route.
- **FR-004**: Client-side protection for the Admin Panel and for routes using the shared admin guard MUST use **AuthContext role** (`user.role === "admin"`), **not** Developer mode / localStorage flags.
- **FR-005**: `AdminRoute` (or successor) MUST be role-based. It MUST gate at least: Admin Panel (`/admin`), System Logs (`/admin/logs`), and Central Command (`/admin/command`). Developer mode MUST NOT unlock these routes.
- **FR-006**: Primary navigation MUST show an **Admin** (or equivalent) item **only** when `user.role === "admin"`. Traders MUST NOT see the Admin Panel nav entry. Engineering destinations under the former Developer nav (logs/command) MUST also appear only for admins (not via Developer mode alone).
- **FR-007**: Deep-linking to `/admin`, `/admin/logs`, or `/admin/command` as a trader MUST show forbidden UX and MUST NOT leak admin/ops data.
- **FR-039**: Developer mode MAY remain as a non-route UI preference **only if** it still controls non-`/admin/*` UI behavior. It MUST NOT unlock any `/admin/*` route (FR-005). If nothing non-route remains dependent on it, the sidebar toggle MUST be **hidden** (or removed from retail chrome) so it cannot be mistaken for admin access.

### Admin Panel Shell

- **FR-008**: The Admin Panel MUST provide a dedicated page shell (title, short description, content area) consistent with app layout (`AppShell` / page-container patterns).
- **FR-009**: The panel MUST contain **exactly two** top-level tabs: **Users** and **Features**.
- **FR-010**: Active tab MUST be visible and switchable without full page reload.
- **FR-011**: Active tab MUST be reflected in the URL as query param `tab=users` or `tab=features`. Changing tabs MUST update the URL (replace or push). On load, invalid/missing `tab` MUST default to **Users** (`tab=users` or omit treated as users).

### Users Tab

- **FR-012**: On open (or tab focus), the UI MUST load users from `GET /admin/users` with authentication credentials (Bearer / cookie as existing client does).
- **FR-013**: Default list request MUST use sensible pagination (at least page 1, size within API max 100; recommended default size **20**).
- **FR-014**: Each row MUST display at least: email, full name, role, active flag, created date (as returned by API).
- **FR-015**: Admin MUST be able to change a user’s role between `trader` and `admin` only.
- **FR-016**: Role change MUST require an explicit **confirmation** step (modal or equivalent) naming the target user and new role.
- **FR-017**: On confirm, UI MUST call `PATCH /admin/users/{user_id}/role` with body `{ "role": "trader" | "admin" }`.
- **FR-018**: On **200**, UI MUST update the row (or refresh list) and show success feedback.
- **FR-019**: On **400** (last-admin protection), UI MUST show the backend message (or equivalent clear text) and MUST NOT change the displayed role.
- **FR-020**: On **403/401**, UI MUST show unauthorized/session feedback and MUST NOT apply optimistic role change permanently.
- **FR-021**: On network/5xx errors, UI MUST show a recoverable error and leave prior role displayed.
- **FR-022**: Users tab MUST provide a **search** control that maps to the API `search` query (partial email/name). Empty search means no search filter. A **role filter** is **not required** this sprint (MAY be omitted).
- **FR-023**: Loading state MUST be shown while the list is fetching; empty state when total is zero (including “no matches” for search).

### Features Tab

- **FR-024**: On open (or tab focus), the UI MUST load features from `GET /admin/features`.
- **FR-025**: Each feature row MUST show at least: `feature_key`, description, `allowed_roles`, `is_active`.
- **FR-026**: Admin MUST be able to edit allowed roles using clear controls for **trader** and **admin** (checkboxes, multi-select, or equivalent).
- **FR-027**: Saving a feature MUST call `PATCH /admin/features/{feature_key}` with body containing **`allowed_roles` only** (MUST NOT send `is_active` or `description` from this UI in Sprint 4).
- **FR-028**: On **200**, UI MUST reflect returned `allowed_roles` (canonical order from API) and show success feedback.
- **FR-029**: On **400** (critical feature safety), UI MUST show the error and revert controls to last known good server state.
- **FR-030**: On **404/422/401/403**, UI MUST show appropriate error feedback without silent failure.
- **FR-031**: Critical features (`admin_panel`, `user_management`) MUST prevent unchecking **admin** in the UI (disable that control); backend remains source of truth if bypassed.
- **FR-032**: Loading and empty states MUST be provided for the features list.
- **FR-040**: Features tab MUST display `is_active` as **read-only** status (no toggle control this sprint).

### Feedback & UX

- **FR-033**: Success and error feedback MUST use the existing design-system patterns (e.g. Toast and/or inline alerts).
- **FR-034**: Destructive or privilege-changing actions (role demotion/promotion) MUST not be single-click without confirmation.
- **FR-035**: Concurrent edits: last server response wins for that row; no requirement for multi-admin realtime sync.

### Non-Regression

- **FR-036**: Retail navigation and trader workflows (scanner, markets, paper, profile) MUST remain available to traders without Admin Panel entry.
- **FR-037**: Sprint 1 auth flows and role persistence in AuthContext MUST continue to work.
- **FR-038**: No backend contract changes are required for this sprint.

---

## 6. Non-Functional Requirements

### Security

- **NFR-001**: UI admin checks are **defense-in-depth only**; all mutations rely on backend admin authorization.
- **NFR-002**: Admin API responses (emails, roles) MUST only be requested after role-gate passes (avoid unnecessary PII fetch for traders).
- **NFR-003**: Tokens MUST not be logged to console in production builds.

### Usability

- **NFR-004**: Primary admin tasks (find user → change role; find feature → update roles) MUST be completable without documentation.
- **NFR-005**: Touch targets and layout MUST work on desktop and usable tablet widths; mobile may stack tables.
- **NFR-006**: Loading indicators MUST appear within a short perceived delay for network waits (skeleton or spinner).

### Reliability

- **NFR-007**: Failed mutations MUST leave UI consistent with last successful server state (no stuck optimistic roles).
- **NFR-008**: Tab switch during load MUST not crash; in-flight requests MAY be ignored if tab unmounted (no state update on unmounted component).

### Performance

- **NFR-009**: User list pagination MUST bound payload (max 100 per API).
- **NFR-010**: Features list is small (tens of rows); full load without client pagination is acceptable.

### Accessibility

- **NFR-011**: Tabs MUST be keyboard-operable and expose appropriate roles/labels (design-system Tabs already provide tablist/tab).
- **NFR-012**: Confirm dialogs MUST trap focus and be dismissible (cancel / escape where Modal supports it).

### Maintainability

- **NFR-013**: Admin API client helpers SHOULD live in a dedicated module (e.g. `api_admin.ts` or under `services/`).
- **NFR-014**: Panel components SHOULD be split (layout, users table, features table) for testability.

---

## 7. UI/UX Guidelines

1. **Visual language**: Tailwind + existing `design-system` components; match page-container / Card patterns used on Settings and Diagnostics.  
2. **Tabs**: Use design-system `Tabs` (`underline` or `segment` variant).  
3. **Tables**: Simple responsive table or card list; show role as Badge.  
4. **Confirm**: Modal with primary confirm + secondary cancel.  
5. **Toasts**: Success (role updated / feature updated); error with server `detail` when present.  
6. **Copy**: Prefer plain language (“Cannot demote the last active admin”) over raw status codes alone.  
7. **Features controls**: Checkbox pair “Trader” / “Admin” per row + Save (or auto-save with explicit save to reduce accidental PATCH). **Preferred**: explicit **Save** per row or drawer to avoid noisy API calls.  
8. **Forbidden page**: Short title “Admin access required”, explanation, link back to Scanner/Home.  
9. **Nav label**: “Admin” → `/admin` (or `/admin/panel`).  

---

## 8. User Scenarios & Testing

### User Story 1 – Admin-Only Access (P1) 🎯 MVP

**Independent Test**: As trader, open `/admin` → forbidden, no user list. As admin, open `/admin` → panel with tabs. Nav Admin visible only for admin.

1. Trader deep-links `/admin` → forbidden UX; no `GET /admin/users` data rendered.  
2. Admin opens `/admin` → Users tab loads.  
3. Admin sees Admin in nav; trader does not.

### User Story 2 – Manage User Roles (P1)

**Independent Test**: Admin promotes trader → success; demote last admin → error message, role unchanged.

1. List shows users with roles.  
2. Confirm promote trader → admin → row updates.  
3. Last-admin demotion → 400 message shown.  
4. Loading/empty/error states behave correctly.

### User Story 3 – Manage Feature Visibility (P1)

**Independent Test**: Admin sets watchlist to admin-only → success; remove admin from admin_panel → error, UI restored.

1. Features list shows keys and roles.  
2. Edit + save allowed_roles → UI matches response.  
3. Critical feature violation → error + revert.  
4. Loading/error states.

### User Story 4 – Replace Developer-Mode Gate (P1)

**Independent Test**: Admin reaches panel/logs/command without Developer mode; trader cannot with Developer mode on.

1. Admin, developerMode false → `/admin`, `/admin/logs`, `/admin/command` accessible.  
2. Trader, developerMode true → all three still forbidden.  
3. Guard uses AuthContext role only for those routes.

### Edge Cases

- Session expires mid-session → 401 on API → prompt re-login.  
- Stale admin JWT after demotion → 403 from API → show forbidden / logout guidance.  
- Rapid double-submit role change → disable confirm button while pending.  
- Empty users page (no matches on search).  
- Feature save with empty roles on non-critical → allowed if API allows.  

---

## 9. Key Entities (Frontend)

- **Auth User**: id, email, full_name, role.  
- **Admin User Row**: id, email, full_name, role, is_active, created_at.  
- **Feature Permission Row**: id, feature_key, description, allowed_roles, is_active, timestamps.  
- **Admin Tab**: `users` | `features`.  

---

## 10. Acceptance Criteria

### Access & Nav

- [ ] **AC-ACC-01**: Unauthenticated access to Admin Panel redirects to login.  
- [ ] **AC-ACC-02**: Trader access shows forbidden UX; no user/feature admin data shown.  
- [ ] **AC-ACC-03**: Admin access shows Admin Panel with Users and Features tabs.  
- [ ] **AC-ACC-08**: Tab selection syncs with `?tab=users|features`; invalid tab defaults to Users; refresh preserves tab.  
- [ ] **AC-ACC-04**: Admin nav item visible only when `user.role === "admin"`.  
- [ ] **AC-ACC-05**: Guard does not use Developer mode for Admin Panel, logs, or command access.  
- [ ] **AC-ACC-06**: Trader with Developer mode enabled still cannot open `/admin`, `/admin/logs`, or `/admin/command`.  
- [ ] **AC-ACC-07**: Admin with Developer mode off can open `/admin/logs` and `/admin/command` (role is sufficient).  
- [ ] **AC-ACC-09**: Developer mode toggle, if visible, does not grant `/admin/*` access; if unused for non-route UI, toggle is hidden.

### Users Tab

- [ ] **AC-USR-01**: Users load from `GET /admin/users` and render required fields.  
- [ ] **AC-USR-02**: Pagination defaults are valid (page ≥ 1, size ≤ 100).  
- [ ] **AC-USR-03**: Role change requires confirmation.  
- [ ] **AC-USR-04**: Successful role change updates UI + success feedback.  
- [ ] **AC-USR-05**: Last-admin 400 shows error; role unchanged.  
- [ ] **AC-USR-06**: Loading and empty states work.  
- [ ] **AC-USR-07**: 401/403 on list/mutation handled without crash.  
- [ ] **AC-USR-08**: Search input sends `search` query and updates the list (including empty results).

### Features Tab

- [ ] **AC-FEAT-01**: Features load from `GET /admin/features` with key, description, roles, active.  
- [ ] **AC-FEAT-02**: Admin can change allowed_roles and save via PATCH (`allowed_roles` only).  
- [ ] **AC-FEAT-03**: Success updates row from response.  
- [ ] **AC-FEAT-04**: Critical-feature 400 shows error and restores prior roles in UI.  
- [ ] **AC-FEAT-05**: Loading and error states work.  
- [ ] **AC-FEAT-06**: `is_active` is visible but not editable; no is_active PATCH from this UI.  
- [ ] **AC-FEAT-07**: Critical features cannot uncheck Admin in the UI.

### Regression

- [ ] **AC-REG-01**: Trader retail nav unchanged (no Admin entry).  
- [ ] **AC-REG-02**: Auth login/logout and role in context still work.

---

## 11. Success Criteria

- **SC-001**: 100% of non-admin attempts to use Admin Panel fail closed in UI tests (no admin data).  
- **SC-002**: Admins can complete “change a user’s role” with confirmation in one guided flow.  
- **SC-003**: Admins can complete “change a feature’s allowed roles” and see server-confirmed state.  
- **SC-004**: 100% of simulated last-admin and critical-feature errors show user-visible messages without incorrect UI state.  
- **SC-005**: Developer mode no longer grants access to Admin Panel, System Logs, or Central Command; admin role does.  
- **SC-006**: Existing trader primary workflows remain reachable and navigation-clean.

---

## 12. Dependencies

- Sprint 1–3 complete and deployed APIs available.  
- Frontend AuthContext / `useAuth` with `user.role`.  
- Design system Tabs, Modal, Toast, Button, Card, EmptyState, Badge.  
- Existing HTTP client auth (cookies/Bearer) used by the app.

---

## 13. Risks

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| UI-only admin check spoofed | Medium | Backend still enforces; never trust client alone |
| Last-admin confusion | High | Clear 400 copy + no optimistic commit |
| Critical feature mis-edit | High | UI hints + revert on 400 |
| Developer mode confusion | Medium | FR-004/005/AC-ACC-05/06; separate engineering tooling if retained |
| Scope creep into FeatureGuard | Medium | Explicit Sprint 5 boundary |

---

## 14. Sprint Summary

| Component | Mandate |
| :--- | :--- |
| **Guard** | `user.role === "admin"` only |
| **Nav** | Admin entry for admins only |
| **Users tab** | List + confirm + change role; last-admin errors |
| **Features tab** | List + edit allowed_roles; critical-feature errors |
| **Backend** | No changes |
| **FeatureGuard** | Out of scope (Sprint 5) |

---

## 15. Traceability

| Artifact | Path |
| :--- | :--- |
| Spec | [spec.md](./spec.md) |
| Plan | [plan.md](./plan.md) |
| Tasks | [tasks.md](./tasks.md) |
| UI contracts | [contracts/admin-panel-ui.md](./contracts/admin-panel-ui.md) |
| Checklist | [checklists/requirements.md](./checklists/requirements.md) |
