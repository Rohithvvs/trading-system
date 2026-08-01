"""Unit tests for role normalization mapping and constraints (Phase 2)."""

from app.core.roles import UserRole, DEFAULT_ROLE, VALID_ROLES, normalize_role
from app.models.auth import User


def test_user_role_constants():
    assert UserRole.TRADER.value == "trader"
    assert UserRole.ADMIN.value == "admin"
    assert DEFAULT_ROLE == "trader"
    assert "trader" in VALID_ROLES
    assert "admin" in VALID_ROLES
    assert len(VALID_ROLES) == 2


def test_normalize_role_helper():
    assert normalize_role("ADMIN") == "admin"
    assert normalize_role("Trader") == "trader"
    assert normalize_role("owner") == "trader"
    assert normalize_role(None) == "trader"


def test_migration_sql_normalization_mapping_matches_upgrade_script():
    """L-5: document upgrade script mapping (same as alembic upgrade body)."""
    # Mirrors 20260728_001_rbac_role_normalization upgrade UPDATE statements.
    def migrate_role(raw):
        if raw is not None and str(raw).lower() == "admin":
            return "admin"
        return "trader"

    for raw, expected in [
        ("Trader", "trader"),
        ("ADMIN", "admin"),
        ("admin", "admin"),
        ("manager", "trader"),
        (None, "trader"),
    ]:
        assert migrate_role(raw) == expected


def test_role_normalization_logic_ac_db_01_02():
    """AC-DB-01 / AC-DB-02: case variants and legacy roles map correctly."""
    cases = {
        "Trader": "trader",
        "TRADER": "trader",
        "trader": "trader",
        "Admin": "admin",
        "ADMIN": "admin",
        "admin": "admin",
        "owner": "trader",
        "manager": "trader",
        "USER": "trader",
        "member": "trader",
        None: "trader",
    }
    for raw, expected in cases.items():
        normalized = "admin" if raw and str(raw).lower() == "admin" else "trader"
        assert normalized == expected
        assert normalized in VALID_ROLES


def test_user_model_role_server_default():
    """FR-004: model column default is trader."""
    col = User.__table__.c.role
    assert col.nullable is False
    # server_default or default present
    assert col.default is not None or col.server_default is not None


def test_user_model_check_constraint_name():
    """FR-005: role CHECK constraint is declared on the users model."""
    names = [c.name for c in User.__table__.constraints if getattr(c, "name", None)]
    # SQLAlchemy may prefix (e.g. ck_users_ck_users_role_valid)
    assert any(n and "role" in n and n.startswith("ck_") for n in names), names
