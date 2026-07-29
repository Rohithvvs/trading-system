# Feature Specification: Sprint 2 – Backend Authorization + User Management APIs

**Feature Directory**: `specs/023-admin-user-apis`  
**Feature Branch**: `023-admin-user-apis`  
**Created**: 2026-07-29  
**Status**: Draft (clarified; ready for implementation planning)  
**Target Sprint**: Sprint 2 (Admin Authorization Foundation)  
**Depends On**: Sprint 1 – Role Normalization + JWT + Default Admin (`specs/022-rbac-role-jwt-admin`)  

---

## 1. Overview

Sprint 2 delivers the **server-side administrative APIs** that will power a future Admin Panel. Building on Sprint 1’s normalized roles (`trader` | `admin`), JWT identity foundation, registration hardening, and default admin bootstrap, this sprint enables verified administrators to:

1. Browse a paginated user directory (with optional search and role filter).
2. Promote or demote users within the two-role model.
3. Rely on **last-admin protection** so the platform cannot be left with zero usable administrators.
4. Leave a durable **audit trail** for every real privilege change.

No administrative UI is included. This sprint is strictly **backend authorization enforcement + user-management contracts**.

---

## Clarifications

### Session 2026-07-29

- Q: When counting admins for last-admin protection, which accounts count? → A: Count only **active, non-deleted** users with role `admin`
- Q: How should the system verify that a caller is allowed to perform admin operations? → A: Require **authenticated + active account + current role `admin` in the user store** (not token role claim alone)
- Q: May an administrator change the role of an inactive or soft-deleted user? → A: **No** — reject as not found (no role mutation, no reactivation)
- Q: When an admin sets a user’s role to the same value they already have (no-op)? → A: **Succeed** and return the user; **do not** write a role-change audit entry

---

## 2. Background / Context (Sprint 1)

Sprint 1 established:

| Capability | Status |
| :--- | :--- |
| Roles strictly `trader` \| `admin` | Done |
| JWT claims include `sub`, `role`, `exp` | Done |
| Registration always forces `trader` | Done |
| Default admin bootstrap on startup | Done |
| Stateless `require_admin` foundation in `deps.py` | Done (token-claim based) |
| Frontend AuthContext carries `user.role` | Done |

**Gap this sprint closes**: There are no admin-facing user-management operations. Operators cannot list users or change roles without direct database access. The existing token-based `require_admin` is not sufficient alone for privilege-sensitive admin mutations (a demoted admin’s JWT may still claim `admin` until expiry).

---

## 3. Business Objective

1. **Controlled privilege management** — only live administrators may list users or change roles.
2. **Operational safety** — never leave zero **active, non-deleted** admins via demotion (including self-demotion).
3. **Accountability** — every actual role change is audited (actor, target, from → to).
4. **Admin Panel readiness** — stable HTTP contracts and error semantics for a future UI sprint.

---

## 4. Scope

### In Scope

- Harden admin authorization for user-management routes using **live user store** role checks.
- `GET /admin/users` — paginated list with optional search and role filter.
- `PATCH /admin/users/{user_id}/role` — change role to `trader` or `admin`.
- Last-admin protection (self and other; active non-deleted admins only).
- Audit logging of real role changes via existing `AuditService`.
- Comprehensive automated tests (authz, success, safety, audit, regression).

### Out of Scope (Explicitly Deferred)

- Any frontend / Admin Panel UI.
- Feature permission matrices beyond the two roles.
- User create/delete/deactivate product APIs.
- Soft-delete product flows or complex user CRUD.
- Session mass-revocation on demotion (live role re-check is sufficient for admin APIs this sprint).
- Changes to trading, scanner, paper-trading, or portfolio business logic.
- Bulk role changes or scheduled privilege reviews.

---

## 5. Functional Requirements

### Authorization Gate

- **FR-001**: Administrative user-management operations MUST be allowed only when the caller is authenticated, the account is **active and not soft-deleted**, and the **current stored role** is `admin`.
- **FR-002**: Unauthenticated callers MUST receive **HTTP 401**.
- **FR-003**: Authenticated callers whose live stored role is not `admin` (including traders and recently demoted former admins) MUST receive **HTTP 403**.
- **FR-004**: Admin authorization MUST resolve identity from the existing Sprint 1 session (Bearer token or HttpOnly cookie), then **re-load the user row** and verify `is_active`, non-deleted, and `role == "admin"`. Token/session role claims alone MUST NOT authorize these operations.
- **FR-005**: A production-ready dependency (e.g. `get_current_admin_user`) MUST encapsulate FR-001–FR-004 for reuse on all admin user-management routes. Stateless JWT-only `require_admin` MAY remain for non-mutating or future low-risk gates but MUST NOT be the sole gate for these admin APIs.

