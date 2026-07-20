"""Unit tests for POST /api/token/generate (cron token automation)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.token import router as token_router


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SCHEDULER_SECRET", "test-cron-secret")
    application = FastAPI()
    application.include_router(token_router)

    # Override DB dependency used by the route
    async def _fake_db():
        yield AsyncMock()

    from backend.app.db import get_db

    application.dependency_overrides[get_db] = _fake_db
    return application


@pytest.mark.unit
def test_generate_requires_secret_header(app):
    client = TestClient(app)
    res = client.post("/api/token/generate")
    assert res.status_code == 401


@pytest.mark.unit
def test_generate_rejects_bad_secret(app):
    client = TestClient(app)
    res = client.post(
        "/api/token/generate",
        headers={"X-Scheduler-Secret": "wrong"},
    )
    assert res.status_code == 403


@pytest.mark.unit
def test_generate_success_does_not_return_raw_token(app):
    client = TestClient(app)
    with patch(
        "backend.app.services.token_service.generate_and_persist_fyers_token",
        new_callable=AsyncMock,
    ) as gen, patch(
        "backend.app.services.token_service.get_token_status",
        new_callable=AsyncMock,
    ) as status:
        gen.return_value = {
            "status": "Success",
            "saved_at": "2026-07-20T10:00:00+00:00",
            "token_preview": "********************ABCD",
        }
        status.return_value = {
            "connection_status": "Connected",
            "access_token_active": True,
            "expires_at": "2026-07-21T00:30:00+00:00",
        }
        res = client.post(
            "/api/token/generate",
            headers={"X-Scheduler-Secret": "test-cron-secret"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "Success"
    assert body["token_preview"] == "********************ABCD"
    assert body["connection_status"] == "Connected"
    assert "access_token" not in body or body.get("access_token") in (None, "")
    # Ensure nothing JWT-like leaked
    assert "eyJ" not in res.text
