"""Unit tests for JWT role claims and auth response schemas (US2)."""

import pytest
from app.core.security import create_access_token, decode_access_token
from app.schemas.auth import AuthSuccessResponse, TokenPayload, UserResponse
import uuid


def test_jwt_access_token_role_claim():
    """AC-JWT-01 / AC-JWT-02: trader token has sub, role, exp."""
    token, jti = create_access_token({"sub": "usr_12345", "role": "trader"})
    decoded = decode_access_token(token)
    assert decoded["sub"] == "usr_12345"
    assert decoded["role"] == "trader"
    assert "exp" in decoded
    assert decoded.get("jti") == jti


def test_jwt_admin_role_claim():
    """AC-JWT-03: admin token role claim is admin."""
    token, jti = create_access_token({"sub": "usr_admin", "role": "admin"})
    decoded = decode_access_token(token)
    assert decoded["sub"] == "usr_admin"
    assert decoded["role"] == "admin"
    assert "exp" in decoded


def test_jwt_missing_role_defaults_to_trader():
    token, _ = create_access_token({"sub": "usr_default"})
    assert decode_access_token(token)["role"] == "trader"


def test_jwt_invalid_role_clamped_to_trader():
    token, _ = create_access_token({"sub": "usr_bad", "role": "superuser"})
    assert decode_access_token(token)["role"] == "trader"


def test_jwt_admin_case_normalized():
    token, _ = create_access_token({"sub": "usr_admin_case", "role": "ADMIN"})
    assert decode_access_token(token)["role"] == "admin"


def test_access_token_expire_minutes_is_positive():
    from app.core.security import ACCESS_TOKEN_EXPIRE_MINUTES

    assert ACCESS_TOKEN_EXPIRE_MINUTES > 0
    assert ACCESS_TOKEN_EXPIRE_MINUTES <= 1440


def test_auth_success_response_schema():
    """FR-008 response shape."""
    resp = AuthSuccessResponse(
        id="usr_123",
        email="trader@example.com",
        full_name="Jane Doe",
        role="trader",
        access_token="test_token",
    )
    assert resp.id == "usr_123"
    assert resp.role == "trader"
    assert resp.access_token == "test_token"


def test_token_payload_schema_requires_role():
    payload = TokenPayload(sub="u1", role="admin", jti="j1", exp=9999999999)
    assert payload.role == "admin"


def test_user_response_role_default():
    user = UserResponse(
        id=uuid.uuid4(),
        email="a@example.com",
        full_name="A",
    )
    assert user.role == "trader"
