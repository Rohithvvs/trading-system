# Feature Specification: Sprint 5 – Frontend Feature Guards & Integration

**Feature Directory**: `specs/026-feature-guards`  
**Feature Branch**: `026-feature-guards`  
**Created**: 2026-07-31  
**Status**: Specification Ready  
**Target Sprint**: Sprint 5 (Frontend Feature Guards & Integration)  
**Depends On**:
- Sprint 1 – RBAC Foundation (`specs/022-rbac-role-jwt-admin`)
- Sprint 2 – Admin User Management APIs (`specs/023-admin-user-apis`)
- Sprint 3 – Feature Permissions System (`specs/024-feature-permissions`)
- Sprint 4 – Admin Panel UI (`specs/025-admin-panel-ui`)

---

## Clarifications

### Session 2026-07-31

- **Q**: How should the frontend obtain feature permissions given that `GET /admin/features` requires admin privileges?  
  **A**: The `useFeaturePermissions` hook will query `GET /admin/features` for `admin` users to retrieve real-time permissions from the backend DB. For `trader` users (or when `GET /admin/features` returns `403 Forbidden`), the hook gracefully catches the authorization response and evaluates permissions against a client-side feature catalog default filtered by `user.role === "trader"`. This enforces feature security without requiring backend modifications.

- **Q**: What behavior should occur when a user navigates directly via URL to a route protected by a disabled/restricted feature?  
  **A**: The system will display a friendly, brand-consistent `AccessDenied` view (or redirect to `/markets` with an informative toast message), preventing unauthorized page rendering.

- **Q**: What happens if the permission fetch fails due to a network error or API timeout?  
  **A**: The system **fails closed**. In the event of an unresolvable error, access to non-essential/gated features is strictly denied until a successful revalidation occurs.

- **Q**: Which existing pages and UI components must be protected by feature permissions in Sprint 5?  
  **A**: 
  - `watchlist`: Watchlist tab / widget
  - `advanced_scanner`: Advanced scanner features / views
  - `portfolio_analytics`: Performance & analytics views
  - `system_logs`: System logs page (`/admin/logs`)
  - `central_command`: Central command console (`/admin/command`)
  - `export_data`: Data export buttons/dialogs

- **Q**: How should permissions be cached across re-renders and navigation?  
  **A**: Feature permissions will be fetched once upon session initialization (or role change) and managed via a lightweight `FeaturePermissionsContext`. Re-renders and route transitions consume the cached state in memory without redundant network requests.

---

## 1. Overview & Goal

Sprint 5 completes the frontend integration of the Feature Permissions architecture built in Sprint 3 and managed via Sprint 4's Admin Panel.

The primary goal is to establish dynamic frontend authorization gates (`FeatureGuard`, `useFeaturePermissions`, `canAccess`) so that feature visibility and page navigation in the application dynamically adapt to user roles and database-driven feature permission policies.

Key outcomes:
1. **Dynamic Navigation**: Navigation items automatically hide when the current user lacks the required role or feature permission.
2. **Component & Page Guards**: UI components and full pages are wrapped with `<FeatureGuard>` components that enforce permissions cleanly.
3. **Fail-Closed Security**: Missing, loading, or failed permission checks deny access by default to prevent privilege leakage.
4. **Developer Experience**: Simple, clean API for feature protection (`<FeatureGuard feature="watchlist">`, `canAccess("export_data")`).

---

## 2. Background & Context

| Sprint | Capability Delivered | Status |
| :--- | :--- | :--- |
| **Sprint 1** | RBAC Foundation (`trader` \| `admin` roles, JWT claims) | Done |
| **Sprint 2** | Admin User Management APIs (`/admin/users`) | Done |
| **Sprint 3** | Database-driven Feature Permissions API (`/admin/features`) | Done |
| **Sprint 4** | Admin Panel UI (Users & Features tabs at `/admin`) | Done |
| **Sprint 5** | Frontend Feature Guards & Navigation Integration | **This Sprint** |

**Gap Closed**: Prior to Sprint 5, backend feature permissions existed in the database and could be edited via the Admin Panel (Sprint 4), but the frontend UI did not respect these feature permissions when rendering pages, component controls, or navigation links. Sprint 5 connects the backend permissions to the actual user experience.

---

## 3. In Scope / Out of Scope

