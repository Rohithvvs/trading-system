# Quickstart Validation Guide: Sprint 3 – Feature Permissions System

Validate after implementation. Prefer automated tests first; use these HTTP checks for smoke validation.

## Prerequisites

* DB migrated including feature permissions revision (seed applied).
* Backend running (e.g. `http://localhost:8000`).
* Default admin: `admin@example.com` / `Admin@123` (or env overrides).
* HTTP client (`curl` or equivalent).

Contracts: [contracts/feature-permissions-api.md](./contracts/feature-permissions-api.md).

---

## Scenario 1: Admin Login + List Features

```bash
curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"admin@example.com\",\"password\":\"Admin@123\"}"

curl -s http://localhost:8000/admin/features \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### Expected

* Login 200 with `"role":"admin"`.
* List 200; `items.length` ≥ 7.
* Keys include: `admin_panel`, `user_management`, `system_logs`, `export_data`, `watchlist`, `portfolio_analytics`, `advanced_scanner`.
* Items ordered by `feature_key` ascending.
* Each item: `id`, `feature_key`, `description`, `allowed_roles`, `is_active`, `created_at`, `updated_at`.

---

## Scenario 2: Trader Denied

```bash
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"trader_fp@example.com\",\"password\":\"SecurePassword123!\",\"full_name\":\"FP Trader\"}"

curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/admin/features \
  -H "Authorization: Bearer <TRADER_TOKEN>"
```

### Expected

* HTTP **403**.

---

## Scenario 3: Unauthenticated Denied

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/admin/features
```

### Expected

* HTTP **401**.

---

## Scenario 4: Restrict Watchlist to Admin Only

```bash
curl -s -X PATCH http://localhost:8000/admin/features/watchlist \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"allowed_roles\":[\"admin\"]}"
```

### Expected

* HTTP **200**; `allowed_roles` = `["admin"]`; `updated_at` advanced.

---

## Scenario 5: Canonical Role Order

```bash
curl -s -X PATCH http://localhost:8000/admin/features/watchlist \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"allowed_roles\":[\"admin\",\"trader\"]}"
```

### Expected

* HTTP **200**; response `allowed_roles` is exactly `["trader","admin"]` (not request order).

---

## Scenario 6: Critical Feature Protection

```bash
curl -s -o /dev/null -w "%{http_code}" -X PATCH http://localhost:8000/admin/features/admin_panel \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"allowed_roles\":[\"trader\"]}"

curl -s -o /dev/null -w "%{http_code}" -X PATCH http://localhost:8000/admin/features/user_management \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"is_active\":false}"
```

### Expected

* Both → HTTP **400**.
* Re-list still shows admin on those keys and `is_active: true`.

---

## Scenario 6b: Critical Mixed Payload (no partial apply)

```bash
# Capture description before:
curl -s http://localhost:8000/admin/features \
  -H "Authorization: Bearer <ADMIN_TOKEN>"

curl -s -X PATCH http://localhost:8000/admin/features/admin_panel \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"allowed_roles\":[\"trader\"],\"description\":\"Hacked description\"}"
```

### Expected

* HTTP **400**.
* Description remains the original seed text (not `"Hacked description"`).
* `allowed_roles` still includes `admin`.

---

## Scenario 7: Unknown Feature Key

```bash
curl -s -o /dev/null -w "%{http_code}" -X PATCH http://localhost:8000/admin/features/does_not_exist \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"allowed_roles\":[\"admin\"]}"
```

### Expected

* HTTP **404**.

---

## Scenario 8: Invalid Role Value

```bash
curl -s -o /dev/null -w "%{http_code}" -X PATCH http://localhost:8000/admin/features/watchlist \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"allowed_roles\":[\"superuser\"]}"
```

### Expected

* HTTP **422**.

---

## Scenario 9: Sprint 2 Regression Smoke (catalog-only)

```bash
curl -s http://localhost:8000/admin/users?page=1&size=5 \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

### Expected

* HTTP **200** (Sprint 2 still works; not gated by feature keys).

---

## Scenario 10: Non-admin Discovery Must Not Exist

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/me/features \
  -H "Authorization: Bearer <TRADER_TOKEN>"
```

### Expected

* **404** (or other non-200 for unimplemented route). There is **no** deliberate non-admin feature discovery API this sprint.

---

## Automated Preference

```bash
cd backend
pytest tests/test_feature_permission_service.py `
  tests/test_feature_permissions_list.py `
  tests/test_feature_permissions_update.py `
  tests/test_feature_permission_schemas.py -q
# Also run Sprint 1 + Sprint 2 suites as in CI
```
