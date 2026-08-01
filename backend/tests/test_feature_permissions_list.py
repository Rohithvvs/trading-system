"""Integration tests for GET /admin/features (Sprint 3 US1)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.db.session import AsyncSessionLocal
from app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
from app.services.feature_permission_service import DEFAULT_FEATURES


REQUIRED_KEYS = {
    "admin_panel",
    "user_management",
    "system_logs",
    "central_command",
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


def test_list_features_unauthenticated_401(api):
    assert api.get("/admin/features").status_code == 401


def test_list_features_trader_403(api):
    trader = _register_trader(api)
    res = api.get(
        "/admin/features",
        headers={"Authorization": f"Bearer {trader['access_token']}"},
    )
    assert res.status_code == 403


def test_list_features_admin_200_fields_and_order(api):
    headers = _admin_headers(api)
    res = api.get("/admin/features", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "items" in body
    items = body["items"]
    assert len(items) >= 7
    keys = [i["feature_key"] for i in items]
    assert keys == sorted(keys)
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


def test_list_features_seeded_keys_and_roles(api):
    headers = _admin_headers(api)
    res = api.get("/admin/features", headers=headers)
    assert res.status_code == 200
    by_key = {i["feature_key"]: i for i in res.json()["items"]}
    assert REQUIRED_KEYS <= set(by_key.keys())
    for key, expected_roles in SEED_DEFAULTS.items():
        assert by_key[key]["allowed_roles"] == expected_roles


def test_list_features_includes_inactive(api):
    headers = _admin_headers(api)
    # Deactivate non-critical watchlist
    patch = api.patch(
        "/admin/features/watchlist",
        headers=headers,
        json={"is_active": False},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["is_active"] is False

    res = api.get("/admin/features", headers=headers)
    assert res.status_code == 200
    by_key = {i["feature_key"]: i for i in res.json()["items"]}
    assert "watchlist" in by_key
    assert by_key["watchlist"]["is_active"] is False
