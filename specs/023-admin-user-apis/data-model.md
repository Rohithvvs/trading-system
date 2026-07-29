# Phase 1 Data Model: Sprint 2 – Backend Authorization + User Management APIs

## Overview

Sprint 2 **does not introduce new database tables**. It reuses the Sprint 1 `users` entity and `audit_logs` entity. This document defines the **logical views**, **API-facing DTOs**, and **state rules** used by admin user-management operations.

---

## 1. Existing Entity: User Account (`users`)

### Attributes (relevant subset)

| Field | Type | Notes |
| :--- | :--- | :--- |
| `id` | UUID | Primary key |
| `email` | string | Unique, non-null |
| `full_name` | string | Non-null |
| `role` | string | `trader` \| `admin` (CHECK constrained) |
| `is_active` | boolean | Soft disable without delete |
| `deleted_at` | timestamp \| null | Soft-delete marker |
| `password_hash` | string | **Never** returned by admin APIs |
| `created_at` | timestamp | Account creation |
| `updated_at` | timestamp | Last modification |

### Eligibility predicates

| Context | Predicate |
| :--- | :--- |
| **Directory list (default)** | `is_active = true` AND `deleted_at IS NULL` |
| **Last-admin count** | `role = 'admin'` AND `is_active = true` AND `deleted_at IS NULL` |
| **Role-change target** | Same as directory eligibility; else treat as not found |
| **Admin API caller** | Authenticated user matching eligibility **and** `role = 'admin'` |

### Role domain

```
VALID: "trader" | "admin"
DEFAULT (registration): "trader"   # Sprint 1 — unchanged
```

### Role transitions (admin-initiated)

```
trader  --promote-->  admin     # always allowed (if target eligible)
admin   --demote--->  trader    # blocked if would leave 0 eligible admins
role    --same----->  role      # no-op success; no audit
```

---

## 2. Existing Entity: Audit Log (`audit_logs`)

### Attributes used for role change

| Field | Value / Source |
| :--- | :--- |
| `user_id` | Acting administrator id (preferred) |
| `event_type` | `admin_role_change` |
| `ip_address` | Request client IP (optional) |
| `user_agent` | Request UA (optional) |
| `metadata` | JSON: see below |
| `created_at` | Server timestamp |

### Metadata schema (role change)

```json
{
  "actor_user_id": "<uuid>",
  "target_user_id": "<uuid>",
  "previous_role": "trader",
  "new_role": "admin",
  "target_email": "user@example.com"
}
```

* `target_email` is optional but recommended for human-readable audit review.
* No-ops and failed mutations do **not** write this event type.

---

## 3. API DTOs (not persisted)

### UserAdminResponse

| Field | Type | Required |
| :--- | :--- | :--- |
| `id` | string (UUID) | yes |
| `email` | string | yes |
| `full_name` | string | yes |
| `role` | `"trader"` \| `"admin"` | yes |
| `is_active` | boolean | yes |
| `created_at` | datetime (ISO-8601) | yes |

**Excluded**: password_hash, reset tokens, google_id secrets, etc.

### UserListResponse

| Field | Type | Required |
| :--- | :--- | :--- |
| `items` | UserAdminResponse[] | yes |
| `total` | integer ≥ 0 | yes |
| `page` | integer ≥ 1 | yes |
| `size` | integer 1–100 | yes |

### UpdateRoleRequest

| Field | Type | Required |
| :--- | :--- | :--- |
| `role` | `"trader"` \| `"admin"` | yes |

---

## 4. Query Parameters (List)

| Param | Type | Default | Constraints |
| :--- | :--- | :--- | :--- |
| `page` | int | 1 | ≥ 1 |
| `size` | int | 20 | 1–100 |
| `search` | string \| omit | — | Partial match email OR full_name (case-insensitive) |
| `role` | string \| omit | — | If present: `trader` or `admin` only |

---

## 5. Validation Rules Summary

1. Role values outside `{trader, admin}` → request validation failure (422).
2. Role change target not eligible → 404.
3. Demotion leaving zero eligible admins → 400.
4. Caller not live admin → 403 (or 401 if unauthenticated).
5. Password hashes and secrets never appear in admin list/role responses.

---

## 6. Relationships

```
Administrator (User, role=admin, active)
    |-- lists --> User[] (eligible)
    |-- changes role --> User (eligible)
    |-- writes --> AuditLog (on real role change)
```

No new foreign keys. `AuditLog.user_id` continues to reference the acting user when provided.
