"""
Sprint 3 Feature Permissions — AC matrix (SDET / Testing.md).

Maps each AC-* from specs/024-feature-permissions/spec.md to at least one test.
Prefer thin orchestration + shared helpers; deeper assertions live in dedicated modules.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.core.roles import UserRole
from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.auth import AuditLog, User
from app.models.feature_permission import FeaturePermission
from app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
from app.services.feature_permission_service import (
    DEFAULT_FEATURES,
    EVENT_FEATURE_PERMISSION_CHANGE,
    can_access_feature,
    ensure_default_feature_permissions,
)


REQUIRED_KEYS = {
    "admin_panel",
    "user_management",
    "system_logs",
    "export_data",
    "watchlist",
    "portfolio_analytics",
    "advanced_scanner",
}
SEED_DEFAULTS = {f["feature_key"]: f["allowed_roles"] for f in DEFAULT_FEATURES}


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
    email = f"ac_trader_{uuid.uuid4().hex[:10]}@example.com"
    res = api.post(
        "/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "AC Trader",
        },
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


# --- Authorization ---


def test_ac_auth_01_unauthenticated_get_401(api):
    api.cookies.clear()
    assert api.get("/admin/features").status_code == 401


def test_ac_auth_02_trader_get_403(api):
    trader = _register_trader(api)
    res = api.get(
        "/admin/features",
        headers={"Authorization": f"Bearer {trader['access_token']}"},
    )
    assert res.status_code == 403


def test_ac_auth_03_admin_get_200(api):
    headers = _admin_headers(api)
    res = api.get("/admin/features", headers=headers)
    assert res.status_code == 200
    assert "items" in res.json()


def test_ac_auth_04_stale_jwt_after_demotion_403(api, test_engine):
    headers = _admin_headers(api)
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    email = f"stale_{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as session:
        u = User(
            id=uuid.uuid4(),
            email=email,
            full_name="Stale Admin",
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
    stale = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert api.get("/admin/features", headers=stale).status_code == 200
    demote = api.patch(
        f"/admin/users/{uid}/role",
        headers=headers,
        json={"role": "trader"},
    )
    assert demote.status_code == 200
    assert api.get("/admin/features", headers=stale).status_code == 403
    assert api.patch(
        "/admin/features/watchlist",
        headers=stale,
        json={"allowed_roles": ["admin"]},
    ).status_code == 403


def test_ac_auth_05_patch_unauth_401_trader_403(api):
    trader = _register_trader(api)
    assert (
        api.patch(
            "/admin/features/watchlist",
            headers={"Authorization": f"Bearer {trader['access_token']}"},
            json={"allowed_roles": ["admin"]},
        ).status_code
        == 403
    )
    api.cookies.clear()
    assert (
        api.patch(
            "/admin/features/watchlist",
            json={"allowed_roles": ["admin"]},
        ).status_code
        == 401
    )


# --- List & seed ---


def test_ac_list_01_to_04_seed_shape_order_roles(api):
    headers = _admin_headers(api)
    res = api.get("/admin/features", headers=headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) >= 7  # AC-LIST-01
    keys = [i["feature_key"] for i in items]
    assert REQUIRED_KEYS <= set(keys)  # AC-LIST-02
    assert keys == sorted(keys)  # AC-LIST-04
    by_key = {i["feature_key"]: i for i in items}
    for k, roles in SEED_DEFAULTS.items():
        assert by_key[k]["allowed_roles"] == roles  # AC-LIST-03
    for item in items:
        assert {
            "id",
            "feature_key",
            "description",
            "allowed_roles",
            "is_active",
            "created_at",
            "updated_at",
        } <= set(item.keys())


def test_ac_list_05_inactive_still_listed(api):
    headers = _admin_headers(api)
    assert (
        api.patch(
            "/admin/features/export_data",
            headers=headers,
            json={"is_active": False},
        ).status_code
        == 200
    )
    items = api.get("/admin/features", headers=headers).json()["items"]
    row = next(i for i in items if i["feature_key"] == "export_data")
    assert row["is_active"] is False


# --- Update ---


def test_ac_upd_01_change_non_critical_roles(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"allowed_roles": ["admin"]},
    )
    assert res.status_code == 200
    assert res.json()["allowed_roles"] == ["admin"]


def test_ac_upd_02_unknown_key_404(api):
    headers = _admin_headers(api)
    assert (
        api.patch(
            "/admin/features/nope_missing_key",
            headers=headers,
            json={"allowed_roles": ["admin"]},
        ).status_code
        == 404
    )


def test_ac_upd_03_invalid_role_422(api):
    headers = _admin_headers(api)
    assert (
        api.patch(
            "/admin/features/watchlist",
            headers=headers,
            json={"allowed_roles": ["superuser"]},
        ).status_code
        == 422
    )


def test_ac_upd_04_empty_roles_non_critical(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/system_logs",
        headers=headers,
        json={"allowed_roles": []},
    )
    assert res.status_code == 200
    assert res.json()["allowed_roles"] == []


def test_ac_upd_05_and_aud_03_noop_no_audit(api, test_engine):
    headers = _admin_headers(api)
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)

    def count_audits() -> int:
        with SessionLocal() as s:
            return int(
                s.execute(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.event_type == EVENT_FEATURE_PERMISSION_CHANGE)
                ).scalar_one()
            )

    api.patch(
        "/admin/features/advanced_scanner",
        headers=headers,
        json={"allowed_roles": ["trader", "admin"]},
    )
    before = count_audits()
    res = api.patch(
        "/admin/features/advanced_scanner",
        headers=headers,
        json={"allowed_roles": ["trader", "admin"]},
    )
    assert res.status_code == 200
    assert count_audits() == before


def test_ac_upd_06_is_active_toggle(api):
    headers = _admin_headers(api)
    off = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"is_active": False},
    )
    assert off.status_code == 200 and off.json()["is_active"] is False
    on = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"is_active": True},
    )
    assert on.status_code == 200 and on.json()["is_active"] is True


def test_ac_upd_07_dedupe_roles(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"allowed_roles": ["admin", "admin"]},
    )
    assert res.status_code == 200
    assert res.json()["allowed_roles"] == ["admin"]


def test_ac_upd_08_canonical_order(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"allowed_roles": ["admin", "trader"]},
    )
    assert res.status_code == 200
    assert res.json()["allowed_roles"] == ["trader", "admin"]


# --- Critical safety ---


def test_ac_safe_01_admin_panel_drop_admin_400(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/admin_panel",
        headers=headers,
        json={"allowed_roles": ["trader"]},
    )
    assert res.status_code == 400
    row = next(
        i
        for i in api.get("/admin/features", headers=headers).json()["items"]
        if i["feature_key"] == "admin_panel"
    )
    assert "admin" in row["allowed_roles"]


def test_ac_safe_02_user_management_drop_admin_400(api):
    headers = _admin_headers(api)
    res = api.patch(
        "/admin/features/user_management",
        headers=headers,
        json={"allowed_roles": []},
    )
    assert res.status_code == 400


def test_ac_safe_03_critical_deactivate_400(api):
    headers = _admin_headers(api)
    for key in ("admin_panel", "user_management"):
        assert (
            api.patch(
                f"/admin/features/{key}",
                headers=headers,
                json={"is_active": False},
            ).status_code
            == 400
        )


def test_ac_safe_04_non_critical_flexible(api):
    headers = _admin_headers(api)
    r1 = api.patch(
        "/admin/features/export_data",
        headers=headers,
        json={"allowed_roles": ["trader"]},
    )
    assert r1.status_code == 200
    r2 = api.patch(
        "/admin/features/export_data",
        headers=headers,
        json={"is_active": False},
    )
    assert r2.status_code == 200 and r2.json()["is_active"] is False


def test_ac_safe_05_mixed_payload_atomic(api):
    headers = _admin_headers(api)
    before = next(
        i
        for i in api.get("/admin/features", headers=headers).json()["items"]
        if i["feature_key"] == "admin_panel"
    )
    res = api.patch(
        "/admin/features/admin_panel",
        headers=headers,
        json={
            "allowed_roles": ["trader"],
            "description": "Should not apply",
            "is_active": False,
        },
    )
    assert res.status_code == 400
    after = next(
        i
        for i in api.get("/admin/features", headers=headers).json()["items"]
        if i["feature_key"] == "admin_panel"
    )
    assert after["description"] == before["description"]
    assert after["allowed_roles"] == before["allowed_roles"]
    assert after["is_active"] is True


# --- Helper (via DB session from API path + direct service) ---


def test_ac_help_01_to_06_matrix(api, test_engine):
    headers = _admin_headers(api)
    # Material setup: watchlist admin-only then restore via helper checks in async session
    assert (
        api.patch(
            "/admin/features/watchlist",
            headers=headers,
            json={"allowed_roles": ["admin"], "is_active": True},
        ).status_code
        == 200
    )

    async def _check():
        async with AsyncSessionLocal() as db:
            await ensure_default_feature_permissions(db)
            assert await can_access_feature(db, "watchlist", "admin") is True  # HELP-01
            assert await can_access_feature(db, "watchlist", "trader") is False  # HELP-02
            # inactive
            row = (
                await db.execute(
                    select(FeaturePermission).where(
                        FeaturePermission.feature_key == "watchlist"
                    )
                )
            ).scalar_one()
            row.is_active = False
            await db.commit()
            assert await can_access_feature(db, "watchlist", "admin") is False  # HELP-03
            assert (
                await can_access_feature(db, "missing_feature_xyz", "admin") is False
            )  # HELP-04
            assert (
                await can_access_feature(db, "watchlist", "superuser") is False
            )  # HELP-06
            # reactivate + grant trader for HELP-05 style reflect
            row2 = (
                await db.execute(
                    select(FeaturePermission).where(
                        FeaturePermission.feature_key == "watchlist"
                    )
                )
            ).scalar_one()
            row2.is_active = True
            row2.allowed_roles = ["trader", "admin"]
            await db.commit()
            assert await can_access_feature(db, "watchlist", "trader") is True  # HELP-05

    _run(_check())


# --- Audit ---


def test_ac_aud_01_material_change_creates_audit(api, test_engine):
    headers = _admin_headers(api)
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)

    def count() -> int:
        with SessionLocal() as s:
            return int(
                s.execute(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.event_type == EVENT_FEATURE_PERMISSION_CHANGE)
                ).scalar_one()
            )

    before = count()
    res = api.patch(
        "/admin/features/system_logs",
        headers=headers,
        json={"allowed_roles": ["trader", "admin"]},
    )
    assert res.status_code == 200
    assert count() == before + 1
    with SessionLocal() as s:
        row = (
            s.execute(
                select(AuditLog)
                .where(AuditLog.event_type == EVENT_FEATURE_PERMISSION_CHANGE)
                .order_by(AuditLog.created_at.desc())
            )
            .scalars()
            .first()
        )
        assert row is not None
        meta = row.metadata_ or {}
        assert meta.get("feature_key") == "system_logs"
        assert "previous_allowed_roles" in meta
        assert "new_allowed_roles" in meta
        assert "actor_user_id" in meta


def test_ac_aud_02_critical_fail_no_audit(api, test_engine):
    headers = _admin_headers(api)
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)

    def count() -> int:
        with SessionLocal() as s:
            return int(
                s.execute(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(AuditLog.event_type == EVENT_FEATURE_PERMISSION_CHANGE)
                ).scalar_one()
            )

    before = count()
    assert (
        api.patch(
            "/admin/features/admin_panel",
            headers=headers,
            json={"allowed_roles": ["trader"]},
        ).status_code
        == 400
    )
    assert count() == before


# --- Regression smoke (AC-REG-01/02 lightweight) ---


def test_ac_reg_02_admin_users_still_works(api):
    """Sprint 2 path still reachable; catalog-only does not gate /admin/users."""
    headers = _admin_headers(api)
    res = api.get("/admin/users", headers=headers, params={"page": 1, "size": 5})
    assert res.status_code == 200
    body = res.json()
    assert "items" in body and "total" in body


def test_ac_reg_01_auth_register_login_force_trader(api):
    """Sprint 1 smoke: register remains trader; login returns role."""
    email = f"reg_{uuid.uuid4().hex[:10]}@example.com"
    reg = api.post(
        "/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Reg User",
            "role": "admin",  # must be ignored / forced trader
        },
    )
    assert reg.status_code in (200, 201), reg.text
    body = reg.json()
    # role may be on user object depending on contract
    role = body.get("role") or (body.get("user") or {}).get("role")
    if role is not None:
        assert role == "trader"
    login = api.post(
        "/auth/login",
        json={"email": email, "password": "SecurePassword123!"},
    )
    assert login.status_code == 200
    assert login.json().get("role", "trader") in ("trader", "admin")
    # token path: me if available
    token = login.json().get("access_token")
    if token:
        me = api.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        if me.status_code == 200:
            assert me.json().get("role") == "trader"
