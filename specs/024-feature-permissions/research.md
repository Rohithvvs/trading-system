# Phase 0 Research: Sprint 3 – Feature Permissions System

All technical unknowns from planning are resolved below. Clarification session 2026-07-30 is authoritative where it intersects design choices.

---

## Research Topic 1: Storage for `allowed_roles` (JSONB vs ARRAY)

### Decision
Store `allowed_roles` as **JSONB** containing a JSON array of strings (e.g. `["trader","admin"]`).

### Rationale
* Project already uses JSONB extensively (`AuditLog.metadata`, preferences, experiment metadata).
* Full replace on PATCH is simple and atomic at the column level.
* Easy to serialize to Pydantic `list[str]` without portable ARRAY dialect shims.
* Sufficient for membership checks in Python (`role in allowed_roles`).

### Alternatives Considered
* **PostgreSQL `TEXT[]`**: Good for `= ANY(...)` SQL; more ceremony for tests / portable types.
* **Normalized join table**: Overkill for two roles and full-list replace semantics.
* **Bitmask flags**: Opaque; hard to extend without migrations.

---

## Research Topic 2: Admin Authorization Gate

### Decision
Reuse Sprint 2 **`get_current_admin_user`** (live DB role) for all feature-permission admin routes.

### Rationale
Privilege-sensitive catalog mutations must not honor stale JWT `role: admin` after demotion. Consistency with user-management APIs reduces cognitive load and test matrix duplication.

### Alternatives Considered
* **JWT-only `require_admin`**: *Rejected* for these routes — demotion gap.
* **New permission-specific gate**: Unnecessary indirection.

---

## Research Topic 3: Critical Feature Safety (Last-Admin Analogy)

### Decision
**Minimal critical set** (clarified): only `admin_panel` and `user_management`.
* `allowed_roles` must always include `"admin"`.
* `is_active` cannot be set to `false`.
Reject with **HTTP 400**.

### Rationale
Prevents operational lockout of the console and user-management surfaces once the Admin UI exists, without over-constraining ops features (`system_logs`, `export_data`) that admins may intentionally restrict.

### Alternatives Considered
* **Expand critical set** to all admin-default seeds: *Rejected* (clarification chose minimal).
* **HTTP 409**: Viable; prefer **400** to align with Sprint 2 business-rule style.

---

## Research Topic 4: Fail Closed vs Fail Open for Missing Features

### Decision
`can_access_feature` returns **`false`** when the feature key is missing or inactive.

### Rationale
Security default: unknown or disabled features must not grant access. New product surfaces must add a seed row before relying on the helper.

### Alternatives Considered
* **Fail open**: Unsafe for production permissions.
* **Raise on missing**: Useful for misconfiguration detection; helper contract remains bool for simple guards (may log warning).

---

## Research Topic 4b: Helper Role Resolution vs `normalize_role` (post-analyze)

### Decision
For feature access, resolve role as strip+lower exact membership in `VALID_ROLES` only. **Do not** call `normalize_role()` for access checks when that function clamps unknown values to `trader`/`DEFAULT_ROLE`.

### Rationale
Post-analyze finding I1: clamping `"superuser"` → `"trader"` would grant access whenever traders are allowed—fails closed incorrectly. Admin PATCH validation remains strict exact lower-case (422); helper is separate read-side path.

### Alternatives Considered
* **Reuse `normalize_role` as-is**: *Rejected* — unsafe for feature grants.
* **Change global `normalize_role`**: Out of scope; would alter Sprint 1 JWT/registration behavior.

---

## Research Topic 5: Empty `allowed_roles`

### Decision
Allow `[]` for **non-critical** features only. Semantics: no role may access while the row is active.

### Rationale
Gives admins a way to turn off a feature for everyone without deleting the catalog key (keys stay stable for UI).

### Alternatives Considered
* **Disallow empty**: Forces `is_active` only; less flexible.
* **Null column**: *Rejected* — prefer explicit empty list.

---

## Research Topic 6: Seed Idempotency

### Decision
Seed with **insert-if-not-exists** by `feature_key`. Do not overwrite existing `allowed_roles` / `is_active` / `description` on re-run.

### Rationale
Operators customize roles after deploy. Re-running migrations must not reset production configuration.

### Alternatives Considered
* **Upsert always to defaults**: *Rejected* — destroys runtime configuration.

---

## Research Topic 7: List Response Shape

### Decision
Return `{ "items": [ ... ] }` ordered by `feature_key` ascending. Include active and inactive rows. No pagination in v1.

### Rationale
Matches Sprint 2 list envelope style; catalog size is tiny; evolvable without breaking bare-array clients.

---

## Research Topic 8: Role Validation Strictness & Canonical Order

### Decision
* PATCH accepts only exact lower-case `"trader"` and `"admin"` → else **422**.
* After dedupe, store/return in **role priority order**: `trader` then `admin` when both present (clarified).

### Rationale
Predictable API and tests. Silent `normalize_role` on writes could map unknown values to `trader` and accidentally grant access.

### Alternatives Considered
* **Lexicographic sort**: Would put `admin` first; rejected in favor of priority order.
* **Preserve request order**: Non-deterministic for clients/tests.

---

## Research Topic 9: Scope of Enforcement & Discovery

### Decision (clarified)
* **Catalog only**: do not wire helper onto existing admin/product routes.
* **No** non-admin discovery endpoint (`GET /me/features` deferred).
* **`can_access_feature` required**; **`require_feature` optional / not DoD**.

### Rationale
Unblocks Admin UI data contract without risking trading/scanner or Sprint 2 regressions. Helper is ready for Sprint 4–5 opt-in.

### Alternatives Considered
* Wire `user_management` onto Sprint 2 routes: deferred by clarification.
* Ship `require_feature` as required: not needed until routes consume it.

---

## Research Topic 10: Route Module Placement

### Decision
Extend existing `backend/app/routes/admin.py` under prefix `/admin` (already registered in `routes/__init__.py`).

### Rationale
Single Admin OpenAPI tag/surface; zero new mount points; mirrors Sprint 2 pattern.

### Alternatives Considered
* New `routes/feature_permissions.py`: Acceptable if `admin.py` grows large; still must mount under `/admin`.

---

## Research Topic 11: Migration Tooling Path

### Decision
Use project Alembic at `backend/alembic/` (`backend/alembic.ini`), not a fictional `app/db/migrations` path.

### Rationale
Matches repository layout discovered during planning.

---

## Research Topic 12: Audit Event Shape

### Decision
Event type `admin_feature_permission_change` via existing `AuditService.log_event`, with metadata including actor, feature_key, previous/new `allowed_roles`, and is_active when relevant. Skip on no-op and failures.

### Rationale
Consistent with Sprint 2 `admin_role_change` pattern; queryable in existing `audit_logs`.

---

## Resolved NEEDS CLARIFICATION

None remaining. All Technical Context items are specified; clarification session closed five open product decisions.
