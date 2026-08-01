# Implementation Plan: Sprint 3 – Feature Permissions System

**Branch**: `024-feature-permissions`  
**Date**: 2026-07-30  
**Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/024-feature-permissions/spec.md`  
**Status**: Implementation-ready (post-clarify)  
**Depends On**: Sprint 1 (`022-rbac-role-jwt-admin`), Sprint 2 (`023-admin-user-apis`)

---

## Summary

Deliver a **database-driven Feature Permissions** catalog so administrators can change which roles (`trader` | `admin`) may access named product features **at runtime**, without code deploys. This is the backend foundation for the future Admin Panel “Feature Visibility” tab.

**Technical approach**: New `feature_permissions` table (Alembic + seed ≥7 keys) → service layer (`list`, `update`, `can_access_feature`) → admin-only HTTP APIs on existing `/admin` router → audit material changes → comprehensive tests. **Catalog-only**: do not wire the helper onto existing product or Sprint 2 admin user routes.

**Clarifications locked (2026-07-30)**:
1. Catalog only — no route enforcement wiring
2. No non-admin feature discovery API
3. `can_access_feature` required; `require_feature` optional / not DoD
4. Critical keys: only `admin_panel`, `user_management`
5. Canonical `allowed_roles` order: `trader` then `admin`

---

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async), Pydantic v2, Alembic, pytest / pytest-asyncio  
**Storage**: PostgreSQL — new table `feature_permissions`; `allowed_roles` as **JSONB** list of strings  
**Testing**: pytest + FastAPI TestClient; unit + HTTP integration + Sprint 1/2 regression  
**Target Platform**: Backend API service (Linux/Windows server)  
**Project Type**: Web application (backend APIs only this sprint)  
**Performance Goals**: Full catalog list (small N ≤ tens of rows); access check = 1 indexed row by `feature_key`  
**Constraints**: Live-store admin gate; critical-feature safety; fail-closed helper; no frontend; no product route wiring  
**Scale/Scope**: 7 seeded features; 2 admin endpoints; 1 model + 1 service + schema extensions  

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution file is a placeholder template; project practice from Sprints 1–2 applies:

| Gate | Status | Notes |
| :--- | :--- | :--- |
| Reuse existing auth/role foundations | **Pass** | `get_current_admin_user`, `VALID_ROLES`, `AuditService` |
| No unjustified new subsystems | **Pass** | Single table + service + admin routes |
| Testable acceptance criteria | **Pass** | AC-* / SC-* in spec; tasks cover tests |
| Scope bounded | **Pass** | Catalog-only; no UI; no product enforcement |
| Security-sensitive ops audited | **Pass** | `admin_feature_permission_change` on material updates |

**Post-design re-check**: **Pass** — no parallel auth stack, no frontend, no hierarchy engine, clarifications reduce scope risk.

---

## Project Structure

### Documentation (this feature)

```text
specs/024-feature-permissions/
├── plan.md                              # This file
├── spec.md                              # Clarified feature specification
├── research.md                          # Phase 0
├── data-model.md                        # Phase 1
├── quickstart.md                        # Phase 1 validation guide
├── contracts/feature-permissions-api.md # Phase 1 API contracts
├── tasks.md                             # Implementation tasks
└── checklists/requirements.md
```

### Source Code (repository)

```text
backend/
├── alembic/
│   └── versions/
│       └── YYYYMMDD_HHMM_feature_permissions.py   # NEW: table + seed
├── app/
│   ├── models/
│   │   ├── feature_permission.py                  # NEW
│   │   └── __init__.py                            # EXPORT FeaturePermission
│   ├── schemas/
│   │   └── admin.py                               # EXTEND feature DTOs
│   ├── services/
│   │   └── feature_permission_service.py          # NEW
│   ├── core/
│   │   ├── deps.py                                # REUSE get_current_admin_user; optional require_feature
│   │   └── roles.py                               # REUSE VALID_ROLES / normalize_role
│   └── routes/
│       └── admin.py                               # EXTEND GET/PATCH /features
└── tests/
    ├── test_feature_permission_schemas.py
    ├── test_feature_permission_service.py
    ├── test_feature_permissions_list.py
    └── test_feature_permissions_update.py
