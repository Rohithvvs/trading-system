# Release Notes — Sprint 5 Feature Guards (`026-feature-guards`)

**Date**: 2026-07-31  
**Audience**: Operators, API clients, frontend consumers, release managers  

---

## Summary

Sprint 5 connects database-driven feature permissions to the React SPA and complements them with backend product gates so denied features cannot be reached via UI **or** direct API calls.

---

## Breaking / behavioral changes

### 1. Authenticated feature gates on product APIs

The following surfaces now require a valid authenticated principal **and** an active feature permission for the caller’s role:

| Surface | Feature key | Typical effect without access |
| :--- | :--- | :--- |
| Advanced scanner / screener | `advanced_scanner` | `401` unauthenticated; `403` if feature denied |
| System logs list / clear | `system_logs` | `401` / `403` |
| System logs export | `system_logs` + `export_data` | `401` / `403` |
| Paper portfolio / daily analytics | `portfolio_analytics` | `401` / `403` |
| Profile watchlist preference mutations | `watchlist` | `403` when patching `preferences.watchlist` |

**Migration for scripts and tooling**: send session cookie or `Authorization: Bearer <access_token>` on previously open log/scanner calls. Unauthenticated callers receive `401 Unauthorized`.

### 2. Session feature catalog endpoint

| Method | Path | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/features` | Any active authenticated user | Full feature permission catalog for SPA `canAccess` evaluation |

- Mutations remain admin-only under `GET/PATCH /admin/features`.
- Traders no longer depend solely on a static client matrix; Admin Panel policy applies on the next fetch/refetch.
- Client still applies a trader catalog fallback only on HTTP `403` to `/features` (legacy safety net).

### 3. Default SPA landing is `/markets`

| Before | After |
| :--- | :--- |
| `/`, `/home`, brand link, and unknown routes preferred `/scanner` | Prefer **`/markets`** (ungated core landing) |

Direct URLs to gated routes (e.g. `/scanner`) still work when the user has access; otherwise `<AccessDenied />` is shown with **Back to Markets**.

### 4. Backend scope (intentional expansion)

Original Sprint 5 plan constrained work to frontend-only. Delivery **also** includes:

- `GET /features` session catalog  
- `require_feature` / `require_feature_sync` product gates  
- Seed key `central_command` (admin-only) aligned with UI nav  

This satisfies NFR-002 (client guards complement backend enforcement) and is covered by automated tests.

---

## Non-breaking product behavior

- Navigation items with `featureKey` are hidden when `canAccess` is false.
- Export controls (`export_data`) are omitted from the DOM when denied.
- Fail-closed: network / 500 on permission load denies gated features until revalidation.
- Default seed still grants traders `watchlist`, `advanced_scanner`, and `portfolio_analytics` when those rows exist and are active.

---

## Seed feature keys (insert-if-missing)

`admin_panel`, `user_management`, `system_logs`, `central_command`, `export_data`, `watchlist`, `portfolio_analytics`, `advanced_scanner`

Existing databases pick up missing keys (including `central_command`) on catalog list or gate evaluation without a separate migration.

---

## Verification

```bash
# Frontend
cd frontend && npm test -- --run

# Backend (feature + impacted)
cd backend && python -m pytest tests/test_features_session_catalog.py tests/test_require_feature_gates.py tests/integration/test_logs_api.py -q
```

Manual scenarios: see [quickstart.md](./quickstart.md).
