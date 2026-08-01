# Implementation Plan: Sprint 2 – Backend Authorization + User Management APIs

**Branch**: `023-admin-user-apis`  
**Date**: 2026-07-29  
**Spec Document**: [spec.md](./spec.md)  
**Status**: Approved Architecture Plan  
**Depends On**: Sprint 1 (`022-rbac-role-jwt-admin`)  

---

## Summary

Deliver production-grade **admin-only** user directory and role-change APIs with live-store authorization, last-admin protection, and audit logging. No frontend work. Reuse Sprint 1 roles, auth deps, User model, and AuditService.

**Technical approach**: Add `get_current_admin_user` (DB-backed admin gate), `admin_user_service` for list/update-role business rules, `routes/admin.py` mounted at `/admin`, Pydantic schemas in `schemas/admin.py`, and comprehensive pytest coverage.

---

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async), Pydantic v2, pytest / pytest-asyncio  
**Storage**: PostgreSQL (prod) / project test DB (same as Sprint 1); no new migration expected  
**Testing**: pytest + FastAPI TestClient; unit + integration  
**Target Platform**: Backend API service (Linux/Windows server)  
**Project Type**: Web application (backend APIs only this sprint)  
**Performance Goals**: Admin list paginated (≤100/page); admin gate = 1 user row read per request  
**Constraints**: Live-store admin check; last-admin active-only; no frontend; no trading logic changes  
**Scale/Scope**: Low-volume admin operations; two endpoints; ~1 service module  

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution file is a placeholder template; project practice from Sprint 1 applies:

| Gate | Status | Notes |
| :--- | :--- | :--- |
| Reuse existing auth/role foundations | **Pass** | Sprint 1 UserRole, deps, AuditService |
| No unjustified new subsystems | **Pass** | Single service + routes + schemas |
| Testable acceptance criteria | **Pass** | AC-* in spec + tasks |
| Scope bounded | **Pass** | Explicit no UI / no permissions matrix |
| Security-sensitive ops audited | **Pass** | Role change audit required |

**Post-design re-check**: Still pass — design adds no parallel auth stack, no new DB product surface, no frontend.

---

## 1. Sprint Goal

1. Harden admin dependency for privilege-sensitive routes (`get_current_admin_user`).
2. Implement `GET /admin/users` (pagination, search, role filter).
3. Implement `PATCH /admin/users/{user_id}/role` with last-admin protection.
4. Audit real role changes; skip no-ops and failures.
5. Full test matrix + Sprint 1 regression green.

---

## 2. Architecture Overview

```
+-----------------------------------------------------------------------------------+
|  Client (future Admin UI — OUT OF SCOPE)                                          |
+--------------------------------------+--------------------------------------------+
                                       |  Bearer / HttpOnly cookie
                                       v
+-----------------------------------------------------------------------------------+
|  routes/admin.py  — GET /users, PATCH /users/{id}/role                            |
|         | depends on get_current_admin_user                                       |
|         v                                                                         |
|  core/deps.py — get_current_active_user + live role == admin                      |
|         |                                                                         |
|         v                                                                         |
|  services/admin_user_service.py — list_users, update_user_role                    |
|         |                           last-admin count, no-op, 404 rules            |
|         +----> models/auth.User                                                   |
|         +----> services/audit_service.AuditService (on real change)               |
+-----------------------------------------------------------------------------------+
```

### Key design decisions

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| Admin gate | **Live DB role** via `get_current_admin_user` | Clarification: token claim alone insufficient after demotion |
| Stateless `require_admin` | Keep for non-admin-panel use; **do not** use alone on these routes | Avoid breaking potential future lightweight gates |
| Last-admin population | Active + non-deleted + role=admin | Clarification session |
| Inactive/deleted role change | **404** | Align with directory eligibility |
| No-op role | 200, no audit | Clarification session |
| Service layer | `admin_user_service.py` | Keep routes thin; testable business rules |
| Schemas | `schemas/admin.py` | Clean separation from auth DTOs |
| Router | `routes/admin.py` prefix `/admin` | Matches `/auth` pattern |
| Migration | **None** (unless deleted_at filter needs index later) | Columns already exist |

---

## 3. File Structure Changes

### Documentation (this feature)

```text
specs/023-admin-user-apis/
├── plan.md                 # This file
├── spec.md                 # Feature specification
├── research.md             # Phase 0
├── data-model.md           # Phase 1
├── quickstart.md           # Phase 1 validation guide
├── contracts/admin-api.md  # API contracts
├── tasks.md                # Implementation tasks
└── checklists/requirements.md
```

### Source Code

```text
backend/
├── app/
│   ├── core/
│   │   └── deps.py                    # ADD get_current_admin_user; document require_admin
│   ├── schemas/
│   │   └── admin.py                   # NEW: UserAdminResponse, UserListResponse, UpdateRoleRequest
│   ├── services/
│   │   └── admin_user_service.py      # NEW: list_users, update_user_role, count_active_admins
│   └── routes/
│       ├── admin.py                   # NEW: GET /users, PATCH /users/{user_id}/role
│       └── __init__.py                # REGISTER admin router prefix=/admin
└── tests/
    ├── test_admin_deps.py             # NEW: live admin gate unit/integration
    ├── test_admin_users_list.py       # NEW: list authz + pagination + filters
    ├── test_admin_users_role.py       # NEW: role change, last-admin, audit, no-op
    └── test_sprint2_admin_comprehensive.py  # NEW: optional matrix suite
```

