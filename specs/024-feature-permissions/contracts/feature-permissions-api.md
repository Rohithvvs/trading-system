# API Contracts: Feature Permissions

**Base path**: `/admin`  
**Auth**: `Authorization: Bearer <access_token>` **or** HttpOnly `access_token` cookie  
**Authorization**: Caller must be an **active, non-deleted** user with **stored** `role = "admin"` via `get_current_admin_user` (live DB check)

**Scope note (clarified)**: These are the only feature-permission HTTP endpoints this sprint. No non-admin discovery API. Existing `/admin/users` routes are unchanged and are **not** gated by feature keys.

---

## Endpoint 1: List Feature Permissions

* **HTTP Method**: `GET`
* **Path**: `/admin/features`
* **Auth Required**: Yes (admin)
* **Summary**: List feature permissions (admin only)

### Query Parameters

None (full catalog; small N).

### Success Response (HTTP 200 OK)

```json
{
  "items": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "feature_key": "admin_panel",
      "description": "Access to the administrative console",
      "allowed_roles": ["admin"],
      "is_active": true,
      "created_at": "2026-07-30T00:00:00.000000Z",
      "updated_at": "2026-07-30T00:00:00.000000Z"
    },
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "feature_key": "advanced_scanner",
      "description": "Advanced scanner tools and views",
      "allowed_roles": ["trader", "admin"],
      "is_active": true,
      "created_at": "2026-07-30T00:00:00.000000Z",
      "updated_at": "2026-07-30T00:00:00.000000Z"
    },
    {
      "id": "33333333-3333-4333-8333-333333333333",
      "feature_key": "export_data",
      "description": "Export data from the platform",
      "allowed_roles": ["admin"],
      "is_active": true,
      "created_at": "2026-07-30T00:00:00.000000Z",
      "updated_at": "2026-07-30T00:00:00.000000Z"
    },
    {
      "id": "44444444-4444-4444-8444-444444444444",
      "feature_key": "portfolio_analytics",
      "description": "Portfolio analytics and reports",
      "allowed_roles": ["trader", "admin"],
      "is_active": true,
      "created_at": "2026-07-30T00:00:00.000000Z",
      "updated_at": "2026-07-30T00:00:00.000000Z"
    },
    {
      "id": "55555555-5555-4555-8555-555555555555",
      "feature_key": "system_logs",
      "description": "View system and operational logs",
      "allowed_roles": ["admin"],
      "is_active": true,
      "created_at": "2026-07-30T00:00:00.000000Z",
      "updated_at": "2026-07-30T00:00:00.000000Z"
    },
    {
      "id": "66666666-6666-4666-8666-666666666666",
      "feature_key": "user_management",
      "description": "List users and change roles",
      "allowed_roles": ["admin"],
      "is_active": true,
      "created_at": "2026-07-30T00:00:00.000000Z",
      "updated_at": "2026-07-30T00:00:00.000000Z"
    },
    {
      "id": "77777777-7777-4777-8777-777777777777",
      "feature_key": "watchlist",
      "description": "Watchlist management and views",
      "allowed_roles": ["trader", "admin"],
      "is_active": true,
      "created_at": "2026-07-30T00:00:00.000000Z",
      "updated_at": "2026-07-30T00:00:00.000000Z"
    }
  ]
}
```

**Ordering**: `feature_key` ascending.  
**Includes**: active and inactive rows.  
**Seed count**: ≥ 7 fixed keys (see data-model seed table).

### Error Responses

#### HTTP 401 Unauthorized

```json
{
  "detail": "Not authenticated"
}
```

#### HTTP 403 Forbidden

```json
{
  "detail": "Admin privileges required"
}
```

---

## Endpoint 2: Update Feature Permission

* **HTTP Method**: `PATCH`
* **Path**: `/admin/features/{feature_key}`
* **Auth Required**: Yes (admin)
* **Summary**: Update feature permission (admin only)

### Path Parameters

| Name | Type | Description |
| :--- | :--- | :--- |
| `feature_key` | string | Stable feature key (e.g. `watchlist`) |

### Request Body

At least one field required.

```json
{
  "allowed_roles": ["admin"],
  "is_active": true,
  "description": "Watchlist management and views"
}
```

