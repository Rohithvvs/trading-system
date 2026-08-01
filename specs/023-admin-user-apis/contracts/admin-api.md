# API Contracts: Admin User Management

**Base path**: `/admin`  
**Auth**: Session identity via `Authorization: Bearer <access_token>` **or** HttpOnly `access_token` cookie  
**Authorization**: Caller must be an **active, non-deleted** user with **stored** `role = "admin"` (live DB check)

---

## Endpoint 1: List Users

* **HTTP Method**: `GET`
* **Path**: `/admin/users`
* **Auth Required**: Yes (admin)

### Query Parameters

| Name | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `page` | integer | No | `1` | Page number (≥ 1) |
| `size` | integer | No | `20` | Page size (1–100) |
| `search` | string | No | — | Case-insensitive partial match on email or full_name |
| `role` | string | No | — | Filter: `trader` or `admin` |

### Success Response (HTTP 200 OK)

```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "email": "trader@example.com",
      "full_name": "Jane Doe",
      "role": "trader",
      "is_active": true,
      "created_at": "2026-07-20T10:15:30.000000Z"
    },
    {
      "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "email": "admin@example.com",
      "full_name": "Default Admin",
      "role": "admin",
      "is_active": true,
      "created_at": "2026-07-01T00:00:00.000000Z"
    }
  ],
  "total": 2,
  "page": 1,
  "size": 20
}
```

### Error Responses

#### HTTP 401 Unauthorized — missing/invalid authentication

```json
{
  "detail": "Not authenticated"
}
```

#### HTTP 403 Forbidden — authenticated but not a live admin

```json
{
  "detail": "Admin privileges required"
}
```

#### HTTP 422 Unprocessable Entity — invalid query params

Examples: `page=0`, `size=101`, `role=superuser`

```json
{
  "detail": [
    {
      "type": "greater_than_equal",
      "loc": ["query", "page"],
      "msg": "Input should be greater than or equal to 1"
    }
  ]
}
```

---

## Endpoint 2: Update User Role

* **HTTP Method**: `PATCH`
* **Path**: `/admin/users/{user_id}/role`
* **Auth Required**: Yes (admin)

### Path Parameters

| Name | Type | Description |
| :--- | :--- | :--- |
| `user_id` | UUID string | Target user id |

### Request Body

```json
{
  "role": "admin"
}
```

`role` MUST be exactly `"trader"` or `"admin"`.

### Success Response (HTTP 200 OK)

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "email": "trader@example.com",
  "full_name": "Jane Doe",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-07-20T10:15:30.000000Z"
}
```

### Idempotent No-Op (HTTP 200 OK)

Requesting the same role the user already has returns the same shape; **no** audit event is written.

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

#### HTTP 404 Not Found — missing, inactive, or soft-deleted target

```json
{
  "detail": "User not found"
}
```

#### HTTP 400 Bad Request — last-admin protection

```json
{
  "detail": "Cannot demote the last active admin"
}
```

#### HTTP 422 Unprocessable Entity — invalid body or path UUID

Invalid role:

```json
{
  "detail": [
    {
      "type": "literal_error",
      "loc": ["body", "role"],
      "msg": "Input should be 'trader' or 'admin'"
    }
  ]
}
```

Invalid `user_id` format:

```json
{
  "detail": [
    {
      "type": "uuid_parsing",
      "loc": ["path", "user_id"],
      "msg": "Input should be a valid UUID"
    }
  ]
}
```

---

## Status Code Matrix

| Situation | GET /admin/users | PATCH .../role |
| :--- | :---: | :---: |
| No auth | 401 | 401 |
| Trader / demoted former admin | 403 | 403 |
| Success | 200 | 200 |
| Validation error | 422 | 422 |
| Target not found / inactive / deleted | — | 404 |
| Last active admin demotion | — | 400 |

---

## Security Notes

1. Never return `password_hash`, reset tokens, or secrets in responses.
2. Authorization uses **live stored role**, not JWT claim alone.
3. Last-admin rule uses **active + non-deleted** admins only.
4. Successful privilege-changing PATCHes MUST create audit event `admin_role_change`.
