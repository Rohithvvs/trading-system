"""Single-owner dependency providers.

User JWT/session authentication was removed in 026-remove-multi-user.
All request-scoped "user" resolution returns the static Application Owner.
"""
from __future__ import annotations

import uuid
import warnings
from typing import NamedTuple

from fastapi import Request

SYSTEM_OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class ApplicationOwnerContext(NamedTuple):
    id: uuid.UUID = SYSTEM_OWNER_ID
    email: str = "owner@personal.trading"
    full_name: str = "Application Owner"
    is_active: bool = True
    role: str = "Owner"


SYSTEM_OWNER = ApplicationOwnerContext()


def get_application_owner_context() -> ApplicationOwnerContext:
    """Return static application owner context for single-user operation."""
    return SYSTEM_OWNER


def get_application_owner_id() -> uuid.UUID:
    """Return static SYSTEM_OWNER_ID (preferred over legacy user-id helpers)."""
    return SYSTEM_OWNER_ID


def get_current_user(request: Request = None) -> ApplicationOwnerContext:
    """Deprecated compatibility alias for get_application_owner_context().

    Retained so existing Depends(...) call sites keep working without implying
    real session authentication.
    """
    warnings.warn(
        "get_current_user is a single-owner compatibility shim; "
        "prefer get_application_owner_context()",
        DeprecationWarning,
        stacklevel=2,
    )
    return SYSTEM_OWNER


def get_current_active_user(request: Request = None) -> ApplicationOwnerContext:
    """Deprecated compatibility alias for get_application_owner_context()."""
    warnings.warn(
        "get_current_active_user is a single-owner compatibility shim; "
        "prefer get_application_owner_context()",
        DeprecationWarning,
        stacklevel=2,
    )
    return SYSTEM_OWNER


def get_current_user_id_sync(request: Request = None) -> uuid.UUID:
    """Deprecated compatibility alias for get_application_owner_id()."""
    return SYSTEM_OWNER_ID


def get_current_user_sync(request: Request = None) -> ApplicationOwnerContext:
    """Deprecated compatibility alias for get_application_owner_context()."""
    return SYSTEM_OWNER
