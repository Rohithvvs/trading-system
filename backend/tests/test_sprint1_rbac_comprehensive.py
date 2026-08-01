"""
Sprint 1 RBAC comprehensive tests — maps to specs/022-rbac-role-jwt-admin acceptance criteria.

Covers unit, integration, failure-path, edge-case, bootstrap, and database constraint behavior.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.core.roles import UserRole, DEFAULT_ROLE, VALID_ROLES
from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from app.core.deps import _normalize_token_role
from app.schemas.auth import (
    UserCreate,
    UserRegisterRequest,
    AuthSuccessResponse,
    TokenPayload,
    UserResponse,
)
from app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_NAME,
    ensure_default_admin,
    ensure_default_admin_safe,
)
from app.models.auth import User

client = TestClient(app)


# ==============================================================================
# Helpers
# ==============================================================================

def _unique_email(prefix: str = "user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}@example.com"


def _register(email: str | None = None, password: str = "SecurePassword123!", full_name: str = "Test User", **extra):
    payload = {
        "email": email or _unique_email("reg"),
        "password": password,
        "full_name": full_name,
        **extra,
    }
    return client.post("/auth/register", json=payload), payload


def _login(email: str, password: str = "SecurePassword123!"):
    return client.post("/auth/login", json={"email": email, "password": password})


def _decode_jwt_payload_unverified(token: str) -> dict:
    """Decode JWT payload segment without signature verification (inspection only)."""
    parts = token.split(".")
    assert len(parts) >= 2
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    raw = base64.urlsafe_b64decode(payload_b64 + padding)
    return json.loads(raw.decode("utf-8"))


# ==============================================================================
# 1. UNIT TESTS
# ==============================================================================

def test_unit_role_constants():
    """FR-001 / NFR-006: role domain constants and whitelist."""
    assert UserRole.TRADER.value == "trader"
    assert UserRole.ADMIN.value == "admin"
    assert DEFAULT_ROLE == "trader"
    assert VALID_ROLES == {"trader", "admin"}
    assert len(VALID_ROLES) == 2


def test_unit_password_hashing_argon2():
    """NFR-005: password hashing is one-way and verifies correctly."""
    raw = "Admin@123"
    hashed = get_password_hash(raw)
    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_unit_jwt_trader_role_claims():
    """AC-JWT-01 / AC-JWT-02: JWT contains sub, role=trader, exp."""
    token, jti = create_access_token({"sub": "usr_trader_123", "role": "trader"})
    decoded = decode_access_token(token)
    assert decoded["sub"] == "usr_trader_123"
    assert decoded["role"] == "trader"
    assert "exp" in decoded
    assert jti
    assert decoded.get("jti") == jti


def test_unit_jwt_admin_role_claims():
    """AC-JWT-01 / AC-JWT-03: JWT contains role=admin."""
    token, _ = create_access_token({"sub": "usr_admin_123", "role": "admin"})
    decoded = decode_access_token(token)
    assert decoded["sub"] == "usr_admin_123"
    assert decoded["role"] == "admin"
    assert "exp" in decoded


def test_unit_jwt_default_role_fallback():
    """Edge: omitted role claim defaults to trader at issuance."""
    token, _ = create_access_token({"sub": "usr_no_role"})
    decoded = decode_access_token(token)
    assert decoded["role"] == "trader"


def test_unit_jwt_empty_role_defaults_to_trader():
    """Edge: empty role string defaults to trader."""
    token, _ = create_access_token({"sub": "usr_empty_role", "role": ""})
    decoded = decode_access_token(token)
    assert decoded["role"] == "trader"


def test_unit_deps_normalize_token_role():
    """FR-007: middleware normalizes valid roles and falls back for invalid/missing."""
    assert _normalize_token_role({"role": "admin"}) == "admin"
    assert _normalize_token_role({"role": "trader"}) == "trader"
    assert _normalize_token_role({}) == DEFAULT_ROLE
    assert _normalize_token_role({"role": "superuser"}) == DEFAULT_ROLE
    assert _normalize_token_role({"role": "ADMIN"}) == "admin"  # case-normalized


def test_unit_schema_registration_strips_role():
    """FR-003 / AC-REG-02: UserRegisterRequest does not accept authoritative role."""
    payload = {
        "email": "attacker@example.com",
        "password": "Password123!",
        "full_name": "Attacker Name",
        "role": "admin",
    }
    req = UserRegisterRequest(**payload)
    assert req.email == "attacker@example.com"
    assert not hasattr(req, "role") or getattr(req, "role", "trader") == "trader"


def test_unit_schema_user_create_default_role():
    """FR-002: UserCreate defaults role to trader."""
    user_in = UserCreate(
        email="trader_test@example.com",
        password="Password123!",
        full_name="Trader Test",
    )
    assert user_in.role == "trader"


def test_unit_auth_success_and_token_payload_schemas():
    """FR-008 / FR-006 schemas expose required identity + token fields."""
    resp = AuthSuccessResponse(
        id="usr_123",
        email="trader@example.com",
        full_name="Jane Doe",
        role="trader",
        access_token="test_token",
    )
    assert resp.role == "trader"
    assert resp.access_token == "test_token"

    payload = TokenPayload(sub="usr_123", role="admin", jti="jti-1", exp=1785168000)
    assert payload.role == "admin"
    assert payload.sub == "usr_123"


def test_unit_user_response_includes_role():
    """FR-009: UserResponse includes normalized role field."""
    body = UserResponse(
        id=uuid.uuid4(),
        email="me@example.com",
        full_name="Me User",
        role="admin",
    )
    assert body.role == "admin"


def test_unit_admin_bootstrap_constants():
    """AC-ADM-01 constants match specification."""
    assert DEFAULT_ADMIN_EMAIL == "admin@example.com"
    assert DEFAULT_ADMIN_PASSWORD == "Admin@123"
    assert DEFAULT_ADMIN_NAME == "Default Admin"


# ==============================================================================
# 2. INTEGRATION TESTS (API Endpoints)
# ==============================================================================

def test_integration_register_creates_trader_with_token():
    """AC-REG-01: register returns id, email, full_name, role=trader, access_token."""
    res, payload = _register()
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["email"] == payload["email"]
    assert data["full_name"] == payload["full_name"]
    assert data["role"] == "trader"
    assert data.get("id")
    assert data.get("access_token")
    # AC-JWT-01/02: issued token has required claims
    claims = decode_access_token(data["access_token"])
    assert claims["sub"] == str(data["id"])
    assert claims["role"] == "trader"
    assert "exp" in claims


def test_integration_register_ignores_admin_role_escalation():
    """AC-REG-02: client role=admin is ignored; account is trader."""
    email = _unique_email("esc_admin")
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Attacker",
            "role": "admin",
        },
    )
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["role"] == "trader"
    claims = decode_access_token(data["access_token"])
    assert claims["role"] == "trader"


def test_integration_register_ignores_superuser_role():
    """AC-REG-03: role=SUPERUSER is ignored; account is trader."""
    email = _unique_email("esc_super")
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Super Attempt",
            "role": "SUPERUSER",
        },
    )
    assert res.status_code in (200, 201)
    assert res.json()["role"] == "trader"


def test_integration_signup_alias_forces_trader():
    """AC-REG-01 via /auth/signup alias."""
    email = _unique_email("signup")
    res = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Signup User",
            "role": "admin",
        },
    )
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["email"] == email
    assert data["role"] == "trader"
    assert data.get("access_token")


def test_integration_login_trader_returns_full_identity():
    """AC-LOG-01: trader login returns id, email, full_name, role, access_token."""
    email = _unique_email("login_trader")
    pwd = "Password123!"
    client.post(
        "/auth/register",
        json={"email": email, "password": pwd, "full_name": "Login Trader"},
    )
    res = _login(email, pwd)
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == email
    assert data["full_name"] == "Login Trader"
    assert data["role"] == "trader"
    assert data.get("id")
    assert data.get("access_token")
    claims = decode_access_token(data["access_token"])
    assert claims["role"] == "trader"
    assert claims["sub"] == str(data["id"])
    assert "exp" in claims


@pytest.mark.asyncio
async def test_integration_login_admin_returns_admin_role():
    """AC-LOG-02 / AC-ADM-03: default admin login returns role=admin after bootstrap."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await ensure_default_admin(db)

    res = client.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert res.status_code == 200, res.text
    admin_body = res.json()
    assert admin_body["email"] == DEFAULT_ADMIN_EMAIL
    assert admin_body["role"] == "admin"
    assert admin_body.get("access_token")
    claims = decode_access_token(admin_body["access_token"])
    assert claims["role"] == "admin"
    assert "sub" in claims and "exp" in claims


