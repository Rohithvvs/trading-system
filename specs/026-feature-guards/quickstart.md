# Quickstart Validation Guide: Sprint 5 – Frontend Feature Guards

**Feature Directory**: `specs/026-feature-guards`  
**Date**: 2026-07-31  
**Release notes**: [RELEASE_NOTES.md](./RELEASE_NOTES.md)

---

## Ops / client notes (before testing)

1. **Default landing** after login/home is **`/markets`** (not `/scanner`).
2. API callers must authenticate for gated product endpoints (`/api/logs*`, screener/scanner, paper analytics). See release notes.
3. SPA loads permissions via **`GET /features`** (session catalog).

---

## Runnable Verification Scenarios

### Scenario 1: Trader Navigation & Feature Protection
1. Log in as a user with role `trader`.
2. Confirm the app lands on **`/markets`** (or brand link navigates there).
3. Observe the sidebar navigation menu:
   - **Expectation**: "Markets", "Scanner", "Paper Desk", "Performance", and "Profile" links are visible. "Admin", "Central Command", "System Logs", and "Diagnostics" links are hidden.
4. Open a data table or candidate list:
   - **Expectation**: "Export Data" buttons are hidden from the DOM because `export_data` requires role `admin`.
5. Directly enter `/admin/logs` into the browser URL bar:
   - **Expectation**: The page renders the `<AccessDenied />` view instead of system logs. Clicking "Back to Markets" navigates safely to `/markets`.

### Scenario 2: Admin Dynamic Feature Control
1. Log in as a user with role `admin`.
2. Navigate to Admin Panel (`/admin?tab=features`).
3. Edit the `allowed_roles` for feature `portfolio_analytics` (Performance) to remove `trader` or toggle `is_active` to `false`, and click Save.
4. Log out and log back in as a `trader` (SPA loads `GET /features`):
   - **Expectation**: "Performance" item is immediately hidden from the sidebar navigation. Navigating directly to `/performance` shows the `<AccessDenied />` screen.

### Scenario 3: Fail-Closed Network Error Verification
1. Simulate a backend API failure (e.g. mock a 500 error on `GET /features`).
2. Reload the application:
   - **Expectation**: Non-essential feature access evaluates to `false` (fail-closed posture), preventing unauthorized access to protected components.

---

## Automated Test Execution

Run the frontend test suite to verify Feature Guards and navigation filtering:

```bash
cd frontend
npm run test
```

Specific test files:
```bash
npx vitest run src/hooks/__tests__/useFeaturePermissions.test.tsx
npx vitest run src/components/__tests__/FeatureGuard.test.tsx
npx vitest run src/components/__tests__/navConfig.featureGuards.test.tsx
```
