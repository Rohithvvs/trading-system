# Phase 0 Research: Sprint 2 – Backend Authorization + User Management APIs

## Research Topic 1: Admin Authorization — JWT Claim vs Live Store Role

### Decision
Authorize admin user-management APIs with **`get_current_admin_user`**: resolve session identity (Bearer/cookie JWT), load the `User` row, require `is_active`, not soft-deleted, and **stored `role == "admin"`**. Do not authorize these routes with JWT `role` claim alone.

### Rationale
After demotion, a previously issued access token may still contain `"role": "admin"` until expiry. Privilege-sensitive operations (list all users, change roles) must reflect **current** authority. Clarification session explicitly selected live-store admin verification.

### Alternatives Considered
* **Stateless `require_admin` (JWT only)**: *Rejected for these APIs* — demoted admins retain access until token expiry.
* **Hybrid (JWT must claim admin AND DB confirms)**: Acceptable equivalent; slightly more brittle if token missing role claim after refresh. Live DB role after authenticated identity is sufficient and simpler.
* **Always revoke all sessions on demotion**: Strong but expands scope (session table bulk updates); deferred. Live check covers admin API surface this sprint.

---

## Research Topic 2: Last-Admin Counting Population

### Decision
Count only users where `role = 'admin'` AND `is_active = true` AND `deleted_at IS NULL`.

### Rationale
Protection exists to preserve **usable** administrative access. Counting inactive/deleted admins would allow demoting the last working admin while a disabled row still “counts.” Clarification session selected active non-deleted only.

### Alternatives Considered
* **Count all rows with role=admin**: *Rejected* — operational lockout risk.
* **Count active only but include soft-deleted**: *Rejected* — soft-deleted accounts are not operational.

---

## Research Topic 3: Role Change Target Eligibility

### Decision
Role change targets must be **active and non-deleted**. Otherwise return **HTTP 404** (same as missing). Do not mutate role or reactivate.

### Rationale
Aligns directory visibility with mutability. Prevents silent privilege edits on accounts excluded from the default admin directory. Clarification session selected not-found behavior.

### Alternatives Considered
* **Allow role change on inactive users without reactivation**: *Rejected* — surprising; splits eligibility rules.
* **403 for inactive targets**: *Rejected* — implies existence disclosure with different semantics; 404 matches “not in operable set.”

---

## Research Topic 4: No-Op Role Updates and Audit Noise

### Decision
If requested role equals current role → **HTTP 200** with current user; **no** `admin_role_change` audit entry.

### Rationale
Idempotent admin clients (and future UI retries) should not fail or flood audit logs. Spec SC-006 and clarification session: audit only real privilege changes.

### Alternatives Considered
* **Audit every request including no-ops**: *Rejected* — audit noise.
* **400 if role unchanged**: *Rejected* — poor UX for idempotent PATCH.

---

## Research Topic 5: HTTP Status Mapping

### Decision
| Condition | Status |
| :--- | :--- |
| Missing/invalid auth | 401 |
| Authenticated non-admin / inactive principal | 403 |
| Target missing / inactive / soft-deleted | 404 |
| Last-admin demotion blocked | 400 |
| Invalid role / bad pagination / invalid UUID format | 422 |

### Rationale
Matches user-provided Sprint 2 requirements and common REST admin API practice. Distinguishes authn, authz, missing resource, business rule, and validation.

### Alternatives Considered
* **409 Conflict for last-admin**: Viable; *rejected* in favor of explicit product requirement for **400**.
* **403 for last-admin**: *Rejected* — caller is authorized; rule is business constraint.

---

## Research Topic 6: Pagination and Search Defaults

### Decision
* `page` default 1, minimum 1  
* `size` default 20, minimum 1, maximum 100  
* `search`: case-insensitive partial match on `email` OR `full_name`  
* Default sort: `created_at DESC` (stable, predictable for admin UIs)  
* Empty/whitespace search: ignore filter  

### Rationale
Industry-standard admin directory defaults; bounds payload size; no product requirement for custom sort this sprint.

### Alternatives Considered
* **Cursor pagination**: Better at huge scale; unnecessary for current user volume.
* **Exact-match search only**: *Rejected* — weaker admin UX.

---

## Research Topic 7: Schema / Migration Need

### Decision
**No Alembic migration** for Sprint 2 unless implementation finds missing indexes. Reuse existing `users` columns from Sprint 1.

### Rationale
Role CHECK, defaults, is_active, deleted_at, created_at already present. Feature is API + service + authz only.

### Alternatives Considered
* **Partial index on (role) WHERE active**: Optional optimization; defer until measured need.
