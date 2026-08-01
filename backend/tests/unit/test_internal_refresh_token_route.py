"""Unit tests for POST /internal/refresh-fyers-token route (isolated app).

Mirrors the style of test_token_generate_api.py: minimal FastAPI app with only
the internal_router, so auth and response contracts can be verified without
loading the full application stack.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.token import internal_router


ENDPOINT = "/internal/refresh-fyers-token"
SECRET = "test-cron-secret"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
    application = FastAPI()
    application.include_router(internal_router)

    async def _fake_db():
        yield AsyncMock()

    from backend.app.db import get_db

    application.dependency_overrides[get_db] = _fake_db
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.mark.unit
def test_internal_refresh_requires_secret_header(client):
    res = client.post(ENDPOINT)
    assert res.status_code == 401
    assert res.json() == {"detail": "Unauthorized"}


@pytest.mark.unit
def test_internal_refresh_rejects_bad_secret(client):
    res = client.post(
        ENDPOINT,
        headers={"X-Scheduler-Secret": "wrong"},
    )
    assert res.status_code == 403
    assert res.json() == {"detail": "Forbidden"}


@pytest.mark.unit
def test_internal_refresh_success_contract(client):
    with patch(
        "backend.app.services.token_service.generate_and_persist_fyers_token",
        new_callable=AsyncMock,
    ) as gen:
        gen.return_value = {
            "status": "Success",
            "saved_at": "2026-07-21T00:00:00+00:00",
            "token_preview": "****************ABCD",
        }
        res = client.post(
            ENDPOINT,
            headers={"X-Scheduler-Secret": SECRET},
        )

    assert res.status_code == 200
    assert res.json() == {
        "status": "success",
        "message": "Access token generated and saved successfully",
    }
    gen.assert_awaited_once()


@pytest.mark.unit
def test_internal_refresh_failure_contract(client):
    with patch(
        "backend.app.services.token_service.generate_and_persist_fyers_token",
        new_callable=AsyncMock,
    ) as gen:
        gen.side_effect = Exception("broker timeout after retries")
        res = client.post(
            ENDPOINT,
            headers={"X-Scheduler-Secret": SECRET},
        )

    assert res.status_code == 500
    assert res.json() == {
        "status": "error",
        "message": "Failed to generate access token after retries",
    }
    gen.assert_awaited_once()


@pytest.mark.unit
def test_internal_refresh_passes_db_session_to_service(client):
    """Route must pass the DI session into generate_and_persist_fyers_token."""
    with patch(
        "backend.app.services.token_service.generate_and_persist_fyers_token",
        new_callable=AsyncMock,
    ) as gen:
        gen.return_value = {"status": "Success"}
        res = client.post(
            ENDPOINT,
            headers={"X-Scheduler-Secret": SECRET},
        )

    assert res.status_code == 200
    gen.assert_awaited_once()
    assert gen.await_args is not None
    assert len(gen.await_args.args) == 1


@pytest.mark.unit
def test_internal_refresh_does_not_return_service_payload_fields(client):
    """Route response is the fixed contract, not a passthrough of service dict."""
    with patch(
        "backend.app.services.token_service.generate_and_persist_fyers_token",
        new_callable=AsyncMock,
    ) as gen:
        gen.return_value = {
            "status": "Success",
            "token_preview": "****************ABCD",
            "access_token": "should-not-appear",
            "extra_field": "nope",
        }
        res = client.post(
            ENDPOINT,
            headers={"X-Scheduler-Secret": SECRET},
        )

    body = res.json()
    assert body == {
        "status": "success",
        "message": "Access token generated and saved successfully",
    }
    assert "token_preview" not in body
    assert "access_token" not in body
    assert "extra_field" not in body


@pytest.mark.unit
def test_require_scheduler_secret_uses_env_not_hardcoded(monkeypatch):
    """FR-005: secret is resolved from SCHEDULER_SECRET env var."""
    from backend.app.routes.token import _require_scheduler_secret
    from fastapi import HTTPException
    from starlette.requests import Request
    from unittest.mock import MagicMock

    monkeypatch.setenv("SCHEDULER_SECRET", "env-only-secret")
    request = MagicMock(spec=Request)
    request.client = MagicMock()
    request.client.host = "127.0.0.1"

    # Matching env value is accepted (no exception).
    _require_scheduler_secret(request, "env-only-secret")

    with pytest.raises(HTTPException) as exc_info:
        _require_scheduler_secret(request, "different-value")
    assert exc_info.value.status_code == 403
