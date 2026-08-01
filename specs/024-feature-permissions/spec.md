# Feature Specification: Sprint 3 – Feature Permissions System

**Feature Directory**: `specs/024-feature-permissions`  
**Feature Branch**: `024-feature-permissions`  
**Created**: 2026-07-30  
**Status**: Implemented (Sprint 3 backend complete)  
**Target Sprint**: Sprint 3 (Feature Permissions Backend)  
**Depends On**:
- Sprint 1 – Role Normalization + JWT + Default Admin (`specs/022-rbac-role-jwt-admin`)
- Sprint 2 – Admin User Management APIs (`specs/023-admin-user-apis`)

---

## Clarifications

### Session 2026-07-30

- Q: Should Sprint 3 enforce seeded feature keys on existing admin/product HTTP routes, or only deliver the store + admin feature APIs + helper? → A: **Catalog only** — admin list/update + `can_access_feature` helper; existing `/admin/users` and product routes remain role-gated only (no feature-key enforcement wiring this sprint)
- Q: Should this sprint expose any non-admin way for a logged-in user to learn which features their role may access? → A: **Defer** — no non-admin feature discovery API; only admin `GET /admin/features`
- Q: Is a FastAPI `require_feature(feature_key)` dependency factory required this sprint, or only `can_access_feature`? → A: **Helper only required** — `can_access_feature` is mandatory; `require_feature` is optional/nice-to-have (not blocking DoD)
- Q: Which feature keys must be treated as critical (always keep admin; cannot deactivate)? → A: **Minimal** — only `admin_panel` and `user_management`
- Q: When storing and returning `allowed_roles`, what is the canonical order after normalization? → A: **Role priority order** — `trader` then `admin` when both present; single-role lists unchanged

### Session 2026-07-30 (post-analyze remediation)

- Q: How should `can_access_feature` treat invalid/unknown role strings given `normalize_role` clamps unknowns to `trader`? → A: **Deny without clamping** — only exact domain roles (`trader`|`admin` after strip+lower) may match `allowed_roles`; never map garbage roles to `trader` for feature access
- Q: Critical PATCH with mixed fields (e.g. bad roles + new description)? → A: **Reject entire update** (400); no field mutations including description
- Q: Must inactive features appear on admin list? → A: **Yes** — confirmed AC-LIST-05; tests must cover deactivate then re-list

---

## 1. Overview

Sprint 3 delivers a **database-driven Feature Permissions system** that lets administrators control which application features are visible or accessible to each role (`trader` | `admin`) **at runtime**, without code deploys.

This is the backend foundation for the future Admin Panel’s second tab (“Feature Visibility”). Rules are stored as simple feature → allowed roles mappings. The product stays deliberately simple: no permission hierarchies, no multi-tenant policy engines, and no frontend work in this sprint.

---

## 2. Background / Context

| Sprint | Capability | Status |
| :--- | :--- | :--- |
| Sprint 1 | Roles strictly `trader` \| `admin`; JWT includes role; default admin bootstrap | Done |
| Sprint 2 | `get_current_admin_user`; list users; change role; last-admin protection; audit | Done |
| Sprint 3 | Feature permission store + admin APIs + access helper | **This sprint** |
| Sprint 4 | Admin Panel UI (Feature Visibility tab) | Deferred |
| Sprint 5 | Frontend FeatureGuard / route-level visibility | Deferred |

**Gap this sprint closes**: Feature visibility is either hard-coded or absent. Operators cannot grant or revoke access to product areas (e.g. watchlist, advanced scanner, export) without engineering changes. Admin APIs exist for users but not for feature rules.

---

## 3. Business Objective

1. **Runtime control** — administrators change which roles may use a feature without deploying new code.
2. **Simple mental model** — each feature has a stable key and a list of allowed roles.
3. **Safe administration** — critical admin capabilities cannot be accidentally locked out for all administrators.
4. **Accountability** — real permission changes leave an audit trail.
5. **UI readiness** — stable HTTP contracts and a reusable backend helper for Sprint 4–5.

