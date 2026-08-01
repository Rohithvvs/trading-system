"""Integration tests for FYERS token validation / settings authentication path.

Covers POST /settings/token: rejection, broker validation failures, and success
persist with masking and logging.
"""
from __future__ import annotations

import importlib
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models import FyersToken, FyersTokenHistory
from backend.app.services.token_service import _decrypt_from_storage, _mask_token

try:
    from app.db.session import get_db
    from app.main import app
    import backend.tests.conftest as _conftest
except ModuleNotFoundError:  # pragma: no cover
    from backend.app.db.session import get_db
    from backend.app.main import app
    import backend.tests.conftest as _conftest

# Resolve the module that owns the mounted route (handles app.* vs backend.app.*).
_settings_mod_name = "app.routes.settings"
for _route in app.routes:
    endpoint = getattr(_route, "endpoint", None)
    if endpoint is not None and getattr(endpoint, "__name__", "") == "validate_and_save_token":
        _settings_mod_name = endpoint.__module__
        break
settings_routes = importlib.import_module(_settings_mod_name)


@pytest.fixture()
def client(db_session, test_engine) -> Generator[TestClient, None, None]:
    """TestClient with async get_db on the **same per-test SQLite file** as db_session.

    Uses ``CURRENT_TEST_DB_PATH`` / ``test_engine`` URL so seed rows written via
    the sync fixture are visible to the async route (fixes token deactivate flake).
    """
    db_path = getattr(_conftest, "CURRENT_TEST_DB_PATH", None)
    if db_path is None:
        # Fallback: derive path from the sync test engine URL.
        url = str(test_engine.url)
        db_path = Path(url.replace("sqlite:///", ""))
    else:
        db_path = Path(db_path)

    async_url = f"sqlite+aiosqlite:///{db_path.resolve().as_posix()}"
    async_engine = create_async_engine(
        async_url,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

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


def test_save_token_too_short(client, db_session):
    """Token shorter than 10 chars is rejected, not saved, and logged masked."""
    with patch.object(settings_routes, "logger_service") as mock_logger:
        response = client.post(
            "/settings/token",
            json={"access_token": "shorty"},
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "Access token is empty or too short."}

        assert db_session.query(FyersToken).count() == 0

        mock_logger.log_error.assert_called_once()
        call_kwargs = mock_logger.log_error.call_args.kwargs
        assert call_kwargs.get("source") == "API"
        assert call_kwargs.get("module") == "settings.token"
        message = call_kwargs.get("message", "")
        assert "shorty" not in message
        assert "*" in message or "too short" in message.lower()


def test_save_token_fyers_network_error(client, db_session, monkeypatch):
    """httpx network errors return 400, do not persist, and log a masked token."""

    async def mock_get(*args, **kwargs):
        raise httpx.RequestError(
            "Network error",
            request=httpx.Request("GET", "https://api-t1.fyers.in/api/v3/profile"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    token = "valid_length_token_but_network_fails"
    with patch.object(settings_routes, "logger_service") as mock_logger:
        response = client.post(
            "/settings/token",
            json={"access_token": token},
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid or Expired FYERS Token."}

        assert db_session.query(FyersToken).count() == 0

        mock_logger.log_error.assert_called_once()
        call_kwargs = mock_logger.log_error.call_args.kwargs
        assert call_kwargs.get("source") == "API"
        message = call_kwargs.get("message", "")
        assert token not in message
        masked = _mask_token(token)
        assert masked is not None
        assert masked in message or "*" in message


def test_save_token_fyers_rejected(client, db_session, monkeypatch):
    """FYERS error JSON payload rejects the token and logs via LoggingService."""

    class MockResponse:
        status_code = 200

        def json(self):
            return {"s": "error", "code": -15, "message": "invalid token"}

    async def mock_get(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with patch.object(settings_routes, "logger_service") as mock_logger:
        response = client.post(
            "/settings/token",
            json={"access_token": "valid_length_token_but_fyers_rejects"},
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid or Expired FYERS Token."}

        assert db_session.query(FyersToken).count() == 0
        mock_logger.log_error.assert_called_once()
        assert mock_logger.log_error.call_args.kwargs.get("source") == "API"


def test_save_token_success(client, db_session, monkeypatch):
    """Successful FYERS validation encrypts+saves token, deactivates prior, logs info."""
    old_token = FyersToken(
        access_token="old_token_xyz",
        is_active=True,
        status="active",
    )
    db_session.add(old_token)
    db_session.commit()
    old_id = old_token.id

    class MockResponse:
        status_code = 200

        def json(self):
            return {"s": "ok", "code": 200, "message": "Success"}

    async def mock_get(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    plaintext = "valid_length_token_and_fyers_accepts"
    with patch.object(settings_routes, "logger_service") as mock_logger:
        response = client.post(
            "/settings/token",
            json={"access_token": plaintext},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "ok"
        assert data["message"] == "Token successfully verified and saved."

        mock_logger.log_info.assert_called_once()
        call_kwargs = mock_logger.log_info.call_args.kwargs
        assert call_kwargs.get("source") == "API"
        assert "successfully" in call_kwargs.get("message", "").lower()

        # Drop any open sync snapshot so we see the async route's commit.
        db_session.rollback()
        db_session.expire_all()

        reloaded_old = db_session.query(FyersToken).filter_by(id=old_id).one()
        assert not bool(reloaded_old.is_active)
        assert reloaded_old.status == "inactive"

        new_token = (
            db_session.query(FyersToken)
            .filter(FyersToken.is_active.is_(True))
            .order_by(FyersToken.id.desc())
            .first()
        )
        if new_token is None:
            new_token = next(
                (t for t in db_session.query(FyersToken).all() if bool(t.is_active)),
                None,
            )
        assert new_token is not None
        assert new_token.id != old_id
        decrypted = _decrypt_from_storage(new_token.access_token)
        assert decrypted == plaintext
        assert new_token.status == "Success"

        history = (
            db_session.query(FyersTokenHistory)
            .order_by(FyersTokenHistory.id.desc())
            .first()
        )
        assert history is not None
        assert history.status == "Success"
        assert plaintext not in (history.access_token_masked or "")
        assert "*" in (history.access_token_masked or "")
