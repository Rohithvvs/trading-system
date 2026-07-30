"""Integration tests for PATCH /admin/features (Sprint 3 US2–US5)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.core.roles import UserRole
from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.auth import AuditLog, User
from app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
from app.services.feature_permission_service import (
    EVENT_FEATURE_PERMISSION_CHANGE,
)


def _run(coro):
    return asyncio.run(coro)


async def _seed_admin_async() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_default_admin(db)


def _seed_admin() -> None:
    _run(_seed_admin_async())


@pytest.fixture()
def api(test_engine):
    with TestClient(app) as c:
        yield c


def _admin_headers(api: TestClient) -> dict:
    _seed_admin()
    res = api.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _register_trader(api: TestClient) -> dict:
    email = f"trader_{uuid.uuid4().hex[:10]}@example.com"
    res = api.post(
        "/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "FP Trader",
        },
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


def test_patch_watchlist_admin_only_then_restore(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"allowed_roles": ["admin"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["allowed_roles"] == ["admin"]

    res2 = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"allowed_roles": ["trader", "admin"]},
    )
    assert res2.status_code == 200
    assert res2.json()["allowed_roles"] == ["trader", "admin"]


def test_patch_canonical_role_order(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"allowed_roles": ["admin", "trader"]},
    )
    assert res.status_code == 200
    assert res.json()["allowed_roles"] == ["trader", "admin"]


def test_patch_unknown_key_404(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/does_not_exist",
        headers=headers,
        json={"allowed_roles": ["admin"]},
    )
    assert res.status_code == 404


def test_patch_invalid_role_422(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"allowed_roles": ["superuser"]},
    )
    assert res.status_code == 422


def test_patch_empty_body_422(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={},
    )
    assert res.status_code == 422


def test_patch_empty_roles_non_critical(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/export_data",
        headers=headers,
        json={"allowed_roles": []},
    )
    assert res.status_code == 200, res.text
    assert res.json()["allowed_roles"] == []


def test_patch_noop_200(api):
    headers = _admin_headers(api)
    # Ensure known state
    api.patch(
        "/admin/features/system_logs",
        headers=headers,
        json={"allowed_roles": ["admin"]},
    )
    res = api.patch(
        "/admin/features/system_logs",
        headers=headers,
        json={"allowed_roles": ["admin"]},
    )
    assert res.status_code == 200


def test_patch_trader_403_unauth_401(api):
    trader = _register_trader(api)
    res = api.patch(
        "/admin/features/watchlist",
        headers={"Authorization": f"Bearer {trader['access_token']}"},
        json={"allowed_roles": ["admin"]},
    )
    assert res.status_code == 403
    # Clear cookies so a prior register session does not authenticate
    api.cookies.clear()
    unauth = api.patch(
        "/admin/features/watchlist",
        json={"allowed_roles": ["admin"]},
    )
    assert unauth.status_code == 401


def test_critical_remove_admin_400(api):
    headers = _admin_headers(api)
    for key in ("admin_panel", "user_management"):
        res = api.patch(
            f"/admin/features/{key}",
            headers=headers,
            json={"allowed_roles": ["trader"]},
        )
        assert res.status_code == 400, res.text
        body = api.get("/admin/features", headers=headers).json()
        by_key = {i["feature_key"]: i for i in body["items"]}
        assert "admin" in by_key[key]["allowed_roles"]


def test_critical_deactivate_400(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/admin_panel",
        headers=headers,
        json={"is_active": False},
    )
    assert res.status_code == 400
    body = api.get("/admin/features", headers=headers).json()
    by_key = {i["feature_key"]: i for i in body["items"]}
    assert by_key["admin_panel"]["is_active"] is True


def test_critical_mixed_payload_no_partial_apply(api):
    headers = _admin_headers(api)
    before = api.get("/admin/features", headers=headers).json()
    desc_before = next(
        i["description"] for i in before["items"] if i["feature_key"] == "admin_panel"
    )
    res = api.patch(
        "/admin/features/admin_panel",
        headers=headers,
        json={
            "allowed_roles": ["trader"],
            "description": "Hacked description",
        },
    )
    assert res.status_code == 400
    after = api.get("/admin/features", headers=headers).json()
    row = next(i for i in after["items"] if i["feature_key"] == "admin_panel")
    assert row["description"] == desc_before
    assert "admin" in row["allowed_roles"]


def test_stale_jwt_after_demotion_403(api, test_engine):
    """Second admin with JWT is demoted; stale token cannot access feature admin APIs."""
    headers = _admin_headers(api)
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    email = f"second_admin_{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as session:
        u = User(
            id=uuid.uuid4(),
            email=email,
            full_name="Second Admin",
            password_hash=get_password_hash("SecurePassword123!"),
            role=UserRole.ADMIN.value,
            is_active=True,
        )
        session.add(u)
        session.commit()
        uid = str(u.id)

    login = api.post(
        "/auth/login",
        json={"email": email, "password": "SecurePassword123!"},
    )
    assert login.status_code == 200
    stale_token = login.json()["access_token"]
    stale_headers = {"Authorization": f"Bearer {stale_token}"}
    assert api.get("/admin/features", headers=stale_headers).status_code == 200

    demote = api.patch(
        f"/admin/users/{uid}/role",
        headers=headers,
        json={"role": "trader"},
    )
    assert demote.status_code == 200, demote.text
    assert api.get("/admin/features", headers=stale_headers).status_code == 403


def test_ac_upd_06_is_active_toggle_non_critical(api):
    """AC-UPD-06: optional is_active toggle on non-critical works."""
    headers = _admin_headers(api)
    off = api.patch(
        "/admin/features/advanced_scanner",
        headers=headers,
        json={"is_active": False},
    )
    assert off.status_code == 200
    assert off.json()["is_active"] is False
    on = api.patch(
        "/admin/features/advanced_scanner",
        headers=headers,
        json={"is_active": True},
    )
    assert on.status_code == 200
    assert on.json()["is_active"] is True


def test_ac_upd_07_duplicate_roles_stored_uniquely(api):
    """AC-UPD-07: duplicate roles in request are stored uniquely."""
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"allowed_roles": ["admin", "admin", "trader", "trader"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["allowed_roles"] == ["trader", "admin"]


def test_ac_safe_04_non_critical_may_remove_admin(api):
    """AC-SAFE-04: non-critical may remove admin from allowed_roles."""
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/portfolio_analytics",
        headers=headers,
        json={"allowed_roles": ["trader"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["allowed_roles"] == ["trader"]
    assert "admin" not in res.json()["allowed_roles"]


def test_ac_safe_02_user_management_empty_roles_400(api):
    """AC-SAFE-02: empty allowed_roles on user_management → 400."""
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/user_management",
        headers=headers,
        json={"allowed_roles": []},
    )
    assert res.status_code == 400
    body = api.get("/admin/features", headers=headers).json()
    row = next(i for i in body["items"] if i["feature_key"] == "user_management")
    assert "admin" in row["allowed_roles"]
    assert row["is_active"] is True


def test_patch_description_only_success(api):
    """Edge: description-only PATCH on non-critical succeeds."""
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/system_logs",
        headers=headers,
        json={"description": "Updated system logs description"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["description"] == "Updated system logs description"


def test_patch_case_variant_role_422(api):
    """Edge: PATCH with 'Admin' (wrong case) → 422."""
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"allowed_roles": ["Admin"]},
    )
    assert res.status_code == 422


def test_audit_on_material_change_not_on_noop_or_critical_fail(api, test_engine):
    headers = _admin_headers(api)
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)

    def _count_feature_audits() -> int:
        with SessionLocal() as session:
            rows = (
                session.execute(
                    select(AuditLog).where(
                        AuditLog.event_type == EVENT_FEATURE_PERMISSION_CHANGE
                    )
                )
                .scalars()
                .all()
            )
            return len(rows)

    before = _count_feature_audits()

    # Material change
    res = api.patch(
        "/admin/features/export_data",
        headers=headers,
        json={"allowed_roles": ["trader", "admin"]},
    )
    assert res.status_code == 200
    after_material = _count_feature_audits()
    assert after_material == before + 1

    # No-op
    res2 = api.patch(
        "/admin/features/export_data",
        headers=headers,
        json={"allowed_roles": ["trader", "admin"]},
    )
    assert res2.status_code == 200
    assert _count_feature_audits() == after_material

    # Critical fail
    res3 = api.patch(
        "/admin/features/admin_panel",
        headers=headers,
        json={"allowed_roles": ["trader"]},
    )
    assert res3.status_code == 400
    assert _count_feature_audits() == after_material