---

## 4. Scope

### In Scope

- New `feature_permissions` table and Alembic migration.
- Seed of **at least 7** default features with sensible default `allowed_roles`.
- Admin-only APIs:
  - `GET /admin/features` — list all feature permissions.
  - `PATCH /admin/features/{feature_key}` — update `allowed_roles` (and optionally `is_active` / `description` if exposed).
- Backend helper: **required** `can_access_feature(feature_key, role) -> bool`. FastAPI `require_feature(...)` dependency is **optional** (not DoD).
- Validation, safety rules (critical features), audit logging.
- Comprehensive automated tests + Sprint 1/2 regression green.

### Out of Scope (Explicitly Deferred)

- Admin Panel UI / Feature Visibility tab (Sprint 4).
- Frontend `FeatureGuard` component or route guards (Sprint 5).
- Changing trading, scanner, paper-trading, or portfolio **business** logic to enforce features.
- Wiring `can_access_feature` / `require_feature` onto existing admin or product HTTP routes (including Sprint 2 `/admin/users`); those routes remain **role-gated only** this sprint. Catalog + helper only.
- Non-admin feature discovery endpoints (e.g. `GET /me/features` or any authenticated trader-readable feature catalog).
- Creating / deleting feature definitions via public API (seed + migration only; keys are system-owned).
- Complex multi-role hierarchies, attribute-based access control (ABAC), per-user overrides, or feature groups.
- Bulk import/export of permission matrices.
- Caching layer / CDN invalidation (optional optimization later).

---

## 5. Functional Requirements

### Data & Seeding

- **FR-001**: The system MUST persist feature permission rules in a dedicated table `feature_permissions`.
- **FR-002**: Each rule MUST include: unique `feature_key`, human-readable `description`, `allowed_roles` (list of role strings), `is_active` (boolean, default `true`), `created_at`, `updated_at`, and a stable primary key `id` (UUID).
- **FR-003**: `feature_key` MUST be unique, stable, lower-case, and match pattern `^[a-z][a-z0-9_]*$` (snake_case identifiers). Enforcement is via **seed/migration convention** this sprint (no admin create-key API); implementers SHOULD validate keys in seed data and document the pattern on the model.
- **FR-004**: `allowed_roles` MUST only contain values from the Sprint 1 role domain: `trader` and/or `admin`. Duplicates MUST be normalized away (store unique roles). Canonical order after normalization is **role priority**: `trader` then `admin` when both are present; single-role lists remain `["trader"]` or `["admin"]` (clarification Session 2026-07-30). Responses MUST use this canonical order.
- **FR-005**: Migration MUST seed at least the following features (keys fixed for future UI contracts):

| feature_key | Default allowed_roles | Intent |
| :--- | :--- | :--- |
| `admin_panel` | `["admin"]` | Access to administrative console |
| `user_management` | `["admin"]` | Manage users / roles (Sprint 2 APIs) |
| `system_logs` | `["admin"]` | Operational / system log visibility |
| `export_data` | `["admin"]` | Data export capabilities |
| `watchlist` | `["trader", "admin"]` | Watchlist feature |
| `portfolio_analytics` | `["trader", "admin"]` | Portfolio analytics views |
| `advanced_scanner` | `["trader", "admin"]` | Advanced scanner capabilities |

- **FR-006**: Seeding MUST be **idempotent** (re-running migration/seed must not create duplicate keys or corrupt existing operator customizations after first apply). Prefer: insert-if-not-exists by `feature_key` so later admin edits are preserved on re-seed.

### Authorization Gate (Admin APIs)

- **FR-007**: Feature-permission admin operations MUST use the same live-store admin gate as Sprint 2: authenticated, active, non-deleted, stored `role = admin` via `get_current_admin_user`.
- **FR-008**: Unauthenticated callers MUST receive **HTTP 401**.
- **FR-009**: Authenticated non-admins (traders, demoted former admins with stale JWT) MUST receive **HTTP 403**.

