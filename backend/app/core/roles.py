from enum import Enum
from typing import Any


class UserRole(str, Enum):
    TRADER = "trader"
    ADMIN = "admin"


DEFAULT_ROLE = UserRole.TRADER.value
VALID_ROLES = {UserRole.TRADER.value, UserRole.ADMIN.value}


def normalize_role(role: Any) -> str:
    """Clamp any role value to a valid lower-case domain value (trader|admin)."""
    if role is None:
        return DEFAULT_ROLE
    value = str(role).strip().lower()
    if value in VALID_ROLES:
        return value
    return DEFAULT_ROLE