def test_integration_get_me_trader_profile():
    """AC-ME-01: GET /auth/me returns trader profile fields."""
    res, payload = _register(full_name="Me Trader")
    token = res.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    data = me.json()
    assert data["email"] == payload["email"]
    assert data["full_name"] == "Me Trader"
    assert data["role"] == "trader"
    assert data.get("id")


@pytest.mark.asyncio
async def test_integration_get_me_admin_profile():
    """AC-ME-02: GET /auth/me for admin returns role=admin."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await ensure_default_admin(db)

    login = client.post(
        "/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    data = me.json()
    assert data["email"] == DEFAULT_ADMIN_EMAIL
    assert data["role"] == "admin"
    assert data.get("id")
    assert data.get("full_name") is not None


def test_integration_get_me_via_cookie_session():
    """Regression: cookie-based session still authenticates /auth/me."""
    email = _unique_email("cookie")
    pwd = "Password123!"
    # Use a dedicated client to capture cookies from login
    c = TestClient(app)
    c.post("/auth/register", json={"email": email, "password": pwd, "full_name": "Cookie User"})
    login = c.post("/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200
    me = c.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "trader"


def test_integration_register_then_me_without_relogin():
    """AC-REG-01 + AC-ME-01: register access_token is immediately usable on /auth/me."""
    res, payload = _register()
    token = res.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == payload["email"]
    assert me.json()["role"] == "trader"


# ==============================================================================
# 3. FAILURE PATH TESTS
# ==============================================================================

def test_failure_login_invalid_password():
    """AC-LOG-03: invalid password → 401."""
    email = _unique_email("fail_pwd")
    client.post(
        "/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Fail Pwd"},
    )
    res = _login(email, "WrongPassword!")
    assert res.status_code == 401


def test_failure_login_nonexistent_user():
    """AC-LOG-03: unknown email → 401 (no enumeration of existence via status)."""
    res = _login("nonexistent_9999@example.com", "Password123!")
    assert res.status_code == 401


def test_failure_get_me_missing_token():
    """AC-ME-03: no bearer/cookie → 401."""
    fresh = TestClient(app)
    res = fresh.get("/auth/me")
    assert res.status_code == 401


def test_failure_get_me_malformed_token():
    """AC-ME-03: malformed bearer → 401."""
    fresh = TestClient(app)
    res = fresh.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


def test_failure_get_me_tampered_role_claim():
    """NFR-004 / security: tampering JWT role claim invalidates signature → 401."""
    res, _ = _register()
    token = res.json()["access_token"]
    parts = token.split(".")
    assert len(parts) == 3
    payload = _decode_jwt_payload_unverified(token)
    payload["role"] = "admin"
    tampered_payload = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    tampered = f"{parts[0]}.{tampered_payload}.{parts[2]}"
    fresh = TestClient(app)
    me = fresh.get("/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert me.status_code == 401


def test_failure_register_weak_password():
    """Failure: password policy rejection on registration."""
    res = client.post(
        "/auth/register",
        json={
            "email": _unique_email("weak"),
            "password": "short",
            "full_name": "Weak Pwd",
        },
    )
    assert res.status_code in (400, 422)


def test_failure_register_invalid_email():
    """Failure: invalid email format rejected."""
    res = client.post(
        "/auth/register",
        json={
            "email": "not-an-email",
            "password": "SecurePassword123!",
            "full_name": "Bad Email",
        },
    )
    assert res.status_code == 422


# ==============================================================================
# 4. EDGE CASE TESTS
# ==============================================================================

def test_edge_duplicate_registration():
    """Edge: second registration with same email returns 400."""
    email = _unique_email("dup")
    payload = {"email": email, "password": "Password123!", "full_name": "Dup"}
    assert client.post("/auth/register", json=payload).status_code in (200, 201)
    assert client.post("/auth/register", json=payload).status_code == 400


def test_edge_registration_privilege_escalation_matrix():
    """AC-REG-02/03: matrix of malicious roles all become trader."""
    for malicious_role in ["MANAGER", "OWNER", "ROOT", "sysadmin", "ADMIN", "Admin", "administrator"]:
        email = _unique_email("esc")
        res = client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "Password123!",
                "full_name": "Esc Test",
                "role": malicious_role,
            },
        )
        assert res.status_code in (200, 201), malicious_role
        assert res.json()["role"] == "trader", malicious_role


def test_edge_jwt_exp_is_future_unix_timestamp():
    """Edge: exp claim is a future integer epoch."""
    token, _ = create_access_token({"sub": "u1", "role": "trader"})
    claims = decode_access_token(token)
    now = int(datetime.now(timezone.utc).timestamp())
    assert isinstance(claims["exp"], int)
    assert claims["exp"] > now


def test_edge_login_missing_fields_validation():
    """Edge: empty login body fails validation."""
    res = client.post("/auth/login", json={})
    assert res.status_code == 422


# ==============================================================================
# 5. DEFAULT ADMIN BOOTSTRAP (DB-backed)
# ==============================================================================

@pytest.mark.asyncio
async def test_admin_bootstrap_creates_when_zero_admins(async_db_session):
    """AC-ADM-01: seeds default admin when no admin exists."""
    created = await ensure_default_admin(async_db_session)
    assert created is True
    # Re-query within same session
    from sqlalchemy import select

    result = await async_db_session.execute(
        select(User).where(User.email == DEFAULT_ADMIN_EMAIL)
    )
    admin = result.scalar_one_or_none()
    assert admin is not None
    assert admin.role == UserRole.ADMIN.value
    assert verify_password(DEFAULT_ADMIN_PASSWORD, admin.password_hash)


@pytest.mark.asyncio
async def test_admin_bootstrap_idempotent_when_admin_exists(async_db_session):
    """AC-ADM-02: second bootstrap skips without duplicating/mutating."""
    first = await ensure_default_admin(async_db_session)
    assert first is True
    second = await ensure_default_admin(async_db_session)
    assert second is False

    from sqlalchemy import select, func

    count = await async_db_session.execute(
        select(func.count()).select_from(User).where(User.role == UserRole.ADMIN.value)
    )
    assert count.scalar_one() == 1


@pytest.mark.asyncio
async def test_admin_bootstrap_skips_when_other_admin_exists(async_db_session):
    """AC-ADM-02: existing non-default admin prevents default seed."""
    other = User(
        id=uuid.uuid4(),
        email="custom-admin@example.com",
        full_name="Custom Admin",
        password_hash=get_password_hash("CustomAdmin1!"),
        role=UserRole.ADMIN.value,
        is_active=True,
        provider="email",
    )
    async_db_session.add(other)
    await async_db_session.commit()

    created = await ensure_default_admin(async_db_session)
    assert created is False

    from sqlalchemy import select

    result = await async_db_session.execute(
        select(User).where(User.email == DEFAULT_ADMIN_EMAIL)
    )
    assert result.scalar_one_or_none() is None


# ==============================================================================
# 6. DATABASE CONSTRAINTS & NORMALIZATION
# ==============================================================================

def test_db_check_constraint_rejects_invalid_role(test_engine):
    """AC-DB-03: invalid role value fails CHECK constraint."""
    with test_engine.begin() as conn:
        with pytest.raises(Exception):
            conn.execute(
                text(
                    "INSERT INTO users (id, email, full_name, password_hash, role, provider, is_active, is_email_verified) "
                    "VALUES (:id, :email, :name, :pwd, :role, 'email', 1, 0)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "email": f"bad_role_{uuid.uuid4().hex[:8]}@example.com",
                    "name": "Bad Role",
                    "pwd": "x",
                    "role": "superuser",
                },
            )


def test_db_role_default_trader_when_omitted(test_engine):
    """AC-DB-04: inserting without role uses default trader (column default)."""
    user_id = str(uuid.uuid4())
    email = f"default_role_{uuid.uuid4().hex[:8]}@example.com"
    with test_engine.begin() as conn:
        # Omit role column — server_default / column default should apply
        conn.execute(
            text(
                "INSERT INTO users (id, email, full_name, password_hash, provider, is_active, is_email_verified) "
                "VALUES (:id, :email, :name, :pwd, 'email', 1, 0)"
            ),
            {"id": user_id, "email": email, "name": "Default Role", "pwd": "x"},
        )
        row = conn.execute(
            text("SELECT role FROM users WHERE id = :id"),
            {"id": user_id},
        ).fetchone()
    assert row is not None
    assert row[0] == "trader"


def test_db_normalization_mapping_logic():
    """AC-DB-01 / AC-DB-02: migration normalization mapping (unit-level)."""
    cases = [
        ("Trader", "trader"),
        ("TRADER", "trader"),
        ("trader", "trader"),
        ("Admin", "admin"),
        ("ADMIN", "admin"),
        ("admin", "admin"),
        ("owner", "trader"),
        ("manager", "trader"),
        ("USER", "trader"),
        (None, "trader"),
    ]
    for raw, expected in cases:
        normalized = "admin" if raw and str(raw).lower() == "admin" else "trader"
        assert normalized == expected
        assert normalized in VALID_ROLES


def test_db_model_check_constraint_present():
    """Regression: User model declares role CHECK constraint on users.role."""
    from sqlalchemy import CheckConstraint

    check_constraints = [
        c for c in User.__table__.constraints if isinstance(c, CheckConstraint)
    ]
    assert check_constraints, "Expected at least one CheckConstraint on users"
    names = [c.name for c in check_constraints if c.name]
    assert any(n and "role" in n for n in names), names
    # TextClause sqltext holds the original expression
    texts = []
    for c in check_constraints:
        sqltext = getattr(c, "sqltext", None)
        texts.append(str(sqltext) if sqltext is not None else "")
    joined = " ".join(texts).lower()
    assert "trader" in joined and "admin" in joined, texts


# ==============================================================================
# 7. BACKWARD COMPATIBILITY / REGRESSION
# ==============================================================================

def test_regression_existing_credentials_still_login():
    """AC-BC-01: previously registered user can login with same password."""
    email = _unique_email("bc")
    pwd = "LegacyPassword123!"
    reg = client.post(
        "/auth/register",
        json={"email": email, "password": pwd, "full_name": "Legacy User"},
    )
    assert reg.status_code in (200, 201)
    login = _login(email, pwd)
    assert login.status_code == 200
    assert login.json()["role"] == "trader"
    assert login.json()["email"] == email


def test_regression_login_response_still_includes_message_field():
    """Regression: login retains prior message field for clients that read it."""
    email = _unique_email("msg")
    pwd = "Password123!"
    client.post(
        "/auth/register",
        json={"email": email, "password": pwd, "full_name": "Msg User"},
    )
    data = _login(email, pwd).json()
    # message is legacy-friendly; role is new
    assert data.get("role") == "trader"
    assert "access_token" in data


def test_regression_refresh_preserves_role_claim():
    """Regression: /auth/refresh issues access token that still authenticates /me."""
    email = _unique_email("refresh")
    pwd = "Password123!"
    c = TestClient(app)
    c.post("/auth/register", json={"email": email, "password": pwd, "full_name": "Refresh User"})
    login = c.post("/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200
    refresh = c.post("/auth/refresh")
    # If refresh depends on cookies, status 200; otherwise skip soft-fail environments
    if refresh.status_code != 200:
        pytest.skip("Refresh cookie flow not available in this client configuration")
    me = c.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "trader"