```

**Structure Decision**: Backend-only extension of the existing FastAPI app. Reuse `/admin` router registration already present in `backend/app/routes/__init__.py`. No frontend paths.

---

## 1. Architecture Overview

```
+-----------------------------------------------------------------------------------+
|  Client (future Admin UI — Feature Visibility tab)     OUT OF SCOPE THIS SPRINT   |
+--------------------------------------+--------------------------------------------+
                                       |  Bearer / HttpOnly cookie
                                       v
+-----------------------------------------------------------------------------------+
|  routes/admin.py                                                                  |
|    GET  /features                                                                 |
|    PATCH /features/{feature_key}                                                  |
|         | Depends(get_current_admin_user)   # Sprint 2 live role gate             |
|         v                                                                         |
|  services/feature_permission_service.py                                           |
|    list_features                                                                  |
|    update_feature_permission  (+ critical safety, normalize, no-op, audit)         |
|    can_access_feature         (fail closed; required helper)                      |
|         |                                                                         |
|         +----> models/feature_permission.FeaturePermission                        |
|         +----> services/audit_service.AuditService                                |
|         +----> core/roles.VALID_ROLES                                             |
+-----------------------------------------------------------------------------------+
|  NOT wired this sprint: product routes, /admin/users, require_feature consumers   |
+-----------------------------------------------------------------------------------+
```

---

## 2. Design Decisions

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| Admin gate | Reuse `get_current_admin_user` | Same privilege bar as Sprint 2; defeats stale JWT after demotion |
| `allowed_roles` storage | JSONB array of strings | Matches project JSONB usage; simple full replace on PATCH |
| Feature keys | System-seeded only | Stable UI contracts; no invent-key admin API |
| Route enforcement | **Catalog only** | Clarification; avoids product/admin regression |
| Non-admin discovery | **None** | Clarification; defer `GET /me/features` |
| Helper DoD | **`can_access_feature` required**; `require_feature` optional | Clarification |
| Critical features | **Only** `admin_panel`, `user_management` | Clarification; lockout prevention |
| Role list order | Canonical **`trader` then `admin`** | Clarification; test/UI stability |
| Empty `allowed_roles` | Allowed on non-critical → deny all | Explicit “off for everyone” without deleting key |
| Missing feature in helper | **Deny** | Fail closed |
| Unknown role in helper | **Deny** (no `normalize_role` clamp to trader) | Post-analyze remediation; avoid accidental trader grants |
| Critical mixed PATCH | **Reject all fields** (400, no partial apply) | Post-analyze remediation |
| Seed strategy | Insert-if-not-exists by `feature_key` | Preserve operator edits |
| List envelope | `{ "items": [...] }` | Align with Sprint 2 list style; evolvable |
| Role write validation | Exact lower-case `trader`\|`admin` only | Predictable 422; no silent clamp |
| Concurrent updates | Last write wins | Acceptable for admin volume |

---

## 3. Database Design

### Table: `feature_permissions`

| Column | Type | Constraints |
| :--- | :--- | :--- |
| `id` | UUID | PK, default uuid4 |
| `feature_key` | VARCHAR(64) | NOT NULL, UNIQUE |
| `description` | VARCHAR(255) | NOT NULL |
| `allowed_roles` | JSONB | NOT NULL, default `[]` |
| `is_active` | BOOLEAN | NOT NULL, default `true` |
| `created_at` | TIMESTAMPTZ | NOT NULL, server default now() |
| `updated_at` | TIMESTAMPTZ | NOT NULL, server default now(), onupdate |

### Seed (idempotent, ≥7)

| feature_key | allowed_roles | critical |
| :--- | :--- | :---: |
| `admin_panel` | `["admin"]` | Yes |
| `user_management` | `["admin"]` | Yes |
| `system_logs` | `["admin"]` | No |
| `export_data` | `["admin"]` | No |
| `watchlist` | `["trader","admin"]` | No |
| `portfolio_analytics` | `["trader","admin"]` | No |
| `advanced_scanner` | `["trader","admin"]` | No |

Full field rules, audit metadata, and DTOs: [data-model.md](./data-model.md).

**Migration location**: `backend/alembic/versions/` (project uses `backend/alembic.ini`).

---

## 4. API Design

| Method | Path | Auth | Success | Errors |
| :--- | :--- | :--- | :--- | :--- |
| GET | `/admin/features` | Live admin | 200 `{items}` | 401, 403 |
| PATCH | `/admin/features/{feature_key}` | Live admin | 200 feature | 401, 403, 404, 400, 422 |

**In-process helper** (required):

```text
can_access_feature(db, feature_key, role) -> bool
  role_n = strip+lower(role)
  if role_n not in {trader, admin}: return False   # no clamp to trader
  missing | inactive | role_n not in allowed_roles → False
  else → True