### List Features

- **FR-010**: Administrators MUST be able to list all feature permissions via `GET /admin/features`.
- **FR-011**: List response MUST include for each item: `id`, `feature_key`, `description`, `allowed_roles`, `is_active`, `created_at`, `updated_at`.
- **FR-012**: Default list MUST include **both** active and inactive features (admins need full visibility to re-enable).
- **FR-013**: Results MUST be ordered stably by `feature_key` ascending (admin UI friendly).
- **FR-014**: Pagination is **not required** for v1 (feature catalog is small: tens of rows). If implemented later, it must not break the v1 list contract without versioning.

### Update Feature Permission

- **FR-015**: Administrators MUST be able to update a feature via `PATCH /admin/features/{feature_key}`.
- **FR-016**: Request body MUST accept `allowed_roles` as a non-null array of role strings when updating roles. Optional fields MAY include `is_active` (boolean) and `description` (string); if omitted, existing values remain unchanged.
- **FR-017**: Unknown `feature_key` MUST yield **HTTP 404**.
- **FR-018**: Invalid role values in `allowed_roles` (not in `{trader, admin}`) MUST yield **HTTP 422**.
- **FR-019**: Non-array / wrong-type `allowed_roles` MUST yield **HTTP 422**.
- **FR-020**: Empty `allowed_roles` (`[]`) is **allowed** for **non-critical** features and means “no role may access this feature while it remains active.”
- **FR-021**: Successful update MUST return the full updated feature representation (same fields as list items).
- **FR-022**: If the patch results in **no material change** (same normalized roles, same is_active, same description), the system MUST return **HTTP 200** with the current feature and MUST **not** write a feature-permission audit entry.

### Safety Rules (Critical Features)

- **FR-023**: The **only** critical feature keys this sprint are `admin_panel` and `user_management` (clarification Session 2026-07-30 — minimal set). Updates that would leave `"admin"` out of `allowed_roles` for a critical feature MUST be rejected with **HTTP 400** and a clear message (no mutation, no success audit).
- **FR-024**: Setting `is_active = false` on a **critical** feature MUST be rejected with **HTTP 400** (prevents locking out the admin console / user management surface via soft-disable).
- **FR-025**: Critical-feature protection MUST apply even if the request also tries to change description or other fields in the same payload. On rejection, the system MUST leave **all** fields unchanged (including description and timestamps).
- **FR-026**: All other seeded features (`system_logs`, `export_data`, `watchlist`, `portfolio_analytics`, `advanced_scanner`) are **non-critical** and MAY remove `admin` from `allowed_roles` or set `is_active = false`.

### Access Helper

- **FR-027**: The system MUST provide a service helper `can_access_feature(feature_key: str, role: str) -> bool` (async if DB-backed). This helper is a **required** deliverable and MUST be covered by automated tests (AC-HELP-*).
- **FR-028**: Access evaluation rules (fail closed; **do not** use `normalize_role` if it clamps unknown values to `trader`):
  1. Resolve `role` as `str(role).strip().lower()`. If the result is **not** exactly in `VALID_ROLES` (`trader`|`admin`) → **deny** (`false`). Unknown/invalid roles MUST NOT inherit `trader` grants.
  2. If no row exists for `feature_key` → **deny** (`false`).
  3. If `is_active` is `false` → **deny**.
  4. If the resolved role is in `allowed_roles` → **allow**; else **deny**.
- **FR-029**: A FastAPI dependency factory (e.g. `require_feature("watchlist")`) is **optional** and **not** required for Definition of Done. If implemented, it MUST NOT be applied to existing product or admin routes this sprint (catalog-only delivery).
- **FR-030**: Helper MUST NOT grant access based solely on JWT claim without loading feature rules from the store (DB is source of truth for feature rules). Caller identity may still come from existing auth deps.
- **FR-036**: Existing Sprint 2 admin user-management routes MUST continue to authorize solely via `get_current_admin_user` (live role). They MUST NOT additionally require `user_management` or `admin_panel` feature permission checks this sprint.

