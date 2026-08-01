"""Unit tests for registration role hardening (US1)."""

from app.schemas.auth import UserCreate, UserRegisterRequest
from app.core.roles import UserRole, DEFAULT_ROLE


def test_user_register_request_schema_strips_role():
    """AC-REG-02: extra role field does not become schema field authority."""
    raw_payload = {
        "email": "attacker@example.com",
        "password": "Password123!",
        "full_name": "Attacker Name",
        "role": "admin",
    }
    req = UserRegisterRequest(**raw_payload)
    assert req.email == "attacker@example.com"
    assert req.full_name == "Attacker Name"
    assert not hasattr(req, "role") or getattr(req, "role", "trader") == "trader"


def test_user_register_request_accepts_minimal_fields():
    """AC-REG-01 request shape: email, password, full_name only."""
    req = UserRegisterRequest(
        email="user@example.com",
        password="SecurePassword123!",
        full_name="Jane Doe",
    )
    assert req.email == "user@example.com"
    dumped = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    assert "role" not in dumped


def test_user_create_default_role():
    user_in = UserCreate(
        email="trader@example.com",
        password="Password123!",
        full_name="Trader Name",
    )
    assert user_in.role == "trader"
    assert user_in.role == DEFAULT_ROLE
    assert user_in.role == UserRole.TRADER.value


def test_user_create_explicit_admin_is_schema_allowed_but_service_must_override():
    """Schema may carry role for internal creates; public register must still force trader (service)."""
    user_in = UserCreate(
        email="admin-internal@example.com",
        password="Password123!",
        full_name="Internal",
        role="admin",
    )
    assert user_in.role == "admin"
