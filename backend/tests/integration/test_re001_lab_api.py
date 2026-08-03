"""Integration: RE-001 lab API auth, feature gate, happy paths (FR-014, FR-022)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.recommendation_engine import RecommendationEngineDecision
from app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    ensure_default_admin,
)
from app.services.feature_permission_service import ensure_default_feature_permissions


def _run(coro):
    return asyncio.run(coro)


async def _bootstrap() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_default_admin(db)
        await ensure_default_feature_permissions(db, commit=True)
        await db.commit()


@pytest.fixture()
def api(test_engine):
    from app.models.recommendation_engine import RecommendationEngineDecision

    Base.metadata.create_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine, tables=[RecommendationEngineDecision.__table__])
    _run(_bootstrap())
    with TestClient(app) as c:
        yield c


def _admin_headers(api: TestClient) -> dict:
    res = api.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert res.status_code == 200, res.text
    # Cookie-based auth may also set cookies; support bearer if present
    body = res.json()
    token = body.get("access_token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def test_lab_registration_requires_auth(api):
    assert api.get("/api/v1/recommendation-lab/registration").status_code in (401, 403)


def test_lab_registration_admin_ok(api):
    headers = _admin_headers(api)
    res = api.get("/api/v1/recommendation-lab/registration", headers=headers)
    # Cookie session from TestClient may work without Authorization
    if res.status_code == 401:
        # retry with cookies from login
        login = api.post(
            "/auth/login",
            json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
        )
        assert login.status_code == 200
        res = api.get("/api/v1/recommendation-lab/registration")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["engine_id"] == "RE-001"
    assert data["stage"] in {"OFF", "LAB_SHADOW", "PAPER_LINKED"}


def test_lab_comparison_empty_scan(api):
    login = api.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    res = api.get("/api/v1/recommendation-lab/scans/scan-empty/comparison")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["scan_run_id"] == "scan-empty"
    assert body["items"] == []


def test_lab_decision_not_found(api):
    login = api.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    res = api.get(f"/api/v1/recommendation-lab/decisions/{uuid.uuid4()}")
    assert res.status_code == 404


def test_lab_comparison_returns_seeded_row(api, test_engine, db_session):
    from datetime import datetime, timezone

    from app.db.base import Base

    Base.metadata.create_all(bind=test_engine, tables=[RecommendationEngineDecision.__table__])

    login = api.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert login.status_code == 200

    rid = str(uuid.uuid4())
    db_session.add(
        RecommendationEngineDecision(
            recommendation_id=rid,
            engine_id="RE-001",
            engine_version="1.0",
            symbol="INFY",
            mode="swing",
            scan_run_id="scan-seed-1",
            market_regime="Bull",
            trading_objective="trend_continuation",
            trading_style="long_only_swing",
            strategy_family="Trend Following",
            strategy_name="Trend Following",
            recommendation_state="WATCH",
            confidence_score=0.66,
            evidence={"ok": True},
            explanation="seed",
            reason_codes=[],
            production_action="BUY",
            production_score=75.0,
            is_mismatch=True,
            evaluation_status="success",
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    res = api.get("/api/v1/recommendation-lab/scans/scan-seed-1/comparison")
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert any(i["symbol"] == "INFY" and i["re001_state"] == "WATCH" for i in items)

    detail = api.get(f"/api/v1/recommendation-lab/decisions/{rid}")
    assert detail.status_code == 200
    assert detail.json()["recommendation_id"] == rid