### Audit Logging

- **FR-031**: On every successful **material** change to a feature permission, the system MUST write an audit log entry via existing `AuditService`.
- **FR-032**: Audit metadata MUST capture at least: actor user id, `feature_key`, previous `allowed_roles`, new `allowed_roles`, previous/new `is_active` when changed, and event type (e.g. `admin_feature_permission_change`).
- **FR-033**: Failed mutations (401/403/404/400/422) and pure no-ops MUST NOT create a successful feature-permission audit entry.

### Non-Regression

- **FR-034**: Sprint 1 auth flows and Sprint 2 admin user APIs MUST continue to pass.
- **FR-035**: Feature permissions MUST NOT alter trading, scanner, paper-trading, portfolio, or existing admin user-management execution paths this sprint. No route opts into the helper by default (clarification: catalog-only).

---

## 6. Non-Functional Requirements

### Security

- **NFR-001**: Admin feature APIs MUST use live-store admin authorization (same defense as Sprint 2 against stale JWT role claims).
- **NFR-002**: Feature catalog is not public; list/update require admin. No non-admin read/list endpoint for features this sprint (clarification Session 2026-07-30).
- **NFR-003**: Fail-closed access helper for missing/inactive features.
- **NFR-004**: Clients cannot invent new `feature_key` values via PATCH (keys are system-seeded).

### Reliability & Safety

- **NFR-005**: Critical-feature protection MUST be server-side; no client-trusted bypass.
- **NFR-006**: Concurrent updates to the same feature: last write wins is acceptable; each material change should still audit. No requirement for optimistic locking in v1.

### Performance

- **NFR-007**: Feature catalog is small; full list without pagination is acceptable for admin volume.
- **NFR-008**: Access checks are single-row lookups by unique `feature_key` (index required). Caching is optional and out of scope unless needed for tests.

### Maintainability

- **NFR-009**: Business logic MUST live in a dedicated service module (e.g. `feature_permission_service`), not fat route handlers.
- **NFR-010**: Role validation MUST reuse Sprint 1 `UserRole` / `VALID_ROLES` / `normalize_role`.
- **NFR-011**: Admin routes SHOULD extend existing `routes/admin.py` (or a clearly registered sibling under `/admin`) to keep one admin surface.

### Observability

- **NFR-012**: Feature permission change audits MUST be queryable via existing audit log storage.
- **NFR-013**: Critical-feature rejections MUST log at **warning** level with actor user id and `feature_key` (no secrets, no passwords/tokens).

### Compatibility

- **NFR-014**: No frontend changes required this sprint.
- **NFR-015**: Alembic migration MUST be reverse-friendly: `downgrade()` drops table `feature_permissions` cleanly (audit history for prior events may remain).

---

## 7. Safety Rules (Critical Feature Protection)

```
Before applying PATCH for feature_key F:
  1. Load F; if missing → 404
  2. Normalize allowed_roles (unique, valid domain only) else 422
  3. If F is critical (admin_panel | user_management):
        a. If new allowed_roles does not include "admin" → REJECT 400
        b. If request sets is_active=false → REJECT 400
  4. If no material change → 200, no audit
  5. Apply update, commit, audit material change, return entity
```

Rules:

1. **Administrators must always retain access** to `admin_panel` and `user_management` (only critical keys).
2. Critical features **cannot** be soft-disabled via `is_active=false`.
3. Critical rejections are **atomic**: no partial field updates (including description / `updated_at`).
4. Non-critical features (including admin-default seeds like `system_logs` / `export_data`) may drop `admin`, use `allowed_roles=[]`, or deactivate.
5. Empty roles on non-critical features means nobody can access via the helper while active.

---

## 8. API Contracts Summary

