"""Integration tests for GET /admin/users (Sprint 2 US1/US2)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.core.roles import UserRole
from app.core.security import get_password_hash
from app.models.auth import User
from app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
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


def _admin_headers(api: TestClient) -> dict:
    _seed_admin()
    res = api.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _register_trader(api: TestClient, email: str | None = None, full_name: str = "Trader") -> dict:
    email = email or _unique_email("trader")
    res = api.post(
        "/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": full_name,
        },
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


def test_list_users_unauthenticated_401(api):
    assert api.get("/admin/users").status_code == 401


def test_list_users_trader_403(api):
    trader = _register_trader(api)
    res = api.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {trader['access_token']}"},
    )
    assert res.status_code == 403


def test_list_users_admin_200(api):
    headers = _admin_headers(api)
    res = api.get("/admin/users", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["page"] == 1
    assert body["size"] == 20
    assert "items" in body and "total" in body
    for item in body["items"]:
        assert {"id", "email", "full_name", "role", "is_active", "created_at"} <= set(item.keys())
        assert "password_hash" not in item


def test_list_users_pagination_and_size_max(api):
    headers = _admin_headers(api)
    ok = api.get("/admin/users", params={"page": 1, "size": 20}, headers=headers)
    assert ok.status_code == 200
    assert ok.json()["size"] == 20
    assert api.get("/admin/users", params={"size": 101}, headers=headers).status_code == 422
    assert api.get("/admin/users", params={"page": 0}, headers=headers).status_code == 422


def test_list_users_search_and_role_filter(api):
    headers = _admin_headers(api)
    _register_trader(api, email=_unique_email("findme"), full_name="Findable Name")

    res = api.get("/admin/users", params={"search": "findme"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 1
    assert any("findme" in i["email"] for i in res.json()["items"])

    res_role = api.get("/admin/users", params={"role": "admin"}, headers=headers)
    assert res_role.status_code == 200
    assert all(i["role"] == "admin" for i in res_role.json()["items"])

    assert (
        api.get("/admin/users", params={"role": "superuser"}, headers=headers).status_code
        == 422
    )


def test_list_users_empty_search_is_noop(api):
    headers = _admin_headers(api)
    full = api.get("/admin/users", headers=headers)
    empty = api.get("/admin/users", params={"search": "   "}, headers=headers)
    assert full.status_code == 200 and empty.status_code == 200
    assert full.json()["total"] == empty.json()["total"]


def test_list_users_excludes_inactive(api, test_engine):
    headers = _admin_headers(api)
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        s.add(
            User(
                id=uuid.uuid4(),
                email=_unique_email("inactive"),
                full_name="Inactive",
                password_hash=get_password_hash("Password123!"),
                role=UserRole.TRADER.value,
                is_active=False,
                provider="email",
            )
        )
        s.commit()

    res = api.get("/admin/users", headers=headers)
    assert res.status_code == 200
    assert all(i["is_active"] for i in res.json()["items"])
    assert all("inactive" not in i["email"] for i in res.json()["items"])


def test_list_users_via_cookie_session(api):
    _seed_admin()
    login = api.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    res = api.get("/admin/users")  # cookie from login
    assert res.status_code == 200, res.text


def test_list_users_search_by_full_name_case_insensitive(api):
    """AC-LIST-03: search matches full_name (case-insensitive partial)."""
    headers = _admin_headers(api)
    _register_trader(api, email=_unique_email("fn"), full_name="Zephyr UniqueName")

    res = api.get(
        "/admin/users",
        params={"search": "zephyr uniquename"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["total"] >= 1
    assert any("Zephyr" in i["full_name"] for i in res.json()["items"])


def test_list_users_role_filter_trader(api):
    """AC-LIST-04: role=trader filter returns only traders."""
    headers = _admin_headers(api)
    _register_trader(api)
    res = api.get("/admin/users", params={"role": "trader"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 1
    assert all(i["role"] == "trader" for i in res.json()["items"])


def test_list_users_excludes_soft_deleted(api, test_engine):
    """AC-LIST-05: soft-deleted users excluded from default list."""
    headers = _admin_headers(api)
    deleted_email = _unique_email("softdel")
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        from datetime import datetime, timezone

        s.add(
            User(
                id=uuid.uuid4(),
                email=deleted_email,
                full_name="Soft Deleted",
                password_hash=get_password_hash("Password123!"),
                role=UserRole.TRADER.value,
                is_active=True,
                provider="email",
                deleted_at=datetime.now(timezone.utc),
            )
        )
        s.commit()

    res = api.get("/admin/users", headers=headers)
    assert res.status_code == 200
    assert all(i["email"] != deleted_email for i in res.json()["items"])


def test_list_users_size_boundary_one(api):
    """Edge: size=1 is valid lower bound."""
    headers = _admin_headers(api)
    res = api.get("/admin/users", params={"page": 1, "size": 1}, headers=headers)
    assert res.status_code == 200
    assert res.json()["size"] == 1
    assert len(res.json()["items"]) <= 1


def test_list_users_high_page_returns_empty_items(api):
    """Edge: page beyond data returns empty items, stable total."""
    headers = _admin_headers(api)
    res = api.get(
        "/admin/users",
        params={"page": 9999, "size": 20},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert body["total"] >= 0
    assert body["page"] == 9999


def test_list_users_size_100_allowed(api):
    """Boundary: size=100 is the maximum allowed (not 422)."""
    headers = _admin_headers(api)
    res = api.get("/admin/users", params={"page": 1, "size": 100}, headers=headers)
    assert res.status_code == 200
    assert res.json()["size"] == 100


def test_soft_deleted_admin_session_forbidden_on_admin_and_me(api, test_engine):
    """
    Soft-deleted principal with a still-valid JWT cannot use protected APIs
    (get_current_active_user / admin gate).
    """
    from datetime import datetime, timezone
    from app.core.security import create_access_token

    uid = uuid.uuid4()
    email = _unique_email("softdel_admin")
    SessionLocal = sessionmaker(bind=test_engine, class_=Session)
    with SessionLocal() as s:
        s.add(
            User(
                id=uid,
                email=email,
                full_name="Soft Del Admin",
                password_hash=get_password_hash("Password123!"),
                role=UserRole.ADMIN.value,
                is_active=True,
                provider="email",
                deleted_at=datetime.now(timezone.utc),
            )
        )
        s.commit()

    token, _ = create_access_token({"sub": str(uid), "role": "admin"})
    headers = {"Authorization": f"Bearer {token}"}
    assert api.get("/admin/users", headers=headers).status_code == 403
    assert api.get("/auth/me", headers=headers).status_code == 403