```

Full request/response/error examples: [contracts/feature-permissions-api.md](./contracts/feature-permissions-api.md).

---

## 5. Implementation Steps (Phased)

```
Phase A: Model + Alembic migration + idempotent seed
  → Phase B: Pydantic schemas (response + update request)
    → Phase C: Service (list, update, safety, normalize, no-op, audit, helper)
      → Phase D: Routes on admin.py
        → Phase E: Tests (unit + integration + regression)
          → Phase F: Quickstart polish / DoD checklist
```

### Phase A — Model + Migration + Seed

1. Create `FeaturePermission` in `backend/app/models/feature_permission.py`.
2. Export from `backend/app/models/__init__.py` so metadata registers.
3. Alembic revision: create table + unique on `feature_key`; implement reverse-friendly `downgrade()` that drops the table (NFR-015).
4. Seed 7 rows with insert-if-not-exists (do not overwrite existing rows); keys match `^[a-z][a-z0-9_]*$` (FR-003 seed convention).

### Phase B — Schemas

In `backend/app/schemas/admin.py`:

- `FeaturePermissionResponse`
- `FeatureListResponse` (`items`)
- `UpdateFeaturePermissionRequest` — optional `allowed_roles`, `is_active`, `description`; model validator requires ≥1 field; `allowed_roles` elements `Literal["trader","admin"]`

### Phase C — Service

In `backend/app/services/feature_permission_service.py`:

- `CRITICAL_FEATURE_KEYS = frozenset({"admin_panel", "user_management"})`
- `normalize_allowed_roles(roles) -> list[str]` — validate domain, dedupe, order trader→admin
- `list_features(db)` — order by `feature_key` ASC; include inactive
- `update_feature_permission(...)` — 404 / 400 critical / no-op / apply / audit
- `can_access_feature(db, feature_key, role) -> bool` — fail closed; domain roles only (no `normalize_role` clamp)
- On critical 400: log warning with actor id + feature_key (NFR-013); leave all fields unchanged

### Phase D — Routes

Extend `backend/app/routes/admin.py`:

- `GET /features` → `FeatureListResponse`
- `PATCH /features/{feature_key}` → `FeaturePermissionResponse`
- Both depend on `get_current_admin_user` + `get_db`
- Pass IP / UA into service for audit

Router already mounted: `api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])`.

### Phase E — Tests

Cover AC-AUTH, AC-LIST, AC-UPD, AC-SAFE, AC-HELP, AC-AUD, AC-REG (see Testing Strategy).

### Phase F — Polish

- Sprint 1 + Sprint 2 suites green
- Quickstart scenarios
- Confirm zero frontend diffs
- Optional only: `require_feature` in `deps.py` (not DoD)

---

## 6. Dependencies on Prior Sprints

| Asset | Sprint | Use |
| :--- | :--- | :--- |
| `UserRole`, `VALID_ROLES`, `normalize_role` | 1 | Role domain / helper role normalize |
| JWT Bearer + cookie auth | 1 | Identity for admin gate |
| `get_current_admin_user` | 2 | Gate all feature admin APIs |
| `routes/admin.py` + `/admin` mount | 2 | Host new endpoints |
| `AuditService.log_event` | 1/2 | Permission change audit |
| Admin test login patterns | 2 | Integration tests |

---

## 7. Risks & Mitigations

| ID | Risk | Impact | Mitigation |
| :--- | :--- | :--- | :--- |
| R-01 | Admin removes self from `admin_panel` | Critical lockout | Critical-feature rules + tests |
| R-02 | Fail-open missing feature | High | Helper defaults deny |
| R-03 | Seed overwrites operator edits | Medium | Insert-if-not-exists only |
| R-04 | Invalid roles in JSONB | Medium | Pydantic + service validation |
| R-05 | Scope creep into product routes | Medium | Clarification catalog-only; tasks forbid wiring |
| R-06 | Stale JWT on admin feature APIs | High | Live `get_current_admin_user` |
| R-07 | Implementer treats T041 as required | Low | Tasks mark optional; DoD excludes it |

---

## 8. Testing Strategy

### Unit

- `can_access_feature` matrix: allow / deny / inactive / missing
- Critical safety pure checks
- Role normalization: dedupe + trader-then-admin order
- Schema: invalid roles, empty PATCH body → validation error

### Integration (HTTP)

- List: admin 200 (≥7, ordered, fields); trader 403; anon 401; stale JWT 403
- Seed keys + default roles match FR-005
- PATCH success non-critical; 404 unknown; 422 bad roles / empty body
- Empty roles on non-critical OK; is_active toggle non-critical OK
- Critical remove-admin / deactivate → 400 unchanged
- No-op → 200 no audit; material → audit event present
- Sprint 2 `/admin/users` still works (no feature gate added)

### Regression

- Sprint 1 RBAC comprehensive suite
- Sprint 2 admin user suite

### Manual

- [quickstart.md](./quickstart.md)

---

## 9. Definition of Done

- [ ] `feature_permissions` table migrated; ≥7 seeds present
- [ ] `GET /admin/features` and `PATCH /admin/features/{feature_key}` live under live admin gate
- [ ] Critical protection for `admin_panel` + `user_management` only
- [ ] `can_access_feature` implemented, fail-closed (incl. unknown roles), tested
- [ ] Critical rejections leave all fields unchanged; warning log present
- [ ] Migration `downgrade()` drops `feature_permissions`
- [ ] Material updates audited; no-ops/failures not
- [ ] Canonical role order `trader` then `admin`
- [ ] No wiring of helper onto existing product/admin-user routes
- [ ] No non-admin feature discovery endpoint
- [ ] New tests pass; Sprint 1 + 2 suites green
- [ ] No frontend changes
- [ ] Quickstart scenarios validated
- [ ] `require_feature` **not** required for completion

---

## Complexity Tracking

> No constitution violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

---

## Phase 0 / Phase 1 Outputs

| Artifact | Path |
| :--- | :--- |
| Research | [research.md](./research.md) |
| Data model | [data-model.md](./data-model.md) |
| API contracts | [contracts/feature-permissions-api.md](./contracts/feature-permissions-api.md) |
| Quickstart | [quickstart.md](./quickstart.md) |
| Tasks | [tasks.md](./tasks.md) *(via `/speckit-tasks` or already present)* |

---

## Next Command

`/speckit-tasks` to regenerate/refine task breakdown if needed, then `/speckit-implement`.