**Structure Decision**: Backend-only extension of existing FastAPI app. No frontend files. No new DB revision unless implementation discovers a hard requirement (not expected).

---

## 4. Step-by-Step Implementation Plan

```
Phase A: Dependencies (admin gate)
  -> Phase B: Schemas
    -> Phase C: Service (list + role + last-admin + audit)
      -> Phase D: Routes + router registration
        -> Phase E: Tests
          -> Phase F: Polish / regression / quickstart validation
```

### Phase A — Harden admin dependency

* Implement `async def get_current_admin_user(...)` depending on `get_current_active_user`.
* Raise 403 if `normalize_role(user.role) != admin` or soft-deleted if not already filtered.
* Optionally treat `deleted_at is not None` as 403/401 consistent with “not a valid admin principal.”
* Document that `require_admin` (JWT-only) remains available but admin user APIs use DB-backed gate.

### Phase B — Schemas

* `UserAdminResponse`: id, email, full_name, role, is_active, created_at
* `UserListResponse`: items, total, page, size
* `UpdateRoleRequest`: role: Literal["trader","admin"]

### Phase C — Service

* `list_users(db, *, page, size, search, role)` — filters active non-deleted; ilike search; count + offset/limit; order by created_at desc (stable default).
* `update_user_role(db, *, actor: User, target_id, new_role, ip, ua)`:
  1. Load target; 404 if missing/inactive/deleted
  2. Normalize roles
  3. If same role → return user (no audit)
  4. If demoting admin → count active admins; if would leave 0 → 400
  5. Apply role; commit
  6. Audit `admin_role_change` with metadata
  7. Return user

### Phase D — Routes

* `GET /users` query params with Query validation (page ≥ 1, 1 ≤ size ≤ 100)
* `PATCH /users/{user_id}/role`
* Both depend on `get_current_admin_user` + `get_db`
* Register: `api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])`

### Phase E — Tests

Cover all AC-* from spec (see Testing Strategy).

### Phase F — Polish

* Run Sprint 1 RBAC suite + new admin suite
* Execute quickstart scenarios
* Ensure no frontend diffs

---

## 5. Dependencies on Sprint 1

| Sprint 1 Asset | Sprint 2 Use |
| :--- | :--- |
| `UserRole`, `normalize_role`, `VALID_ROLES` | Role validation & comparisons |
| `User` model (role, is_active, deleted_at) | Directory + last-admin count |
| `get_current_user` / `get_current_active_user` | Base for admin gate |
| JWT Bearer + cookie extraction | Identity resolution |
| `AuditService.log_event` | Role change audit |
| Default admin bootstrap | Seeded admin for manual/E2E tests |
| Registration force-trader | Ensures new users appear as traders in list |

---

## 6. Risks & Mitigations

| Risk ID | Description | Impact | Mitigation |
| :--- | :--- | :--- | :--- |
| **R-01** | Last admin demoted via race | Critical | Re-count active admins immediately before write; tests |
| **R-02** | Stale JWT still used for admin | High | `get_current_admin_user` live role check |
| **R-03** | 404 vs 403 confusion for inactive targets | Medium | Spec: inactive/deleted targets → 404 for role change |
| **R-04** | Audit noise from no-ops | Low | FR-017 / FR-019a: no audit on no-op |
| **R-05** | Soft-delete field naming variance | Medium | Confirm `User.deleted_at`; filter `is_(None)` |
| **R-06** | Accidental frontend scope creep | Medium | Tasks exclude all `frontend/` paths |

---

## 7. Testing Strategy

### Unit

* Admin dependency: active admin passes; trader 403; inactive 403; missing 401.
* Service last-admin counter: active-only.
* No-op short-circuit (no audit call).
* Schema validation rejects invalid roles.

### Integration (HTTP)

* Admin list 200; trader 403; anon 401.
* Pagination defaults and max size.
* Search and role filter.
* Promote / demote success.
* Last-admin self and other → 400.
* Inactive target → 404.
* Invalid role → 422.
* Unknown UUID → 404.
* Audit row created only on real change.
* Stale admin JWT after demotion → 403.

### Regression

* `tests/test_sprint1_rbac_comprehensive.py` (and related Sprint 1 files) remain green.

### Manual (quickstart)

* Login as default admin; list users; promote a trader; attempt demote last admin.

---

## 8. Definition of Done

- [ ] `get_current_admin_user` (or equivalent) production-ready in `deps.py`
- [ ] `GET /admin/users` and `PATCH /admin/users/{user_id}/role` implemented and registered
- [ ] Last-admin protection (active non-deleted) enforced for self and other
- [ ] Audit on real role changes; none on no-ops/failures
- [ ] All new admin tests pass
- [ ] Sprint 1 auth tests still pass
- [ ] No frontend changes
- [ ] Quickstart scenarios validated
- [ ] Spec AC checklist can be marked complete during implement/verify

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
| API contracts | [contracts/admin-api.md](./contracts/admin-api.md) |
| Quickstart | [quickstart.md](./quickstart.md) |
| Tasks | [tasks.md](./tasks.md) |