### In Scope
- `useFeaturePermissions()` hook for accessing permission state and helper utilities.
- `FeaturePermissionsProvider` context for caching feature rules and avoiding redundant fetches.
- `<FeatureGuard feature="...">` component for declarative conditional rendering and route protection.
- `canAccess(featureKey)` synchronous evaluation helper.
- Update `navConfig.ts` and `AppShell` navigation filtering to evaluate feature keys in addition to role checks.
- Application of guards to key existing pages/features: Watchlist, Advanced Scanner, Portfolio Analytics, System Logs, Central Command, and Data Export.
- Loading states (skeletons/spinners) while permissions are resolved.
- Unauthorized/Access Denied fallback UI and safe route redirection.
- Automated unit and component tests (Vitest + React Testing Library) covering guard scenarios.
- **Backend complement (NFR-002)**: authenticated session catalog `GET /features`; `require_feature` product gates on scanner, logs, paper analytics, and watchlist mutations; seed key `central_command`.
- Ungated core landing at `/markets` (fail-closed default route).

### Out of Scope
- New database schema / Alembic migrations (catalog uses existing `feature_permissions` table; insert-if-missing seed only).
- Modifications to the Admin Panel UI implemented in Sprint 4 (aside from permission refetch after policy save).
- Hierarchical permission inheritance (e.g., parent/child feature trees).
- Complete visual redesign of existing application pages.

---

## 4. Functional Requirements (FR-xxx)

### FR-001: Feature Permissions Context & Hook (`useFeaturePermissions`)
- The system MUST provide a `FeaturePermissionsProvider` and `useFeaturePermissions()` hook.
- The hook MUST expose:
  - `permissions`: Record or Map of `feature_key` -> `FeaturePermission`
  - `isLoading`: boolean state during initial fetch
  - `error`: Error | null state
  - `canAccess(featureKey: string): boolean` helper method
  - `refetchPermissions(): Promise<void>` for manual revalidation
- Permissions MUST be fetched once upon user authentication and cached in context memory.

### FR-002: Declarative Feature Guard Component (`FeatureGuard`)
- The system MUST provide a `<FeatureGuard>` component accepting props:
  - `feature`: string (e.g. `"watchlist"`, `"advanced_scanner"`, `"export_data"`)
  - `children`: React.ReactNode (rendered when access is granted)
  - `fallback`?: React.ReactNode (rendered when access is denied; defaults to `null` for inline controls or `AccessDenied` view for routes)
  - `loadingFallback`?: React.ReactNode (rendered while permissions are fetching)
- `<FeatureGuard>` MUST evaluate permissions using `canAccess(feature)`.
- If the feature is inactive (`is_active === false`) or the user's role is not included in `allowed_roles`, access MUST be denied.

### FR-003: Programmatic Helper (`canAccess`)
- The system MUST export a standalone utility or hook method `canAccess(featureKey: string): boolean`.
- `canAccess` MUST return `true` ONLY if:
  - The feature exists in the permissions map.
  - The feature `is_active` flag is `true`.
  - The current user's normalized role (`user.role`) is contained within `allowed_roles`.
- For unknown feature keys or unauthenticated users, `canAccess` MUST return `false` (fail-closed).

### FR-004: Dynamic Navigation Filtering (`navConfig` & `AppShell`)
- The `NavItem` configuration schema MUST be extended with an optional `featureKey?: string` property.
- `RETAIL_NAV` and `ADMIN_NAV` items MUST declare their required `featureKey` where applicable (e.g., `scanner` -> `advanced_scanner`, `performance` -> `portfolio_analytics`).
- `AppShell` MUST filter navigation items using both role eligibility and feature access (`canAccess`).
- Navigation links for features that the user cannot access MUST be completely hidden from the sidebar and navigation menus.

### FR-005: Protected Route Enforcement
- Routes requiring feature access MUST be wrapped with `<FeatureGuard>` or a feature-aware route wrapper.
- If a user directly navigates to a URL for a feature they cannot access (e.g., `/scanner` when `advanced_scanner` is disabled):
  - The page MUST NOT render sensitive feature content.
  - The view MUST render an `AccessDenied` screen with a friendly message and a button returning to `/markets` or the home view.

