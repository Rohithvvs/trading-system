"""
Sprint 2 comprehensive AC matrix — specs/023-admin-user-apis.

Maps acceptance criteria IDs to executable checks. Complements focused modules.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.core.roles import UserRole
from app.core.security import get_password_hash
from app.models.auth import AuditLog, User
from app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
from app.services.admin_user_service import EVENT_ADMIN_ROLE_CHANGE
from app.db.session import AsyncSessionLocal


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def api(test_engine):
    with TestClient(app) as c:
        yield c


def _seed_and_admin(api: TestClient) -> tuple[dict, dict]:
    async def _seed():
        async with AsyncSessionLocal() as db:
            await ensure_default_admin(db)

    _run(_seed())
    login = api.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    body = login.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    return headers, body


def _register(api: TestClient, email: str | None = None, full_name: str = "User") -> dict:
    email = email or f"u_{uuid.uuid4().hex[:8]}@example.com"
    res = api.post(
        "/auth/register",
        json={"email": email, "password": "SecurePassword123!", "full_name": full_name},
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


# --- Authorization (AC-AUTH-*) ---


def test_ac_auth_01_unauthenticated_list_401(api):
    assert api.get("/admin/users").status_code == 401


def test_ac_auth_02_trader_list_403(api):
    t = _register(api)
    assert (
        api.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {t['access_token']}"},
        ).status_code
        == 403
    )


def test_ac_auth_03_admin_list_200(api):
    headers, _ = _seed_and_admin(api)
    assert api.get("/admin/users", headers=headers).status_code == 200


def test_ac_auth_04_stale_jwt_after_demotion_403(api):
    headers, _ = _seed_and_admin(api)
    second = _register(api)
    assert (
        api.patch(
            f"/admin/users/{second['id']}/role",
            json={"role": "admin"},
            headers=headers,
        ).status_code
        == 200
    )
    login2 = api.post(
        "/auth/login",
        json={"email": second["email"], "password": "SecurePassword123!"},
    )
    token2 = login2.json()["access_token"]
    assert (
        api.patch(
            f"/admin/users/{second['id']}/role",
            json={"role": "trader"},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        api.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {token2}"},
        ).status_code
        == 403
    )


def test_ac_auth_05_patch_unauth_and_trader(api):
    assert (
        api.patch(
            f"/admin/users/{uuid.uuid4()}/role",
            json={"role": "admin"},
        ).status_code
        == 401
    )
    t = _register(api)
    assert (
        api.patch(
            f"/admin/users/{t['id']}/role",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {t['access_token']}"},
        ).status_code
        == 403
    )


# --- List (AC-LIST-*) ---


def test_ac_list_01_defaults_and_shape(api):
    headers, _ = _seed_and_admin(api)
    body = api.get("/admin/users", headers=headers).json()
    assert body["page"] == 1 and body["size"] == 20
    assert {"items", "total", "page", "size"} <= set(body.keys())


def test_ac_list_02_size_max_422(api):
    headers, _ = _seed_and_admin(api)
    assert api.get("/admin/users", params={"size": 101}, headers=headers).status_code == 422


def test_ac_list_03_search_email_and_name(api):
    headers, _ = _seed_and_admin(api)
    _register(api, email=f"searchme_{uuid.uuid4().hex[:6]}@example.com", full_name="UniqueSearchName")
    by_email = api.get("/admin/users", params={"search": "searchme_"}, headers=headers)
    by_name = api.get("/admin/users", params={"search": "uniquesearchname"}, headers=headers)
    assert by_email.status_code == 200 and by_email.json()["total"] >= 1
    assert by_name.status_code == 200 and by_name.json()["total"] >= 1


def test_ac_list_04_role_filter(api):
    headers, _ = _seed_and_admin(api)
    _register(api)
    traders = api.get("/admin/users", params={"role": "trader"}, headers=headers)
    admins = api.get("/admin/users", params={"role": "admin"}, headers=headers)
    assert traders.status_code == 200 and all(i["role"] == "trader" for i in traders.json()["items"])
    assert admins.status_code == 200 and all(i["role"] == "admin" for i in admins.json()["items"])


def test_ac_list_05_excludes_inactive_and_soft_deleted(api, test_engine):
    headers, _ = _seed_and_admin(api)
    inactive_email = f"inact_{uuid.uuid4().hex[:6]}@example.com"
    deleted_email = f"del_{uuid.uuid4().hex[:6]}@example.com"
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        s.add_all(
            [
                User(
                    id=uuid.uuid4(),
                    email=inactive_email,
                    full_name="Inact",
                    password_hash=get_password_hash("Password123!"),
                    role=UserRole.TRADER.value,
                    is_active=False,
                    provider="email",
                ),
                User(
                    id=uuid.uuid4(),
                    email=deleted_email,
                    full_name="Del",
                    password_hash=get_password_hash("Password123!"),
                    role=UserRole.TRADER.value,
                    is_active=True,
                    provider="email",
                    deleted_at=datetime.now(timezone.utc),
                ),
            ]
        )
        s.commit()
    items = api.get("/admin/users", headers=headers).json()["items"]
    emails = {i["email"] for i in items}
    assert inactive_email not in emails
    assert deleted_email not in emails


def test_ac_list_06_item_fields(api):
    headers, _ = _seed_and_admin(api)
    items = api.get("/admin/users", headers=headers).json()["items"]
    assert items
    required = {"id", "email", "full_name", "role", "is_active", "created_at"}
    for item in items:
        assert required <= set(item.keys())
        assert "password_hash" not in item


# --- Role (AC-ROLE-*) ---


def test_ac_role_01_promote(api):
    headers, _ = _seed_and_admin(api)
    t = _register(api)
    res = api.patch(f"/admin/users/{t['id']}/role", json={"role": "admin"}, headers=headers)
    assert res.status_code == 200 and res.json()["role"] == "admin"


def test_ac_role_02_demote_non_last(api):
    headers, _ = _seed_and_admin(api)
    t = _register(api)
    assert (
        api.patch(f"/admin/users/{t['id']}/role", json={"role": "admin"}, headers=headers).status_code
        == 200
    )
    res = api.patch(f"/admin/users/{t['id']}/role", json={"role": "trader"}, headers=headers)
    assert res.status_code == 200 and res.json()["role"] == "trader"


def test_ac_role_03_invalid_role_422(api):
    headers, _ = _seed_and_admin(api)
    t = _register(api)
    assert (
        api.patch(
            f"/admin/users/{t['id']}/role",
            json={"role": "superuser"},
            headers=headers,
        ).status_code
        == 422
    )


def test_ac_role_04_unknown_404(api):
    headers, _ = _seed_and_admin(api)
    assert (
        api.patch(
            f"/admin/users/{uuid.uuid4()}/role",
            json={"role": "admin"},
            headers=headers,
        ).status_code
        == 404
    )


def test_ac_role_05_inactive_and_soft_deleted_404(api, test_engine):
    headers, _ = _seed_and_admin(api)
    inactive_id = uuid.uuid4()
    deleted_id = uuid.uuid4()
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        s.add_all(
            [
                User(
                    id=inactive_id,
                    email=f"ri_{uuid.uuid4().hex[:6]}@example.com",
                    full_name="I",
                    password_hash=get_password_hash("Password123!"),
                    role=UserRole.TRADER.value,
                    is_active=False,
                    provider="email",
                ),
                User(
                    id=deleted_id,
                    email=f"rd_{uuid.uuid4().hex[:6]}@example.com",
                    full_name="D",
                    password_hash=get_password_hash("Password123!"),
                    role=UserRole.TRADER.value,
                    is_active=True,
                    provider="email",
                    deleted_at=datetime.now(timezone.utc),
                ),
            ]
        )
        s.commit()
    assert (
        api.patch(
            f"/admin/users/{inactive_id}/role",
            json={"role": "admin"},
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        api.patch(
            f"/admin/users/{deleted_id}/role",
            json={"role": "admin"},
            headers=headers,
        ).status_code
        == 404
    )
    with SessionLocal() as s:
        assert s.get(User, inactive_id).role == UserRole.TRADER.value
        assert s.get(User, deleted_id).role == UserRole.TRADER.value


def test_ac_role_06_noop_no_audit(api, test_engine):
    headers, _ = _seed_and_admin(api)
    t = _register(api)
    res = api.patch(f"/admin/users/{t['id']}/role", json={"role": "trader"}, headers=headers)
    assert res.status_code == 200
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        logs = s.execute(select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)).scalars().all()
        assert not any((lg.metadata_ or {}).get("target_user_id") == t["id"] for lg in logs)


# --- Last admin (AC-LAST-*) ---


def test_ac_last_01_self_demote_blocked(api, test_engine):
    headers, admin = _seed_and_admin(api)
    res = api.patch(
        f"/admin/users/{admin['id']}/role",
        json={"role": "trader"},
        headers=headers,
    )
    assert res.status_code == 400
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        assert s.get(User, uuid.UUID(admin["id"])).role == UserRole.ADMIN.value


def test_ac_last_02_demote_with_two_admins(api):
    headers, admin = _seed_and_admin(api)
    t = _register(api)
    assert (
        api.patch(f"/admin/users/{t['id']}/role", json={"role": "admin"}, headers=headers).status_code
        == 200
    )
    res = api.patch(
        f"/admin/users/{admin['id']}/role",
        json={"role": "trader"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["role"] == "trader"


def test_ac_last_03_inactive_admin_does_not_count(api, test_engine):
    headers, admin = _seed_and_admin(api)
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        s.add(
            User(
                id=uuid.uuid4(),
                email=f"ia_{uuid.uuid4().hex[:6]}@example.com",
                full_name="Inactive Admin",
                password_hash=get_password_hash("Password123!"),
                role=UserRole.ADMIN.value,
                is_active=False,
                provider="email",
            )
        )
        s.commit()
    res = api.patch(
        f"/admin/users/{admin['id']}/role",
        json={"role": "trader"},
        headers=headers,
    )
    assert res.status_code == 400


# --- Audit (AC-AUD-*) ---


def test_ac_aud_01_real_change_audit(api, test_engine):
    headers, admin = _seed_and_admin(api)
    t = _register(api)
    assert (
        api.patch(f"/admin/users/{t['id']}/role", json={"role": "admin"}, headers=headers).status_code
        == 200
    )
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        logs = s.execute(select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)).scalars().all()
        match = [lg for lg in logs if (lg.metadata_ or {}).get("target_user_id") == t["id"]]
        assert len(match) == 1
        meta = match[0].metadata_
        assert meta["actor_user_id"] == admin["id"]
        assert meta["previous_role"] == "trader"
        assert meta["new_role"] == "admin"


def test_ac_aud_02_last_admin_no_audit(api, test_engine):
    headers, admin = _seed_and_admin(api)
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        before = len(
            s.execute(select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)).scalars().all()
        )
    assert (
        api.patch(
            f"/admin/users/{admin['id']}/role",
            json={"role": "trader"},
            headers=headers,
        ).status_code
        == 400
    )
    with SessionLocal() as s:
        after = len(
            s.execute(select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)).scalars().all()
        )
    assert after == before