| Method | Path | Auth | Success | Key Errors |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/admin/features` | Admin (live) | 200 + feature list | 401, 403 |
| `PATCH` | `/admin/features/{feature_key}` | Admin (live) | 200 + feature | 401, 403, 404, 400, 422 |

Full request/response schemas: [contracts/feature-permissions-api.md](./contracts/feature-permissions-api.md).

### Error Status Semantics

| Status | Meaning |
| :--- | :--- |
| **401** | Not authenticated / invalid token |
| **403** | Authenticated but not a live admin |
| **404** | Unknown `feature_key` |
| **400** | Critical-feature safety violation (or other business rule) |
| **422** | Validation failure (invalid roles, body shape) |

---

## 9. User Scenarios & Testing

### User Story 1 – Admin Lists Feature Permissions (P1) 🎯 MVP

**Independent Test**: As admin, `GET /admin/features` returns seeded features with keys and allowed_roles; trader gets 403; unauthenticated gets 401.

1. **Given** admin session, **When** `GET /admin/features`, **Then** 200 with ≥7 features including fixed keys.
2. **Given** trader session, **When** `GET /admin/features`, **Then** 403.
3. **Given** no auth, **When** `GET /admin/features`, **Then** 401.
4. **Given** demoted admin with stale JWT, **When** list features, **Then** 403.

### User Story 2 – Admin Updates Allowed Roles (P1)

**Independent Test**: Admin can set `watchlist` to admin-only, then restore trader+admin; unknown key 404; invalid role 422.

1. Update non-critical feature `allowed_roles` → 200, response reflects new roles.
2. Unknown `feature_key` → 404.
3. `allowed_roles: ["superuser"]` → 422.
4. Trader caller → 403.
5. Same-roles no-op → 200, no audit.

### User Story 3 – Critical Feature Safety (P1)

**Independent Test**: Cannot remove admin from `admin_panel` or `user_management`; cannot set critical `is_active=false`; mixed invalid payload does not partially apply.

1. PATCH `admin_panel` with `allowed_roles: ["trader"]` → 400, roles unchanged.
2. PATCH `user_management` with `allowed_roles: []` → 400.
3. PATCH `admin_panel` with `is_active: false` → 400.
4. PATCH non-critical with `allowed_roles: []` → 200 allowed.
5. PATCH `admin_panel` with `allowed_roles: ["trader"]` **and** a new `description` → 400; description and roles **both** unchanged.

### User Story 4 – Access Helper (P1)

**Independent Test**: Unit/service tests for `can_access_feature` matrix.

1. Active feature with role in list → true.
2. Active feature with role not in list → false.
3. Inactive feature → false even if role listed.
4. Missing feature_key → false.
5. After admin updates roles, subsequent helper checks reflect new rules.
6. Unknown/invalid role string (e.g. `"superuser"`, `""`, `None`-like empty after strip) → false even when `allowed_roles` includes `trader`.

### User Story 5 – Audit Trail (P2)

1. Material role change → audit with actor, feature_key, previous/new allowed_roles.
2. Critical rejection / no-op / 401/403/404 → no success feature-permission audit.

### Edge Cases

- Duplicate roles in request (`["admin","admin"]`) → stored as unique `["admin"]`.
- Request `["admin","trader"]` → stored/returned as `["trader","admin"]` (canonical priority order).
- Case variants in roles on **PATCH** (`"Admin"`) → **422** (exact lower-case `trader`|`admin` only).
- Case variants on **helper** input (`"Admin"`) → strip+lower → `admin` if exact domain match after lower; `"SuperUser"` → deny (not in VALID_ROLES).
- Empty body PATCH → **422** (require at least one of `allowed_roles`, `is_active`, `description`).
- Critical mixed payload (illegal roles or deactivate + description change) → **400**, zero field mutations.
- Non-critical deactivated feature still appears on `GET /admin/features` with `is_active=false`.
- Concurrent dual updates → last write wins; both material writes may audit.
- Migration re-run / seed idempotency → no duplicate keys.
- Helper must not use `normalize_role` clamping that would turn `"xyz"` into `"trader"`.

---

## 10. Key Entities

- **Feature Permission**: Durable rule mapping `feature_key` → allowed roles + active flag.
- **Feature Key**: Stable system identifier (snake_case) referenced by future UI and guards.
- **Allowed Roles**: Subset of `{trader, admin}` granted access to a feature.
- **Critical Feature**: Subset of keys that must always remain usable by admins.
- **Administrator Principal**: Active user with live stored role `admin` (Sprint 2).
- **Audit Event (Feature Permission Change)**: actor, feature_key, previous/new values, event_type, timestamp.

---

## 11. Acceptance Criteria

### Authorization

- [ ] **AC-AUTH-01**: Unauthenticated `GET /admin/features` → 401.
- [ ] **AC-AUTH-02**: Trader `GET /admin/features` → 403.
- [ ] **AC-AUTH-03**: Admin `GET /admin/features` → 200.
- [ ] **AC-AUTH-04**: Demoted user with stale admin JWT → 403 on feature admin APIs.
- [ ] **AC-AUTH-05**: Unauthenticated / trader `PATCH .../features/{key}` → 401 / 403 respectively.

### List & Seed

- [ ] **AC-LIST-01**: List returns all seeded features (≥7) with required fields.
- [ ] **AC-LIST-02**: Seeded keys include: `admin_panel`, `user_management`, `system_logs`, `export_data`, `watchlist`, `portfolio_analytics`, `advanced_scanner`.
- [ ] **AC-LIST-03**: Default seed roles match FR-005 table.
- [ ] **AC-LIST-04**: List ordered by `feature_key` ascending.
- [ ] **AC-LIST-05**: Inactive features still appear in admin list (after non-critical `is_active=false`, GET still returns that row with `is_active=false`).

### Update

- [ ] **AC-UPD-01**: Admin can change non-critical `allowed_roles` → 200 with updated value.
- [ ] **AC-UPD-02**: Unknown feature_key → 404.
- [ ] **AC-UPD-03**: Invalid role in allowed_roles → 422.
- [ ] **AC-UPD-04**: Empty allowed_roles on non-critical → 200.
- [ ] **AC-UPD-05**: No-op update → 200, no audit.
- [ ] **AC-UPD-06**: Optional `is_active` toggle on non-critical works.
- [ ] **AC-UPD-07**: Duplicate roles in request are stored uniquely.
- [ ] **AC-UPD-08**: When both roles present, stored/returned order is `["trader","admin"]` regardless of request order.

### Critical Safety

- [ ] **AC-SAFE-01**: Removing admin from `admin_panel` → 400; unchanged.
- [ ] **AC-SAFE-02**: Removing admin from `user_management` → 400; unchanged.
- [ ] **AC-SAFE-03**: Setting critical feature `is_active=false` → 400; unchanged.
- [ ] **AC-SAFE-04**: Non-critical may remove admin and/or deactivate.
- [ ] **AC-SAFE-05**: Critical PATCH with illegal `allowed_roles` (or `is_active=false`) plus a new `description` → 400; description and all other fields unchanged.

### Access Helper

- [ ] **AC-HELP-01**: Role in allowed_roles + active → true.
- [ ] **AC-HELP-02**: Role not in list → false.
- [ ] **AC-HELP-03**: Inactive → false.
- [ ] **AC-HELP-04**: Missing feature → false.
- [ ] **AC-HELP-05**: Reflects updates after PATCH without process restart.
- [ ] **AC-HELP-06**: Unknown/invalid role (not exact `trader`|`admin` after strip+lower) → false even if `allowed_roles` includes `trader`.

### Audit

- [ ] **AC-AUD-01**: Material change creates audit with actor, feature_key, previous/new roles.
- [ ] **AC-AUD-02**: Failed critical safety change creates no success feature-permission audit.
- [ ] **AC-AUD-03**: No-op creates no feature-permission audit.

### Regression

- [ ] **AC-REG-01**: Sprint 1 auth suite still passes.
- [ ] **AC-REG-02**: Sprint 2 admin user suite still passes.

---

## 12. Success Criteria

- **SC-001**: 100% of unauthenticated feature-admin API calls → 401 in tests.
- **SC-002**: 100% of non-admin feature-admin API calls → 403 in tests (including stale-token-after-demotion).
- **SC-003**: Admins can list all seeded features with correct default roles after migration.
- **SC-004**: Admins can update non-critical feature roles at runtime; subsequent access checks reflect the change without redeploy.
- **SC-005**: 100% of attempts to lock admins out of critical features (`admin_panel`, `user_management`) fail with 400 and leave data intact.
- **SC-006**: 100% of material permission changes produce audit entries; no-ops and failures produce none.
- **SC-007**: Access helper is fail-closed for missing/inactive features and for unknown/invalid role strings (no silent map to trader).
- **SC-008**: Sprint 1 and Sprint 2 regression suites remain green.
- **SC-009**: Operators can complete “change who sees watchlist” in a single admin API call (list → patch) without engineering involvement.

---

## 13. Assumptions

- Sprint 1 binary role model remains the only role domain.
- Sprint 2 `get_current_admin_user` and `AuditService` remain the authorization and audit primitives.
- Feature keys are system-defined; product teams add new keys via migration/seed in future sprints, not via admin API.
- Empty `allowed_roles` is intentional “deny all roles” for non-critical features.
- Enforcement on existing routes is **out of scope** this sprint (clarification Session 2026-07-30: catalog only). Helper availability is the deliverable for future opt-in.
- Future frontend Feature Visibility tab will use admin `GET /admin/features` only. Trader-facing feature discovery (`GET /me/features` or similar) is explicitly deferred (clarification Session 2026-07-30).
- Storage of `allowed_roles` as JSONB (list of strings) is preferred for consistency with existing models and simple full-document replace on PATCH.

---

## 14. Dependencies

- Sprint 1 complete (`022-rbac-role-jwt-admin`).
- Sprint 2 complete (`023-admin-user-apis`) — especially `get_current_admin_user`.
- `UserRole`, `VALID_ROLES`, `normalize_role`, `AuditService`, admin router registration patterns.
- Alembic migration workflow used by the project.
- Test harness patterns from Sprint 1/2 (`TestClient`, async DB fixtures).

---

## 15. Risks

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| Admin locks self out of admin panel via feature rules | Critical operational lockout | FR-023–025 critical feature protection + tests |
| Missing feature key grants access by accident | High privilege leakage | Fail closed (FR-028) |
| Stale JWT used for admin feature APIs | High | Live-store `get_current_admin_user` |
| Seed overwrites operator customizations on re-migrate | Medium | Idempotent insert-if-not-exists |
| Scope creep into frontend / product enforcement | Medium | Strict out-of-scope; helper only |
| Invalid roles stored in JSONB | Medium | Validate against VALID_ROLES on write |

---

## 16. Sprint Summary

| Component | Mandate |
| :--- | :--- |
| **Table + migration** | `feature_permissions` with unique keys + seed ≥7 features |
| **GET /admin/features** | Admin list of all feature rules |
| **PATCH /admin/features/{key}** | Update allowed_roles (+ optional is_active/description) |
| **Critical safety** | Always keep admin on `admin_panel` & `user_management`; cannot deactivate them |
| **Helper** | Required: `can_access_feature` fail-closed (not wired to routes). Optional: `require_feature` dependency |
| **Audit** | Material changes only |
| **Route enforcement / frontend** | No changes this sprint (catalog only) |

---

## 17. Traceability

| Artifact | Path |
| :--- | :--- |
| Spec | [spec.md](./spec.md) |
| Plan | [plan.md](./plan.md) |
| Tasks | [tasks.md](./tasks.md) |
| Data model | [data-model.md](./data-model.md) |
| API contracts | [contracts/feature-permissions-api.md](./contracts/feature-permissions-api.md) |
| Research | [research.md](./research.md) |
| Quickstart | [quickstart.md](./quickstart.md) |
| Quality checklist | [checklists/requirements.md](./checklists/requirements.md) |