#### Field rules

| Field | Type | Required | Rules |
| :--- | :--- | :--- | :--- |
| `allowed_roles` | string[] | No* | Each element exactly `"trader"` or `"admin"`. Full replace when present. Duplicates removed. Stored in canonical order (`trader` then `admin`). Empty `[]` allowed for non-critical only. |
| `is_active` | boolean | No* | Soft enable/disable. `false` forbidden on critical features. |
| `description` | string | No* | Human text; max 255. |

\* At least one of the three must be present.

### Success Response (HTTP 200 OK)

```json
{
  "id": "77777777-7777-4777-8777-777777777777",
  "feature_key": "watchlist",
  "description": "Watchlist management and views",
  "allowed_roles": ["admin"],
  "is_active": true,
  "created_at": "2026-07-30T00:00:00.000000Z",
  "updated_at": "2026-07-30T12:34:56.000000Z"
}
```

### Canonical order example

Request:

```json
{
  "allowed_roles": ["admin", "trader"]
}
```

Response `allowed_roles`:

```json
["trader", "admin"]
```

### Idempotent No-Op (HTTP 200 OK)

If normalized request yields no change vs current row → same response shape; **no** audit event.

### Error Responses

#### HTTP 401 Unauthorized

```json
{
  "detail": "Not authenticated"
}
```

#### HTTP 403 Forbidden

```json
{
  "detail": "Admin privileges required"
}
```

#### HTTP 404 Not Found

```json
{
  "detail": "Feature not found"
}
```

#### HTTP 400 Bad Request — critical feature protection

Removing admin from critical feature:

```json
{
  "detail": "Cannot remove admin from critical feature"
}
```

Disabling critical feature:

```json
{
  "detail": "Cannot deactivate critical feature"
}
```

#### HTTP 422 Unprocessable Entity

Invalid role value:

```json
{
  "detail": [
    {
      "type": "literal_error",
      "loc": ["body", "allowed_roles", 0],
      "msg": "Input should be 'trader' or 'admin'"
    }
  ]
}
```

Empty body (no fields):

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body"],
      "msg": "At least one of allowed_roles, is_active, description must be provided"
    }
  ]
}
```

---

## Status Code Matrix

| Situation | GET /admin/features | PATCH /admin/features/{key} |
| :--- | :---: | :---: |
| No auth | 401 | 401 |
| Trader / demoted former admin | 403 | 403 |
| Success | 200 | 200 |
| Unknown feature_key | — | 404 |
| Critical safety violation | — | 400 |
| Validation error | — | 422 |

---

## In-Process Helper Contract (required)

### `can_access_feature(feature_key: str, role: str) -> bool`

Async/DB-backed service function. **Required deliverable.** Not exposed as HTTP this sprint.

Role resolution: `str(role).strip().lower()` must be exactly `"trader"` or `"admin"`. Do **not** use `normalize_role` if it maps unknown values to `"trader"`.

| Input | Output |
| :--- | :--- |
| Known active feature, role ∈ allowed_roles | `true` |
| Known active feature, role ∉ allowed_roles | `false` |
| Known inactive feature | `false` |
| Unknown feature_key | `false` |
| Unknown/invalid role (e.g. `superuser`) | `false` (even if traders allowed) |
| `"Admin"` / `"TRADER"` | Treated as domain roles after strip+lower |

### Optional: `require_feature(feature_key)` dependency

* **Not** required for Definition of Done.
* If implemented: resolve current user role → 403 when helper returns false.
* Must **not** be applied to existing product or `/admin/users` routes this sprint.

---

## Audit Event Contract

| Field | Value |
| :--- | :--- |
| `event_type` | `admin_feature_permission_change` |
| `user_id` | Acting administrator UUID |
| `metadata.feature_key` | e.g. `watchlist` |
| `metadata.previous_allowed_roles` | list |
| `metadata.new_allowed_roles` | list |
| `metadata.previous_is_active` / `new_is_active` | bool when relevant |
| `metadata.actor_user_id` | uuid string |

Emitted only on **material** successful updates.

---

## OpenAPI

* Tag: **Admin** (shared with Sprint 2)
* Paths registered on existing admin router prefix `/admin`