### User Directory (List)

- **FR-006**: Administrators MUST be able to retrieve a paginated list of users via `GET /admin/users`.
- **FR-007**: Each list item MUST include: `id`, `email`, `full_name`, `role`, `is_active`, `created_at`.
- **FR-008**: Pagination MUST support `page` (default **1**, minimum 1) and `size` (default **20**, maximum **100**). Response MUST include `items`, `total`, `page`, `size`.
- **FR-009**: Optional `search` query MUST match users by partial, case-insensitive email **or** full name.
- **FR-010**: Optional `role` query MUST filter to `trader` or `admin` only; invalid role filter values MUST yield **HTTP 422**.
- **FR-011**: Default directory MUST include only **active, non-deleted** users.

### Role Change

- **FR-012**: Administrators MUST be able to change a user’s role via `PATCH /admin/users/{user_id}/role` with body `{ "role": "trader" | "admin" }`.
- **FR-013**: Invalid role values MUST yield **HTTP 422**.
- **FR-014**: Non-existent user ids MUST yield **HTTP 404**.
- **FR-015**: Inactive or soft-deleted targets MUST yield **HTTP 404** (same as missing). Role MUST NOT be mutated; account MUST NOT be reactivated.
- **FR-016**: Successful role change MUST return the updated user representation (same fields as directory items).
- **FR-017**: If requested role equals current role (no-op), the system MUST return **HTTP 200** with the unchanged user and MUST NOT write a role-change audit entry.

### Last-Admin Protection

- **FR-018**: The system MUST refuse any demotion from `admin` → `trader` that would leave zero **active, non-deleted** users with role `admin`.
- **FR-019**: Protection MUST apply when the target is another user **and** when the target is the calling administrator (self-demotion).
- **FR-020**: Inactive or soft-deleted rows with role `admin` MUST NOT count as surviving administrators.
- **FR-021**: When protection triggers, the target role MUST remain unchanged and the API MUST return **HTTP 400** with a clear message (distinct from 401/403/404/422).
- **FR-022**: Admin count used for protection MUST be re-validated at write time (or under equivalent transactional safety) so concurrent demotions cannot leave zero active admins.

### Audit Logging

- **FR-023**: On every successful role change where previous role ≠ new role, the system MUST write an audit log entry via existing `AuditService`.
- **FR-024**: Audit metadata MUST capture at least: actor user id, target user id, previous role, new role, and event type (e.g. `admin_role_change`).
- **FR-025**: Failed mutations (401/403/404/400/422) and pure no-ops MUST NOT create a successful role-change audit entry.

### Non-Regression

- **FR-026**: Sprint 1 auth flows (register force-trader, login/me role, default admin bootstrap, JWT claims) MUST continue to pass.
- **FR-027**: Administrative operations MUST NOT modify trading, scanner, or paper-trading business behavior.

---

## 6. Non-Functional Requirements

### Security

- **NFR-001**: Admin user-management authorization MUST use live store role (defense against stale JWT role claims after demotion).
- **NFR-002**: Admin list endpoints expose PII (email, name); access MUST be admin-only with no public or trader access.
- **NFR-003**: Role assignment remains system-owned; clients cannot elevate themselves via registration or non-admin routes (Sprint 1 preserved).

### Reliability & Safety

- **NFR-004**: Last-admin protection MUST be enforced server-side for every demotion path; no client-trusted bypass.
- **NFR-005**: Concurrent demotion races MUST not produce zero active admins (re-check count under write path).

### Performance

- **NFR-006**: User list queries MUST use pagination (max page size 100) to bound response size.
- **NFR-007**: Admin gate DB load is one user read per request (acceptable for low-volume admin traffic).

### Maintainability

- **NFR-008**: Business logic for listing and role change MUST live in a dedicated service module (`admin_user_service`), not fat route handlers.
- **NFR-009**: Role constants MUST reuse Sprint 1 `UserRole` / `VALID_ROLES` (no new magic strings).

### Observability

