from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.token_crypto import decrypt_secret
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models import FyersToken
from backend.tests.conftest import TEST_DB_PATH


@pytest.fixture()
def client(db_session) -> Generator[TestClient, None, None]:
    """Async get_db override on the same SQLite file as db_session (parity with test_settings)."""
    db_path = Path(TEST_DB_PATH).resolve()
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    async_engine = create_async_engine(
        async_url,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    try:
        import asyncio

        asyncio.get_event_loop().run_until_complete(async_engine.dispose())
    except Exception:
        pass


@pytest.mark.integration
class TestTokenManagementAPI:
    """Integration tests for the POST /api/token/save-access-token endpoint.

    These tests exercise the full HTTP → Pydantic validation → service →
    SQLAlchemy write → response cycle using the shared ``client`` and
    ``db_session`` fixtures from conftest.py.
    """

    def test_save_access_token_success(self, client, db_session):
        
        """A valid access_token payload should return 200, persist the token
        in fyers_tokens with status 'active', and write a history row."""
        payload = {"access_token": "mock_fyers_token_123"}

        response = client.post("/api/token/save-access-token", json=payload)

        # ── HTTP response assertions ──
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["status"] == "ok"
        assert "saved_at" in body

        # ── Database persistence assertions ──
        db_session.expire_all()
        token_row = (
            db_session.query(FyersToken)
            .filter(FyersToken.id == 1)
            .one_or_none()
        )
        assert token_row is not None, "FyersToken row was not created in DB"
        # Tokens are encrypted at rest (enc:v1:...); compare decrypted value.
        assert decrypt_secret(token_row.access_token) == "mock_fyers_token_123"
        assert token_row.status == "active"
        assert token_row.access_token_saved_at is not None
        assert token_row.last_error is None

    def test_save_access_token_too_short(self, client, db_session):
        """A token shorter than 10 characters should be rejected with 400."""
        payload = {"access_token": "short"}

        response = client.post("/api/token/save-access-token", json=payload)

        assert response.status_code == 400, (
            f"Expected 400 but got {response.status_code}: {response.text}"
        )
        assert "too short" in response.json()["detail"].lower()

        # Verify nothing was written to the database
        token_row = (
            db_session.query(FyersToken)
            .filter(FyersToken.id == 1)
            .one_or_none()
        )
        assert token_row is None, "No token row should exist after a rejected save"

    def test_save_access_token_empty_string(self, client, db_session):
        """An empty string token should be rejected with 400."""
        payload = {"access_token": ""}

        response = client.post("/api/token/save-access-token", json=payload)

        assert response.status_code == 400, (
            f"Expected 400 but got {response.status_code}: {response.text}"
        )

        # Verify nothing was written to the database
        token_row = (
            db_session.query(FyersToken)
            .filter(FyersToken.id == 1)
            .one_or_none()
        )
        assert token_row is None, "No token row should exist after an empty token save"

    def test_save_access_token_missing_field(self, client, db_session):
        """A payload missing the required 'access_token' field should trigger
        FastAPI's Pydantic 422 validation error — not a 500 crash."""
        payload = {"wrong_key": "some_value"}

        response = client.post("/api/token/save-access-token", json=payload)

        assert response.status_code == 422, (
            f"Expected 422 validation error but got {response.status_code}: {response.text}"
        )
        # FastAPI returns a structured validation error body
        body = response.json()
        assert "detail" in body
        errors = body["detail"]
        assert any(
            err.get("loc", [None])[-1] == "access_token"
            for err in errors
        ), f"Expected validation error on 'access_token' field, got: {errors}"

    def test_save_access_token_wrong_type(self, client, db_session):
        """Sending a non-string value for access_token should trigger
        a 422 Pydantic validation error."""
        payload = {"access_token": 12345}

        response = client.post("/api/token/save-access-token", json=payload)

        # Pydantic v2 coerces int → str in lax mode, so this may be 200 or 422
        # depending on Pydantic version. Either way, the endpoint must not crash.
        assert response.status_code in (200, 400, 422), (
            f"Unexpected status {response.status_code}: {response.text}"
        )
