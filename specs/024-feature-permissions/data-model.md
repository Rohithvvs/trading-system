# Phase 1 Data Model: Sprint 3 – Feature Permissions System

## Overview

Sprint 3 introduces one new persisted entity: **Feature Permission** (`feature_permissions`). It reuses **User** (admin principal) and **Audit Log**. No changes to the Sprint 1 role domain or Sprint 2 user-management tables.

---

## 1. New Entity: Feature Permission (`feature_permissions`)

### Purpose

Runtime rules mapping a stable `feature_key` → which roles may access (or see) that feature. Source of truth for admin “Feature Visibility” and backend `can_access_feature`.

### Attributes

| Field | Type | Constraints | Notes |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PK, not null, default uuid4 | Internal identity |
| `feature_key` | VARCHAR(64) | NOT NULL, **UNIQUE** | Public stable key, e.g. `watchlist` |
| `description` | VARCHAR(255) | NOT NULL | Human-readable purpose |
| `allowed_roles` | JSONB | NOT NULL, default `'[]'` | JSON array of role strings |
| `is_active` | BOOLEAN | NOT NULL, default `true` | Soft disable (non-critical only) |
| `created_at` | TIMESTAMPTZ | NOT NULL, default `now()` | Creation time |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default `now()`, on update | Last mutation |

### Indexes / Constraints

| Name | Definition | Purpose |
| :--- | :--- | :--- |
| PK | PRIMARY KEY (`id`) | Row identity |
| `uq_feature_permissions_feature_key` | UNIQUE (`feature_key`) | Lookup + seed idempotency |

### `feature_key` rules

* Pattern: `^[a-z][a-z0-9_]*$`
* Max length 64
* Immutable after seed (no rename/create API this sprint)
* System-owned

### `allowed_roles` rules

* JSON array of unique strings
* Only `"trader"` and/or `"admin"`
* **Canonical order** (clarified): when both present → `["trader", "admin"]`; else `["trader"]` or `["admin"]`
* Empty array `[]` allowed for **non-critical** features → helper denies all roles
* Full replace on PATCH when field is present

### Example row

```json
{
  "id": "c0ffee00-0000-4000-8000-000000000001",
  "feature_key": "watchlist",
  "description": "Watchlist management and views",
  "allowed_roles": ["trader", "admin"],
  "is_active": true,
  "created_at": "2026-07-30T00:00:00.000000Z",
  "updated_at": "2026-07-30T00:00:00.000000Z"
}
```

---

## 2. Seed Data (Idempotent)

Insert **if not exists** by `feature_key`. Never overwrite operator-customized rows on re-seed.

| feature_key | description | allowed_roles | is_active | critical? |
| :--- | :--- | :--- | :---: | :---: |
| `admin_panel` | Access to the administrative console | `["admin"]` | true | **Yes** |
| `user_management` | List users and change roles | `["admin"]` | true | **Yes** |
| `system_logs` | View system and operational logs | `["admin"]` | true | No |
| `export_data` | Export data from the platform | `["admin"]` | true | No |
| `watchlist` | Watchlist management and views | `["trader", "admin"]` | true | No |
| `portfolio_analytics` | Portfolio analytics and reports | `["trader", "admin"]` | true | No |
| `advanced_scanner` | Advanced scanner tools and views | `["trader", "admin"]` | true | No |

### Critical feature set (application constant)

```text
CRITICAL_FEATURE_KEYS = frozenset({"admin_panel", "user_management"})
```

Rules:

1. Critical `allowed_roles` **must always include** `"admin"`.
2. Critical `is_active` **must remain** `true`.
3. Non-critical may drop admin, use `[]`, or set `is_active=false`.

---

## 3. Access Evaluation (Logical)

```text
can_access_feature(feature_key, role):
  role_n = str(role).strip().lower() if role is not None else ""
  if role_n not in VALID_ROLES:          # {"trader", "admin"} only
    return False                         # NEVER clamp unknown → trader
  row = load by feature_key
  if row is None: return False           # fail closed
  if row.is_active is False: return False
  return role_n in row.allowed_roles
```

| Scenario | Result |
| :--- | :--- |
| Active, role in list | Allow |
| Active, role not in list | Deny |
| Inactive, role in list | Deny |
| Missing key | Deny |
| Empty allowed_roles, active | Deny for all roles |
| Unknown role (e.g. `superuser`) | Deny (even if traders allowed) |
| `"Admin"` / `"TRADER"` | Strip+lower → domain match if exact |