- **NFR-010**: Role-change audits MUST be queryable via existing audit log storage for incident review.
- **NFR-011**: Last-admin rejection SHOULD log at warning level with actor and target ids (no secrets).

### Compatibility

- **NFR-012**: No frontend changes required; existing SPA auth continues to work.
- **NFR-013**: No database schema migration required if Sprint 1 user columns already provide role, is_active, deleted_at, created_at.

---

## 7. Safety Rules (Last-Admin Protection)

```
Before applying admin → trader demotion:
  1. Load target (must be active, non-deleted) else 404
  2. If target.role != admin: apply/no-op as appropriate (not a demotion)
  3. Count active non-deleted users WHERE role = 'admin'
  4. If count == 1 AND target is that admin:
        REJECT with HTTP 400 (last admin)
  5. Else apply demotion, commit, audit
```

Rules:

1. **Last active admin cannot be demoted** (by self or by another admin).
2. **Inactive/deleted admins do not count** toward “at least one admin remains.”
3. **Promotion** (`trader` → `admin`) is never blocked by last-admin rules.
4. **No-op** same-role updates do not engage demotion protection.

---

## 8. API Contracts Summary

| Method | Path | Auth | Success | Key Errors |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/admin/users` | Admin (live) | 200 + paginated list | 401, 403, 422 |
| `PATCH` | `/admin/users/{user_id}/role` | Admin (live) | 200 + user | 401, 403, 404, 400, 422 |

Full request/response schemas: [contracts/admin-api.md](./contracts/admin-api.md).

### Error Status Semantics

| Status | Meaning |
| :--- | :--- |
| **401** | Not authenticated / invalid token |
| **403** | Authenticated but not a live admin (or inactive) |
| **404** | User not found, inactive, or soft-deleted (role change target) |
| **400** | Last-admin protection (or other business rule client error) |
| **422** | Validation failure (invalid role, bad page/size, bad UUID) |

---

## 9. User Scenarios & Testing

### User Story 1 – Admin Access Control (P1)

**Independent Test**: List users as admin (200), trader (403), unauthenticated (401).

1. **Given** admin session, **When** `GET /admin/users`, **Then** 200 with paginated directory.
2. **Given** trader session, **When** `GET /admin/users`, **Then** 403.
3. **Given** no auth, **When** `GET /admin/users`, **Then** 401.
4. **Given** JWT still claims admin but live role is trader, **When** any admin API, **Then** 403.

### User Story 2 – Browse & Filter Directory (P1)

1. Default list returns `items`, `total`, `page`, `size` for active non-deleted users.
2. `search` matches partial email or full name (case-insensitive).
3. `role=admin|trader` filters correctly; invalid role filter → 422.
4. Inactive/soft-deleted users excluded from default list.

### User Story 3 – Promote / Demote (P1)

1. Promote trader → admin → 200, role admin, audit written.
2. Demote non-last admin → trader → 200, role trader, audit written.
3. Missing user → 404.
4. Inactive/soft-deleted target → 404, no mutation.
5. Invalid role → 422.
6. Trader caller → 403.
7. Same-role no-op → 200, no audit.

### User Story 4 – Last-Admin Protection (P1)

1. Sole active admin demotion (self or other) → 400, role unchanged.
2. Two+ active admins → demotion allowed.
3. Only inactive admin rows remain as “other admins” → demotion of last active admin still → 400.

### User Story 5 – Audit Trail (P2)

1. Real role change → audit with actor, target, previous_role, new_role, event_type.
2. Failed change / no-op → no success role-change audit.

### Edge Cases

- Concurrent dual demotion when two admins exist: at most one succeeds if the other would leave zero.
- `page < 1` or `size > 100` or `size < 1` → 422.
- Empty `search` → treated as no search filter.
- Sprint 1 register/login/me/bootstrap remain green.

---

## 10. Key Entities

- **User Account**: id, email, full_name, role, is_active, deleted_at, created_at.
- **Administrator Principal**: authenticated active user with live `role=admin`.
- **User Directory Page**: items + total + page + size.
- **Role Change Request**: target user id + desired role.
- **Audit Event (Role Change)**: actor, target, previous_role, new_role, event_type, timestamp.

---

## 11. Acceptance Criteria

### Authorization

- [ ] **AC-AUTH-01**: Unauthenticated `GET /admin/users` → 401.
- [ ] **AC-AUTH-02**: Trader `GET /admin/users` → 403.
- [ ] **AC-AUTH-03**: Admin `GET /admin/users` → 200.
- [ ] **AC-AUTH-04**: Demoted user with stale admin JWT → 403 on admin APIs.
- [ ] **AC-AUTH-05**: Unauthenticated / trader `PATCH .../role` → 401 / 403 respectively.

### List Users

- [ ] **AC-LIST-01**: Default page=1, size=20; response has items/total/page/size.
- [ ] **AC-LIST-02**: size max 100 enforced (size=101 → 422).
- [ ] **AC-LIST-03**: search matches email or full_name (case-insensitive partial).
- [ ] **AC-LIST-04**: role filter works for trader and admin.
- [ ] **AC-LIST-05**: Inactive/soft-deleted users excluded from default list.
- [ ] **AC-LIST-06**: Each item includes id, email, full_name, role, is_active, created_at.

### Role Change

- [ ] **AC-ROLE-01**: Promote trader → admin succeeds; response role=admin.
- [ ] **AC-ROLE-02**: Demote non-last admin → trader succeeds.
- [ ] **AC-ROLE-03**: Invalid role body → 422.
- [ ] **AC-ROLE-04**: Unknown user id → 404.
- [ ] **AC-ROLE-05**: Inactive/soft-deleted target → 404; role unchanged.
- [ ] **AC-ROLE-06**: Same-role no-op → 200; no audit row for role change.

### Last Admin

- [ ] **AC-LAST-01**: Demote sole active admin (as other/self) → 400; role remains admin.
- [ ] **AC-LAST-02**: With 2+ active admins, demotion succeeds.
- [ ] **AC-LAST-03**: Inactive admin does not allow demoting the last active admin.

### Audit

- [ ] **AC-AUD-01**: Real role change creates audit with actor, target, previous_role, new_role.
- [ ] **AC-AUD-02**: Failed last-admin demotion creates no success role-change audit.

### Regression

- [ ] **AC-REG-01**: Sprint 1 auth comprehensive suite still passes.

---

## 12. Success Criteria

- **SC-001**: 100% of unauthenticated admin API calls → 401 in tests.
- **SC-002**: 100% of non-admin (including stale-token-after-demotion) calls → 403 in tests.
- **SC-003**: Admins can list users with pagination/search/role filter; required fields present.
- **SC-004**: Promote and non-last demote succeed with updated role in response.
- **SC-005**: 100% of last-active-admin demotion attempts fail with 400; role intact.
- **SC-006**: 100% of real role changes produce audit entries; no-ops produce none.
- **SC-007**: Invalid role → 422; missing/inactive target → 404; last-admin → 400.
- **SC-008**: Sprint 1 auth regression suite remains green.

---

## 13. Assumptions

- Sprint 1 binary role model and user table columns remain authoritative.
- Soft-delete is represented by `deleted_at IS NOT NULL` (or equivalent already on `User`).
- Search is case-insensitive partial match on email and full_name.
- Session revocation on demotion is out of scope; live role re-check covers admin API safety.
- Existing `AuditService.log_event` is the audit sink.
- Router mount prefix `/admin` under the existing API router (same style as `/auth`).

---

## 14. Dependencies

- Sprint 1 complete (`022-rbac-role-jwt-admin`).
- `User` model, `get_current_user` / `get_current_active_user`, `UserRole`, `AuditService`.
- Test harness patterns from Sprint 1 (`TestClient`, async DB fixtures).

---

## 15. Risks

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| Last active admin demoted | Critical lockout | FR-018–022 + tests AC-LAST-* |
| Stale JWT admin claim after demotion | High privilege leakage | Live store admin gate (FR-004) |
| Trader enumerates user PII | High | 403 on all `/admin/*` for non-admins |
| Concurrent dual demotion | High | Re-count active admins at write time |
| Scope creep into UI/CRUD | Medium | Strict out-of-scope boundary |

---

## 16. Sprint Summary

| Component | Mandate |
| :--- | :--- |
| **Admin gate** | Live active user with stored role `admin` |
| **GET /admin/users** | Paginated, searchable, role-filterable directory |
| **PATCH .../role** | Promote/demote with validation |
| **Last-admin** | Cannot demote last active non-deleted admin (self/other) |
| **Audit** | Real role changes only |
| **Frontend** | No changes this sprint |
