# Quickstart Validation Guide: Sprint 2 – Admin User Management APIs

This guide validates Sprint 2 after implementation. Prefer automated tests first; use these HTTP checks for smoke validation.

## Prerequisites

* Database migrated (Sprint 1 role normalization applied).
* Backend running (e.g. `http://localhost:8000`).
* Default admin available: `admin@example.com` / `Admin@123` (or env overrides).
* HTTP client (`curl` or equivalent).

See contracts: [contracts/admin-api.md](./contracts/admin-api.md).

---

## Scenario 1: Admin Login + List Users

### Action

```bash
# 1) Login as admin
curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"admin@example.com\",\"password\":\"Admin@123\"}"

# 2) Copy access_token from response, then:
curl -s http://localhost:8000/admin/users?page=1&size=20 \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### Expected

* Login HTTP 200 with `"role":"admin"`.
* List HTTP 200 with `items`, `total`, `page`, `size`.
* Items include only active users with fields: id, email, full_name, role, is_active, created_at.

---

## Scenario 2: Trader Denied

### Action

Register a trader (or use existing), login, call list:

```bash
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"trader_qs@example.com\",\"password\":\"SecurePassword123!\",\"full_name\":\"QS Trader\"}"

# Use trader access_token:
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/admin/users \
  -H "Authorization: Bearer <TRADER_TOKEN>"
```

### Expected

* HTTP **403**.

---

## Scenario 3: Unauthenticated Denied

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/admin/users
```

### Expected

* HTTP **401**.

---

## Scenario 4: Promote Trader → Admin

```bash
curl -s -X PATCH http://localhost:8000/admin/users/<TRADER_USER_ID>/role \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"role\":\"admin\"}"
```

### Expected

* HTTP **200**, `"role":"admin"`.
* Audit log row `admin_role_change` with previous_role=trader, new_role=admin.

---

## Scenario 5: Last-Admin Protection

### Action

With only one active admin remaining, attempt:

```bash
curl -s -X PATCH http://localhost:8000/admin/users/<SOLE_ADMIN_ID>/role \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"role\":\"trader\"}"
```

### Expected

* HTTP **400**.
* User role remains `admin`.

---

## Scenario 6: Invalid Role → 422

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -X PATCH http://localhost:8000/admin/users/<USER_ID>/role \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"role\":\"superuser\"}"
```

### Expected

* HTTP **422**.

---

## Automated Validation (preferred)

From `backend/`:

```bash
# New Sprint 2 suites (names may match tasks.md)
pytest tests/test_admin_deps.py tests/test_admin_users_list.py tests/test_admin_users_role.py -v

# Sprint 1 regression
pytest tests/test_sprint1_rbac_comprehensive.py tests/test_auth_register.py tests/test_auth_jwt_login.py -v
```

### Expected

* All selected tests **pass**.

---

## Definition of Smoke Success

| Check | Pass? |
| :--- | :--- |
| Admin can list users | |
| Trader gets 403 | |
| Anon gets 401 | |
| Promote works | |
| Last-admin demotion blocked | |
| Invalid role 422 | |
| Sprint 1 auth still green | |
