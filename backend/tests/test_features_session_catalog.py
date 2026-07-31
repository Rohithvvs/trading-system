"""Integration tests for GET /features (Sprint 5 — authenticated catalog)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import AsyncSessionLocal
from app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
from app.services.feature_permission_service import DEFAULT_FEATURES

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
    email = f"trader_{uuid.uuid4().hex[:10]}@example.com"
    res = api.post(
        "/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Features Trader",
        },
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


def test_session_features_unauthenticated_401(api):
    assert api.get("/features").status_code == 401


def test_session_features_trader_200_includes_seed_keys(api):
    trader = _register_trader(api)
    res = api.get(
        "/features",
        headers={"Authorization": f"Bearer {trader['access_token']}"},
    )
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    by_key = {i["feature_key"]: i for i in items}
    for key, roles in SEED_DEFAULTS.items():
        assert key in by_key
        assert by_key[key]["allowed_roles"] == roles


def test_session_features_admin_200(api):
    headers = _admin_headers(api)
    res = api.get("/features", headers=headers)
    assert res.status_code == 200, res.text
    assert len(res.json()["items"]) >= 8  # includes central_command


def test_session_features_reflects_admin_policy_change(api):
    """AC-FEAT-05 path: admin restricts portfolio_analytics; trader catalog updates."""
    admin_headers = _admin_headers(api)
    patch = api.patch(
        "/admin/features/portfolio_analytics",
        headers=admin_headers,
        json={"allowed_roles": ["admin"]},
    )
    assert patch.status_code == 200, patch.text

    trader = _register_trader(api)
    res = api.get(
        "/features",
        headers={"Authorization": f"Bearer {trader['access_token']}"},
    )
    assert res.status_code == 200
    by_key = {i["feature_key"]: i for i in res.json()["items"]}
    assert by_key["portfolio_analytics"]["allowed_roles"] == ["admin"]