### FR-006: Integration with Key Application Features
- Feature guards MUST be applied to the following application surfaces:
  - **Watchlist** (`feature_key: "watchlist"`): Gated in UI tabs / views.
  - **Advanced Scanner** (`feature_key: "advanced_scanner"`): Gated on `/scanner` route and related controls.
  - **Portfolio Analytics** (`feature_key: "portfolio_analytics"`): Gated on `/performance` route.
  - **System Logs** (`feature_key: "system_logs"`): Gated on `/admin/logs` route.
  - **Central Command** (`feature_key: "central_command"` or `admin_panel`): Gated on `/admin/command` route.
  - **Data Export** (`feature_key: "export_data"`): Export buttons gated inside data tables.

### FR-007: Fail-Closed Security & Error Handling
- If feature permissions fail to load (network error, HTTP 500, timeout):
  - The system MUST fail closed and treat all non-essential features as unauthorized.
  - Core essential features (e.g., basic markets view) remain accessible if un-gated.
  - An unobtrusive warning toast MAY be presented to the user indicating permission sync failure.

---

## 5. Non-Functional Requirements (NFR-xxx)

- **NFR-001: Performance & Zero Redundant Fetching**: Permission checks MUST execute synchronously in memory without blocking UI rendering or causing multi-second delays.
- **NFR-002: Security & Authorization Integrity**: Client-side feature guards MUST complement backend enforcement without exposing protected component DOM nodes when access is denied.
- **NFR-003: Type Safety**: All feature keys MUST be strongly typed using TypeScript string literal unions (`FeatureKey`) matching backend seed data.
- **NFR-004: Maintainability**: Adding a guard to a new component MUST require no more than 3 lines of code (e.g., `<FeatureGuard feature="my_feature"><Component /></FeatureGuard>`).
- **NFR-005: Testability**: Unit and component tests MUST achieve >90% code coverage across `FeatureGuard`, `useFeaturePermissions`, and nav filtering.

---

## 6. Acceptance Criteria (AC-xxx)

### AC-FEAT-01: Permission Fetch & Context
- **Given** an authenticated user logs in,
- **When** `FeaturePermissionsProvider` initializes,
- **Then** feature permissions are fetched from backend (or resolved via client-side defaults for trader roles) and cached in context memory without repeated fetch calls on re-renders.

### AC-FEAT-02: FeatureGuard Access Granted
- **Given** feature permission `"watchlist"` has `allowed_roles: ["trader", "admin"]` and `is_active: true`,
- **When** a `trader` user renders `<FeatureGuard feature="watchlist"><WatchlistWidget /></FeatureGuard>`,
- **Then** `<WatchlistWidget />` renders normally.

### AC-FEAT-03: FeatureGuard Access Denied (Inline)
- **Given** feature permission `"export_data"` has `allowed_roles: ["admin"]`,
- **When** a `trader` user renders `<FeatureGuard feature="export_data"><ExportButton /></FeatureGuard>`,
- **Then** `<ExportButton />` is NOT rendered in the DOM, and fallback (or `null`) is displayed.

### AC-FEAT-04: FeatureGuard Access Denied (Route Level)
- **Given** feature permission `"advanced_scanner"` has `is_active: false` or does not allow the current user's role,
- **When** the user attempts direct URL navigation to `/scanner`,
- **Then** an `AccessDenied` component is displayed with options to navigate back to `/markets`.

### AC-FEAT-05: Dynamic Navigation Filtering
- **Given** feature `"portfolio_analytics"` is restricted to `["admin"]`,
- **When** a `trader` user views the sidebar navigation,
- **Then** the "Performance" item (`/performance`) is hidden from the sidebar menu.

### AC-FEAT-06: Fail-Closed Behavior
- **Given** the permission fetch API encounters a 500 error or network disconnect,
- **When** permissions fail to load,
- **Then** `canAccess` returns `false` for all feature keys, preventing unauthorized rendering of gated components.

---

## 7. Success Criteria

1. **100% Protection of Specified Features**: All 6 target features (`watchlist`, `advanced_scanner`, `portfolio_analytics`, `system_logs`, `central_command`, `export_data`) are fully protected by `FeatureGuard` or nav filters.
2. **Zero Unintended Information Leakage**: Denied components do not render hidden or inspectable sensitive DOM nodes.
3. **Clean UX & Smooth Loading**: Permission resolution completes seamlessly without layout flickering or layout shift.
4. **Comprehensive Test Suite**: All guard components, hooks, and nav filtering logic pass automated unit and integration tests.
