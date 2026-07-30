# UI Contracts: Admin Panel (Sprint 4)

**App route**: `/admin`  
**Auth**: Existing SPA session (AuthContext + API credentials)  
**Client gate**: `user.role === "admin"`  
**Server gate**: Backend live admin (Sprint 2/3) — authoritative  

**Clarifications applied**: unified admin role on logs/command; features roles-only; users search; URL tab sync; developer mode never unlocks `/admin/*`.

---

## 1. Navigation

| Role | Admin / logs / command nav | Deep link `/admin*` |
| :--- | :--- | :--- |
| Unauthenticated | Hidden | → Login |
| `trader` | Hidden | Forbidden (no admin data) |
| `admin` | Visible | Admin Panel / logs / command |

Developer mode **must not** reveal or unlock these destinations.

---

## 2. Screen: Forbidden (authenticated non-admin)

| Element | Content |
| :--- | :--- |
| Title | Admin access required |
| Body | You need an administrator role to open this page. |
| Primary action | Back to Scanner |

Applies to `/admin`, `/admin/logs`, `/admin/command`.

---

## 3. Screen: Admin Panel Shell

| Element | Spec |
| :--- | :--- |
| Path | `/admin` |
| Title | Admin |
| Subtitle | Manage users and feature visibility |
| Tabs | **Users** \| **Features** (exactly two) |
| Default tab | Users |
| URL | **Required**: `?tab=users` \| `?tab=features`; invalid/missing → Users |

---

## 4. Users Tab

### Data source

`GET /admin/users?page={page}&size={size}&search={optional}`

- UI **must** provide search (blank = no filter).  
- Role filter **not** required.

### Defaults

| Param | Default |
| :--- | :--- |
| page | 1 |
| size | 20 (max 100) |

### Table columns

| Column | Field |
| :--- | :--- |
| Email | `email` |
| Name | `full_name` |
| Role | `role` (badge) |
| Active | `is_active` |
| Created | `created_at` |
| Actions | Change role |

### Role change flow

1. Select new role ≠ current.  
2. Modal: “Change {email} to {role}?” Confirm / Cancel.  
3. `PATCH /admin/users/{id}/role` `{ "role": "..." }`.  

| HTTP | UI |
| :--- | :--- |
| 200 | Update row; success toast |
| 400 | Show `detail` (last-admin); role unchanged |
| 401 | Session expired messaging |
| 403 | Not authorized |
| 422/5xx | Error; role unchanged |

### States

Loading skeleton/spinner · Empty “No users found” · Error + retry  

---

## 5. Features Tab

### Data source

`GET /admin/features` → `{ items: FeaturePermission[] }`

### Row fields

| UI | Field | Editable |
| :--- | :--- | :---: |
| Key | `feature_key` | No |
| Description | `description` | No |
| Active | `is_active` | **No** (read-only) |
| Roles | Trader / Admin checkboxes | **Yes** |
| Action | Save | — |

### Save flow

`PATCH /admin/features/{feature_key}`  

Body **only**:

```json
{ "allowed_roles": ["trader", "admin"] }
```

| HTTP | UI |
| :--- | :--- |
| 200 | Replace roles from response; success toast |
| 400 | Critical safety message; revert to last server roles |
| 404/422/401/403 | Error messaging |

### Critical features

Keys `admin_panel`, `user_management`: **Admin** checkbox disabled (always on).

---

## 6. Component Inventory

| Component | Responsibility |
| :--- | :--- |
| `AdminRoute` | `role === admin` for panel/logs/command |
| `AdminPanelPage` | Shell + tabs + URL sync |
| `UsersAdminTab` | Users list, search, pagination, role change |
| `FeaturesAdminTab` | Features list, roles edit, save |
| `RoleChangeModal` | Confirm role change |
| `api_admin.ts` | HTTP helpers |

---

## 7. Non-goals (UI)

- FeatureGuard on retail pages  
- User create/delete  
- Feature key create/delete  
- Editing `is_active` / description from Features tab  
- Audit log viewer  
