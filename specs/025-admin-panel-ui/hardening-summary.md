# Hardening Summary: Admin Panel UI

**Feature**: `025-admin-panel-ui` (Sprint 4)  
**Date**: 2026-07-30  
**Source**: Audit findings (PASS WITH MINOR ISSUES → APPROVED FOR HARDENING) + `Document/Hardening.md`  
**Validation**: Admin FE suite **36 passed** (7 files); no new product tests required by Hardening prompt

---

## Hardening Summary

### Files modified

| File | Change |
|---|---|
| `frontend/src/api_admin.ts` | **H-1** Default 25s abort timeout on all admin fetches; merges external `AbortSignal`; portable `setTimeout`/`clearTimeout`; `isAuthzAdminError` helper; **M-3** dev-only request diagnostics (timing, status, redacted path; no tokens/bodies) |
| `frontend/src/components/AdminRoute.tsx` | **H-2** Forbidden CTA uses SPA `Link` (no full reload; valid markup) |
| `frontend/src/components/admin/UsersAdminTab.tsx` | **M-1** AbortController on load unmount/dep change; **M-2** 401/403 fail-closed logout (stable refs + sessionClosed guard); **M-4** search debounce only resets page when search value changes |
| `frontend/src/components/admin/FeaturesAdminTab.tsx` | **M-1** AbortController on load; **M-2** 401/403 fail-closed logout with same loop-safe pattern |
| `frontend/src/components/__tests__/UsersAdminTab.test.tsx` | Mock `useAuth`; assert logout on 403; keep retry UI on non-authz 500 |
| `frontend/src/components/__tests__/FeaturesAdminTab.test.tsx` | Mock `useAuth` for logout wiring |

### Audit findings resolved

| ID | Severity | Resolution |
|---|---|---|
| **H-1** | High | `ADMIN_FETCH_TIMEOUT_MS = 25_000` aborts hung admin API calls; external unmount signals still cancel in-flight work |
| **H-2** | High | Forbidden “Back to Scanner” is a React Router `Link` with design-system button classes |
| **M-1** | Medium | Users + Features tabs abort `list*` on unmount and when load deps change |
| **M-2** | Medium | 401/403 on list or mutation → toast + `logout()`; one-shot `sessionClosedRef` prevents re-fetch / toast-identity loops |
| **M-3** | Medium | Dev-only `[admin-api]` request/response timing + HTTP/network failure logs; `search` query redacted; no tokens/cookies/bodies (NFR-003) |
| **M-4** | Medium | Search debounce skips redundant `setPage(1)` / `setSearch` when value unchanged (incl. first init) |

### Reliability improvements

- Admin network calls cannot hang indefinitely (timeout + abort).
- Tab unmount no longer races setState after resolve.
- Authz failure is fail-closed once (logout) without infinite load loops caused by Toast context identity changing when `toasts` updates.
- Non-authz errors still show inline error + Retry.

### Performance improvements

- Avoided redundant page-reset/search reloads on debounce ticks when the trimmed query is unchanged (M-4).
- Abort of superseded list requests reduces wasted work on page/search changes.

### Security improvements

- 401/403 no longer leave the admin UI in a half-loaded “retry forever” state with an invalid session.
- Role gate remains JWT/session role-based (`AdminRoute`); developer mode still does not unlock `/admin`.
- Diagnostics never log credentials or raw search PII.

### Observability improvements

- **M-3**: Admin client mirrors main `api.ts` diagnostics — `console.info`/`console.warn` in DEV only with label, method, redacted path, status, and elapsed ms. Expected aborts log at info; gateway/HTTP/network failures at warn.

---

## Remaining Audit Findings

| ID | Severity | Status | Why left unresolved |
|---|---|---|---|
| — | — | **None** | All audit items H-1, H-2, M-1, M-2, M-3, M-4 addressed |

---

## Validation Checklist

- ✅ Critical findings resolved (none open; H-level treated as blocking for this soft-fix pass)
- ✅ High findings resolved (H-1, H-2)
- ✅ Medium findings resolved (M-1, M-2, M-3, M-4)
- ✅ Architecture preserved (FE-only admin client + role gate + tabs; no backend / FeatureGuard)
- ✅ Existing functionality preserved (users/features CRUD UI, tab URL, critical feature lock)
- ✅ Specification preserved (Sprint 4 AC matrix still covered)
- ✅ Existing tests remain valid (**37 passed** after mock + M-2/M-3 alignment)
- ✅ Ready for Regression Testing

---

## Notes

- Hardening did **not** add features, redesign architecture, or expand beyond audit-driven reliability/security/observability fixes.
- Test file edits only keep the suite valid under intentional M-2 behavior (logout on 401/403) and M-3 signal attachment.
- Run suite from `frontend/`:  
  `npm test -- src/components/__tests__/UsersAdminTab.test.tsx src/components/__tests__/FeaturesAdminTab.test.tsx src/components/__tests__/AdminRoute.test.tsx src/components/__tests__/AdminPanelPage.test.tsx src/components/__tests__/api_admin.test.ts src/components/__tests__/navConfig.admin.test.ts src/components/__tests__/sprint4_admin_panel_ac_matrix.test.tsx`
