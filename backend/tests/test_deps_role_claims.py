"""Unit tests for JWT role claim extraction in request deps (FR-007)."""

import uuid

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.deps import _normalize_token_role, _extract_token_payload
from app.core.security import create_access_token
from app.core.roles import DEFAULT_ROLE


def test_normalize_token_role_valid_admin():
    assert _normalize_token_role({"role": "admin"}) == "admin"


def test_normalize_token_role_valid_trader():
    assert _normalize_token_role({"role": "trader"}) == "trader"


def test_normalize_token_role_missing_defaults():
    assert _normalize_token_role({}) == DEFAULT_ROLE
    assert _normalize_token_role({"role": None}) == DEFAULT_ROLE


def test_normalize_token_role_invalid_defaults():
    assert _normalize_token_role({"role": "owner"}) == DEFAULT_ROLE


def test_normalize_token_role_accepts_case_via_normalize():
    # ADMIN upper-case is normalized to admin by normalize_role
    assert _normalize_token_role({"role": "ADMIN"}) == "admin"
    assert _normalize_token_role({"role": "Trader"}) == "trader"


def _request_with_auth(token: str | None) -> Request:
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode("latin-1")))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/auth/me",
        "raw_path": b"/auth/me",
        "query_string": b"",
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_extract_token_payload_from_bearer():
    uid = str(uuid.uuid4())
    token, _ = create_access_token({"sub": uid, "role": "admin"})
    req = _request_with_auth(token)
    payload = _extract_token_payload(req)
    assert payload["sub"] == uid
    assert payload["role"] == "admin"


def test_extract_token_payload_missing_raises_401():
    req = _request_with_auth(None)
    with pytest.raises(HTTPException) as exc:
        _extract_token_payload(req)
    assert exc.value.status_code == 401


def test_extract_token_payload_invalid_raises_401():
    req = _request_with_auth("not.a.valid.jwt")
    with pytest.raises(HTTPException) as exc:
        _extract_token_payload(req)
    assert exc.value.status_code == 401


def test_get_token_principal_is_stateless():
    from app.core.deps import get_token_principal

    uid = str(uuid.uuid4())
    token, _ = create_access_token({"sub": uid, "role": "admin"})
    principal = get_token_principal(_request_with_auth(token))
    assert principal.user_id == uid
    assert principal.role == "admin"
    assert principal.is_admin is True


def test_require_admin_rejects_trader():
    from app.core.deps import require_roles, get_token_principal
    from app.core.roles import UserRole

    uid = str(uuid.uuid4())
    token, _ = create_access_token({"sub": uid, "role": "trader"})
    principal = get_token_principal(_request_with_auth(token))
    checker = require_roles(UserRole.ADMIN.value)
    with pytest.raises(HTTPException) as exc:
        checker(principal)
    assert exc.value.status_code == 403


def test_require_admin_allows_admin():
    from app.core.deps import require_roles, get_token_principal
    from app.core.roles import UserRole

    uid = str(uuid.uuid4())
    token, _ = create_access_token({"sub": uid, "role": "admin"})
    principal = get_token_principal(_request_with_auth(token))
    checker = require_roles(UserRole.ADMIN.value)
    out = checker(principal)
    assert out.is_admin is True
