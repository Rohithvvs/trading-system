"""Integration tests for PATCH /admin/users/{id}/role (Sprint 2 US3–US5)."""

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
from app.core.security import get_password_hash, create_access_token
from app.models.auth import AuditLog, User
from app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
from app.services.admin_user_service import EVENT_ADMIN_ROLE_CHANGE
from app.db.session import AsyncSessionLocal


def _unique_email(prefix: str = "u") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}@example.com"


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


def _admin_login(api: TestClient) -> dict:
    _seed_admin()
    res = api.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _admin_headers(api: TestClient) -> dict:
    body = _admin_login(api)
    return {"Authorization": f"Bearer {body['access_token']}"}, body


def _register(api: TestClient, email: str | None = None) -> dict:
    email = email or _unique_email("reg")
    res = api.post(
        "/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Reg User",
        },
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


def test_patch_role_unauthenticated_401(api):
    res = api.patch(
        f"/admin/users/{uuid.uuid4()}/role",
        json={"role": "admin"},
    )
    assert res.status_code == 401


def test_patch_role_trader_403(api):
    trader = _register(api)
    res = api.patch(
        f"/admin/users/{trader['id']}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {trader['access_token']}"},
    )
    assert res.status_code == 403


def test_promote_trader_to_admin(api):
    headers, _ = _admin_headers(api)
    trader = _register(api)
    res = api.patch(
        f"/admin/users/{trader['id']}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["role"] == "admin"
    assert res.json()["id"] == trader["id"]


def test_demote_non_last_admin(api, test_engine):
    headers, admin_body = _admin_headers(api)
    # Promote a second admin
    trader = _register(api)
    promo = api.patch(
        f"/admin/users/{trader['id']}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert promo.status_code == 200

    # Demote the second admin back to trader
    demote = api.patch(
        f"/admin/users/{trader['id']}/role",
        json={"role": "trader"},
        headers=headers,
    )
    assert demote.status_code == 200, demote.text
    assert demote.json()["role"] == "trader"


def test_invalid_role_422(api):
    headers, _ = _admin_headers(api)
    trader = _register(api)
    res = api.patch(
        f"/admin/users/{trader['id']}/role",
        json={"role": "superuser"},
        headers=headers,
    )
    assert res.status_code == 422


def test_missing_user_404(api):
    headers, _ = _admin_headers(api)
    res = api.patch(
        f"/admin/users/{uuid.uuid4()}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert res.status_code == 404


def test_inactive_target_404(api, test_engine):
    """AC-ROLE-05: inactive target → 404; role unchanged."""
    headers, _ = _admin_headers(api)
    inactive_id = uuid.uuid4()
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        s.add(
            User(
                id=inactive_id,
                email=_unique_email("inactive_tgt"),
                full_name="Inactive T",
                password_hash=get_password_hash("Password123!"),
                role=UserRole.TRADER.value,
                is_active=False,
                provider="email",
            )
        )
        s.commit()

    res = api.patch(
        f"/admin/users/{inactive_id}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert res.status_code == 404
    with SessionLocal() as s:
        row = s.get(User, inactive_id)
        assert row is not None
        assert row.role == UserRole.TRADER.value


def test_soft_deleted_target_404(api, test_engine):
    """AC-ROLE-05: soft-deleted target → 404; role unchanged."""
    headers, _ = _admin_headers(api)
    deleted_id = uuid.uuid4()
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        s.add(
            User(
                id=deleted_id,
                email=_unique_email("del_tgt"),
                full_name="Deleted T",
                password_hash=get_password_hash("Password123!"),
                role=UserRole.TRADER.value,
                is_active=True,
                provider="email",
                deleted_at=datetime.now(timezone.utc),
            )
        )
        s.commit()

    res = api.patch(
        f"/admin/users/{deleted_id}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert res.status_code == 404
    with SessionLocal() as s:
        row = s.get(User, deleted_id)
        assert row is not None
        assert row.role == UserRole.TRADER.value


def test_same_role_noop_no_audit(api, test_engine):
    headers, _ = _admin_headers(api)
    trader = _register(api)
    res = api.patch(
        f"/admin/users/{trader['id']}/role",
        json={"role": "trader"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["role"] == "trader"

    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        logs = (
            s.execute(
                select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)
            )
            .scalars()
            .all()
        )
        # No-op should not add role-change audit for this target
        matching = [
            lg
            for lg in logs
            if (lg.metadata_ or {}).get("target_user_id") == trader["id"]
        ]
        assert matching == []


def test_real_role_change_writes_audit(api, test_engine):
    headers, admin_body = _admin_headers(api)
    trader = _register(api)
    res = api.patch(
        f"/admin/users/{trader['id']}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert res.status_code == 200

    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        logs = (
            s.execute(
                select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)
            )
            .scalars()
            .all()
        )
        matching = [
            lg
            for lg in logs
            if (lg.metadata_ or {}).get("target_user_id") == trader["id"]
        ]
        assert len(matching) == 1
        meta = matching[0].metadata_
        assert meta["previous_role"] == "trader"
        assert meta["new_role"] == "admin"
        assert meta["actor_user_id"] == admin_body["id"]


def test_last_admin_self_demote_400(api, test_engine):
    """AC-LAST-01: sole active admin self-demote → 400; role remains admin."""
    headers, admin_body = _admin_headers(api)
    res = api.patch(
        f"/admin/users/{admin_body['id']}/role",
        json={"role": "trader"},
        headers=headers,
    )
    assert res.status_code == 400
    assert "last active admin" in res.json()["detail"].lower()
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        row = s.get(User, uuid.UUID(admin_body["id"]))
        assert row is not None
        assert row.role == UserRole.ADMIN.value


def test_invalid_user_id_uuid_422(api):
    """Failure: malformed path UUID → 422."""
    headers, _ = _admin_headers(api)
    res = api.patch(
        "/admin/users/not-a-uuid/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert res.status_code == 422


def test_missing_role_body_422(api):
    """Failure: empty body / missing role field → 422."""
    headers, _ = _admin_headers(api)
    trader = _register(api)
    res = api.patch(
        f"/admin/users/{trader['id']}/role",
        json={},
        headers=headers,
    )
    assert res.status_code == 422


def test_last_admin_demote_other_when_sole_400(api, test_engine):
    """Only one active admin: demotion blocked even if another inactive admin exists."""
    headers, admin_body = _admin_headers(api)
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        s.add(
            User(
                id=uuid.uuid4(),
                email=_unique_email("inactive_admin"),
                full_name="Inactive Admin",
                password_hash=get_password_hash("Password123!"),
                role=UserRole.ADMIN.value,
                is_active=False,
                provider="email",
            )
        )
        s.commit()

    res = api.patch(
        f"/admin/users/{admin_body['id']}/role",
        json={"role": "trader"},
        headers=headers,
    )
    assert res.status_code == 400


def test_last_admin_failure_no_audit(api, test_engine):
    headers, admin_body = _admin_headers(api)
    before = 0
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        before = len(
            s.execute(
                select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)
            )
            .scalars()
            .all()
        )

    res = api.patch(
        f"/admin/users/{admin_body['id']}/role",
        json={"role": "trader"},
        headers=headers,
    )
    assert res.status_code == 400

    with SessionLocal() as s:
        after = len(
            s.execute(
                select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)
            )
            .scalars()
            .all()
        )
    assert after == before


def test_stale_jwt_after_demotion_403(api):
    """After demotion, old access token with role=admin claim cannot call admin APIs."""
    headers, admin_body = _admin_headers(api)
    # Create second admin so we can demote someone who has a token
    second = _register(api)
    promo = api.patch(
        f"/admin/users/{second['id']}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert promo.status_code == 200

    # Second user logs in — token has role admin
    login2 = api.post(
        "/auth/login",
        json={"email": second["email"], "password": "SecurePassword123!"},
    )
    assert login2.status_code == 200
    second_token = login2.json()["access_token"]
    second_headers = {"Authorization": f"Bearer {second_token}"}

    # Default admin demotes second
    demote = api.patch(
        f"/admin/users/{second['id']}/role",
        json={"role": "trader"},
        headers=headers,
    )
    assert demote.status_code == 200

    # Stale token still claims admin in JWT but live role is trader
    denied = api.get("/admin/users", headers=second_headers)
    assert denied.status_code == 403

    denied_patch = api.patch(
        f"/admin/users/{admin_body['id']}/role",
        json={"role": "admin"},
        headers=second_headers,
    )
    assert denied_patch.status_code == 403


def test_demote_allowed_with_two_active_admins(api):
    headers, admin_body = _admin_headers(api)
    second = _register(api)
    assert (
        api.patch(
            f"/admin/users/{second['id']}/role",
            json={"role": "admin"},
            headers=headers,
        ).status_code
        == 200
    )
    # Demote original bootstrap admin while second remains
    res = api.patch(
        f"/admin/users/{admin_body['id']}/role",
        json={"role": "trader"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["role"] == "trader"


def test_promote_atomic_role_and_audit(api, test_engine):
    """Hardening M-1: successful promote persists role and audit together."""
    headers, admin_body = _admin_headers(api)
    trader = _register(api)
    res = api.patch(
        f"/admin/users/{trader['id']}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["role"] == "admin"

    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        user = s.get(User, uuid.UUID(trader["id"]))
        assert user is not None and user.role == UserRole.ADMIN.value
        logs = (
            s.execute(
                select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)
            )
            .scalars()
            .all()
        )
        match = [
            lg
            for lg in logs
            if (lg.metadata_ or {}).get("target_user_id") == trader["id"]
            and (lg.metadata_ or {}).get("new_role") == "admin"
            and (lg.metadata_ or {}).get("actor_user_id") == admin_body["id"]
        ]
        assert len(match) == 1


def test_admin_noop_admin_to_admin_no_audit(api, test_engine):
    """AC-ROLE-06: setting admin → admin is no-op without audit noise."""
    headers, admin_body = _admin_headers(api)
    res = api.patch(
        f"/admin/users/{admin_body['id']}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["role"] == "admin"
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        logs = (
            s.execute(
                select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)
            )
            .scalars()
            .all()
        )
        # No audit where previous==new for this target as a pure no-op request
        bad = [
            lg
            for lg in logs
            if (lg.metadata_ or {}).get("target_user_id") == admin_body["id"]
            and (lg.metadata_ or {}).get("previous_role")
            == (lg.metadata_ or {}).get("new_role")
            == "admin"
        ]
        assert bad == []