**Important**: Do **not** call project `normalize_role()` for feature access if it maps unknowns to `DEFAULT_ROLE` (`trader`). That would accidentally grant access whenever traders are allowed.

**Note**: Admin HTTP APIs for features are gated by **live admin role**, not by `can_access_feature("admin_panel")` (catalog-only clarification).

### Critical rejection behavior

On critical-feature safety violation (HTTP 400): **no** column updates (roles, `is_active`, `description`, `updated_at` stay as before commit attempt).

---

## 4. Existing Entity: User (`users`) — reused

| Context | Predicate |
| :--- | :--- |
| **Admin API caller** | Authenticated AND `is_active` AND `deleted_at IS NULL` AND stored `role = 'admin'` |

No schema changes to `users`.

---

## 5. Existing Entity: Audit Log (`audit_logs`) — reused

### Event type

`admin_feature_permission_change`

### Metadata schema

```json
{
  "actor_user_id": "<uuid>",
  "feature_key": "watchlist",
  "previous_allowed_roles": ["trader", "admin"],
  "new_allowed_roles": ["admin"],
  "previous_is_active": true,
  "new_is_active": true,
  "previous_description": "...",
  "new_description": "..."
}
```

* Minimum required on material change: actor, feature_key, previous/new `allowed_roles`.
* Include is_active/description deltas when those fields changed.
* No-ops and failed mutations do **not** write this event type.

---

## 6. API DTOs (not persisted separately)

### FeaturePermissionResponse

| Field | Type | Required |
| :--- | :--- | :--- |
| `id` | string (UUID) | yes |
| `feature_key` | string | yes |
| `description` | string | yes |
| `allowed_roles` | string[] | yes |
| `is_active` | boolean | yes |
| `created_at` | datetime (ISO-8601) | yes |
| `updated_at` | datetime (ISO-8601) | yes |

### FeatureListResponse

| Field | Type | Required |
| :--- | :--- | :--- |
| `items` | FeaturePermissionResponse[] | yes |

### UpdateFeaturePermissionRequest

| Field | Type | Required | Notes |
| :--- | :--- | :--- | :--- |
| `allowed_roles` | `("trader"\|"admin")[]` | optional* | Full replace when present |
| `is_active` | boolean | optional* | Forbidden `false` on critical |
| `description` | string | optional* | Max 255 |

\* At least one field must be present; else **422**.

---

## 7. Validation Rules Summary

1. `allowed_roles` entries outside `{trader, admin}` (exact lower-case) → **422**.
2. Unknown `feature_key` on PATCH → **404**.
3. Critical feature without `admin` in new roles → **400**.
4. Critical feature `is_active=false` → **400**.
5. Empty PATCH body → **422**.
6. Caller not live admin → **403** (or **401** if unauthenticated).
7. Duplicates collapsed; order forced to trader → admin when both present.
8. Request order `["admin","trader"]` → store/return `["trader","admin"]`.

---

## 8. Relationships

```text
Administrator (User, role=admin, active)
    |-- lists --> FeaturePermission[]
    |-- updates --> FeaturePermission
    |-- writes --> AuditLog (on material permission change)

FeaturePermission
    |-- evaluated by --> can_access_feature(role)   # not wired to routes this sprint
```

No foreign keys from `feature_permissions` to `users`.

---

## 9. Migration Notes

* **Tooling**: `backend/alembic/` + `backend/alembic.ini`
* **Upgrade**: create table + unique constraint; seed 7 rows if absent
* **Downgrade**: drop table `feature_permissions` (historical audit rows may remain)
* Register model in `backend/app/models/__init__.py` for metadata

### SQL sketch (illustrative)

```sql
CREATE TABLE feature_permissions (
    id UUID PRIMARY KEY,
    feature_key VARCHAR(64) NOT NULL,
    description VARCHAR(255) NOT NULL,
    allowed_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_feature_permissions_feature_key UNIQUE (feature_key)
);
```

---

## 10. SQLAlchemy Model Sketch (illustrative)

```python
class FeaturePermission(Base):
    __tablename__ = "feature_permissions"

    id: Mapped[uuid.UUID]
    feature_key: Mapped[str]          # unique
    description: Mapped[str]
    allowed_roles: Mapped[list]       # JSONB
    is_active: Mapped[bool]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

Implementation must follow project conventions in `backend/app/models/auth.py` (UUID, JSONB, `func.now()`, etc.).
