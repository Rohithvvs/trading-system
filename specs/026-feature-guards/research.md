# Research & Design Decisions: Sprint 5 – Frontend Feature Guards & Integration

**Feature Directory**: `specs/026-feature-guards`  
**Date**: 2026-07-31  

---

## 1. Permission Caching & Context Architecture

### Decision
Implement `FeaturePermissionsContext` and `FeaturePermissionsProvider` at the root of the React component tree (inside `AuthProvider`).

### Rationale
- **Zero Redundant Fetches**: Feature permissions are fetched once upon session load or role change and stored in memory. Component re-renders or navigation transitions perform synchronous in-memory checks.
- **Consistency**: All component guards (`<FeatureGuard>`), route guards, and navigation items query the same synchronized source of truth.
- **Developer Simplicity**: Any component can consume permission checks via `useFeaturePermissions()` or `canAccess(featureKey)`.

### Alternatives Considered
1. **Fetch permissions inside individual `<FeatureGuard>` components**:
   - *Rejected*: Causes severe N+1 network fetch fanout across table cells, export buttons, and navigation links.
2. **External State Management Library (Redux/Zustand)**:
   - *Rejected*: Adds unnecessary package dependencies when React Context natively handles light session state.

---

## 2. Non-Admin (`trader`) Permission Resolution

### Decision (delivered)
Use **`GET /features`** (authenticated session catalog) for **all** roles so Admin Panel policy applies to traders and admins alike. Keep a client-side trader catalog matrix as a **legacy safety net** only when the session catalog returns HTTP `403`.

### Rationale
- **Live policy for traders**: Static-only trader matrix cannot reflect Admin Panel restrictions (e.g. `portfolio_analytics` → admin-only).
- **NFR-002**: Client guards must complement backend enforcement; a readable session catalog is required for correct SPA evaluation.
- **Safety net**: Trader `403` fallback preserves access if a misconfigured deploy still blocks non-admins from the catalog endpoint.
- **Admin mutations** remain on `/admin/features` (Sprint 3/4).

### Alternatives Considered
1. **Admin-only `GET /admin/features` + static trader matrix only**:
   - *Rejected in delivery*: Admin policy changes would not affect traders until next deploy of client defaults.
2. **Public unauthenticated catalog**:
   - *Rejected*: Exposes full role policy without session binding.

---

## 3. Unauthorized Route Handling & Fail-Closed Strategy

### Decision
When an unauthorized user attempts direct URL navigation to a protected route (e.g. `/scanner` when `advanced_scanner` is disabled or restricted), render a dedicated `<AccessDenied />` page component. If permission fetch fails due to network error, fail closed by default.

### Rationale
- **Security First**: Failing closed prevents privilege escalation or information leakage during API outages.
- **User Experience**: Providing a clean, brand-consistent `<AccessDenied />` screen with a primary "Back to Markets" button prevents blank white screens or uncaught React router exceptions.

---

## 4. Navigation Config Annotations (`navConfig`)

### Decision
Extend the existing `NavItem` type in `navConfig.tsx` with an optional `featureKey?: string` field and filter navigation items inside `AppShell.tsx`.

### Rationale
- **Declarative Navigation**: Menu items automatically declare their required feature key alongside role constraints.
- **Single Source of Truth**: Sidebar and navigation bars cleanly hide links to features the user cannot access.
