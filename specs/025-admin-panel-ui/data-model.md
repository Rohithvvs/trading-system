# Phase 1 Data Model (Frontend): Sprint 4 – Admin Panel UI

Sprint 4 persists **no new backend tables**. This document describes **API-facing DTOs** and **UI state** models.

---

## 1. Auth Principal (existing)

From AuthContext / `useAuth`:

| Field | Type | Notes |
| :--- | :--- | :--- |
| `id` | string | User id |
| `email` | string | |
| `full_name` | string | |
| `role` | `"trader"` \| `"admin"` | Gate for AdminRoute |

**Admin access predicate**: authenticated ∧ `role === "admin"`.

---

## 2. Admin User Row (Sprint 2 API)

| Field | Type | UI |
| :--- | :--- | :--- |
| `id` | string (UUID) | Role change target |
| `email` | string | Display + search |
| `full_name` | string | Display + search |
| `role` | `"trader"` \| `"admin"` | Badge + change action |
| `is_active` | boolean | Display |
| `created_at` | ISO datetime | Display |

### List response

| Field | Type |
| :--- | :--- |
| `items` | AdminUser[] |
| `total` | number |
| `page` | number |
| `size` | number |

### Role change request

```json
{ "role": "trader" | "admin" }
```

---

## 3. Feature Permission Row (Sprint 3 API)

| Field | Type | UI |
| :--- | :--- | :--- |
| `id` | string (UUID) | Internal |
| `feature_key` | string | Display (code style) |
| `description` | string | Display |
| `allowed_roles` | `("trader"\|"admin")[]` | **Editable** |
| `is_active` | boolean | **Read-only** |
| `created_at` / `updated_at` | ISO datetime | Optional display |

### List response

```json
{ "items": [ /* FeaturePermission */ ] }
```

### Feature update request (this UI)

```json
{ "allowed_roles": ["trader", "admin"] }
```

**Must not send** `is_active` or `description` from Features tab in Sprint 4.

### Critical keys (UI constraints)

```text
CRITICAL_FEATURE_KEYS = { "admin_panel", "user_management" }
```

Admin checkbox disabled (must remain checked) for critical keys.

---

## 4. UI State Models (client-only)

### AdminPanelPage

| State | Type | Notes |
| :--- | :--- | :--- |
| `tab` | `"users"` \| `"features"` | Synced to `?tab=` |

### UsersAdminTab

| State | Type | Notes |
| :--- | :--- | :--- |
| `items` | AdminUser[] | From API |
| `total`, `page`, `size` | number | Pagination; default page=1, size=20 |
| `search` | string | Debounced → API `search` |
| `loading` | boolean | |
| `error` | string \| null | |
| `pendingUserId` | string \| null | Disable double-submit |
| `confirmTarget` | { user, nextRole } \| null | Modal |

### FeaturesAdminTab

| State | Type | Notes |
| :--- | :--- | :--- |
| `items` | FeaturePermission[] | Server truth |
| `draftRoles` | Record<feature_key, string[]> | Per-row edits before Save |
| `savingKey` | string \| null | |
| `loading` / `error` | | |

**Dirty detection**: draft ≠ server `allowed_roles` (order-insensitive compare after normalize).

---

## 5. Validation Rules (client)

1. Role change only to `trader` \| `admin`.  
2. Confirm before PATCH role.  
3. Feature Save sends unique roles subset of domain; critical must include `admin` in draft.  
4. Search empty → omit or empty filter.  
5. Tab query only `users` \| `features`.

---

## 6. Relationships

```text
AuthUser (admin)
  ├── opens AdminPanelPage
  ├── UsersAdminTab ──HTTP──► /admin/users
  └── FeaturesAdminTab ──HTTP──► /admin/features
```

No local DB.
