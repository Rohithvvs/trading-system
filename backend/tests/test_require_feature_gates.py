"""Sprint 5 M-5: backend require_feature gates on product surfaces."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.auth import User
from app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
from app.services.feature_permission_service import (
    ensure_default_feature_permissions,
    update_feature_permission,
)


def _run(coro):
    return asyncio.run(coro)


async def _bootstrap() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_default_admin(db)
        await ensure_default_feature_permissions(db, commit=True)
        await db.commit()


@pytest.fixture()
def api(test_engine):
    _run(_bootstrap())
    with TestClient(app) as c:
        yield c


def _admin_headers(api: TestClient) -> dict:
    res = api.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _register_trader(api: TestClient) -> dict:
    email = f"trader_fg_{uuid.uuid4().hex[:10]}@example.com"
    res = api.post(
        "/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Feature Gate Trader",
        },
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


def test_logs_export_requires_auth(api):
    assert api.get("/api/logs/export?format=csv").status_code == 401


def test_logs_export_trader_denied(api):
    trader = _register_trader(api)
    headers = {"Authorization": f"Bearer {trader['access_token']}"}
    res = api.get("/api/logs/export?format=csv", headers=headers)
    assert res.status_code == 403


def test_logs_list_admin_allowed(api):
    headers = _admin_headers(api)
    res = api.get("/api/logs?limit=1", headers=headers)
    assert res.status_code == 200, res.text


def test_scanner_latest_requires_advanced_scanner(api):
    trader = _register_trader(api)
    headers = {"Authorization": f"Bearer {trader['access_token']}"}

    async def _restrict():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.email == DEFAULT_ADMIN_EMAIL)
            )
            admin = result.scalar_one()
            await update_feature_permission(
                db,
                actor=admin,
                feature_key="advanced_scanner",
                allowed_roles=["admin"],
            )
            await db.commit()

    _run(_restrict())

    res = api.get("/scanner/latest", headers=headers)
    assert res.status_code == 403
    assert "advanced_scanner" in str(res.json().get("detail", ""))


def test_paper_analytics_respects_portfolio_analytics(api):
    trader = _register_trader(api)
    headers = {"Authorization": f"Bearer {trader['access_token']}"}

    async def _restrict():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.email == DEFAULT_ADMIN_EMAIL)
            )
            admin = result.scalar_one()
            await update_feature_permission(
                db,
                actor=admin,
                feature_key="portfolio_analytics",
                allowed_roles=["admin"],
            )
            await db.commit()

    _run(_restrict())

    # Prefer cookie session if Bearer is flaky on sync routes: set cookie from token
    token = trader["access_token"]
    api.cookies.set("access_token", token)
    res = api.get("/paper-trading/analytics", headers=headers)
    assert res.status_code == 403, res.text
