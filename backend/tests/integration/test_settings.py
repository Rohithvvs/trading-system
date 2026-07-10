import httpx
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models import FyersToken, FyersTokenHistory


@pytest.fixture
def client():
    return TestClient(app)


def test_save_token_too_short(client, db_session):
    """Test that a token shorter than 10 chars is immediately rejected."""
    with patch("app.routes.settings.logger_service") as mock_logger:
        response = client.post(
            "/settings/token",
            json={"access_token": "shorty"},
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "Access token is empty or too short."}
        
        # Verify it was NOT saved
        assert db_session.query(FyersToken).count() == 0
        
        # Verify LoggingService called and token was masked
        mock_logger.log_error.assert_called_once()
        call_args = mock_logger.log_error.call_args[1]
        assert call_args["source"] == "API"
        assert "shorty" not in call_args["message"]
        assert "***" in call_args["message"] or "*" in call_args["message"]


def test_save_token_fyers_network_error(client, db_session, monkeypatch):
    """Test that httpx network errors return 400."""
    async def mock_get(*args, **kwargs):
        raise httpx.RequestError("Network error", request=httpx.Request("GET", "https://api-t1.fyers.in/api/v3/profile"))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with patch("app.routes.settings.logger_service") as mock_logger:
        response = client.post(
            "/settings/token",
            json={"access_token": "valid_length_token_but_network_fails"},
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid or Expired FYERS Token."}
        
        # Verify it was NOT saved
        assert db_session.query(FyersToken).count() == 0

        # Verify LoggingService called
        mock_logger.log_error.assert_called_once()
        call_args = mock_logger.log_error.call_args[1]
        assert call_args["source"] == "API"
        assert "valid_length_token_but_network_fails" not in call_args["message"]
        assert "..." in call_args["message"]


def test_save_token_fyers_rejected(client, db_session, monkeypatch):
    """Test that FYERS returning an error JSON payload rejects the token."""
    class MockResponse:
        status_code = 200
        def json(self):
            return {"s": "error", "code": -15, "message": "invalid token"}

    async def mock_get(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with patch("app.routes.settings.logger_service") as mock_logger:
        response = client.post(
            "/settings/token",
            json={"access_token": "valid_length_token_but_fyers_rejects"},
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid or Expired FYERS Token."}
        
        # Verify it was NOT saved
        assert db_session.query(FyersToken).count() == 0

        # Verify LoggingService called
        mock_logger.log_error.assert_called_once()


def test_save_token_success(client, db_session, monkeypatch):
    """Test that a successful FYERS validation saves the token."""
    # Seed a pre-existing token
    old_token = FyersToken(
        access_token="old_token_xyz",
        is_active=True,
        status="active",
    )
    db_session.add(old_token)
    db_session.commit()

    class MockResponse:
        status_code = 200
        def json(self):
            return {"s": "ok", "code": 200, "message": "Success"}

    async def mock_get(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with patch("app.routes.settings.logger_service") as mock_logger:
        response = client.post(
            "/settings/token",
            json={"access_token": "valid_length_token_and_fyers_accepts"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["message"] == "Token successfully verified and saved."

        # Verify LoggingService called
        mock_logger.log_info.assert_called_once()
        call_args = mock_logger.log_info.call_args[1]
        assert call_args["source"] == "API"
        assert "successfully" in call_args["message"]

        # Verify old token was deactivated
        db_session.refresh(old_token)
        assert old_token.is_active is False
        assert old_token.status == "inactive"

        # Verify new token was created
        new_token = db_session.query(FyersToken).filter_by(is_active=True).first()
        assert new_token is not None
        assert new_token.access_token == "valid_length_token_and_fyers_accepts"
        assert new_token.status == "active"

        # Verify history entry was created
        history = db_session.query(FyersTokenHistory).first()
        assert history is not None
        assert history.status == "active"
        assert "..." in history.access_token_masked
