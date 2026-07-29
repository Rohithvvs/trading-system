"""Schema smoke tests for admin DTOs (Sprint 2)."""

import pytest
from pydantic import ValidationError

from app.schemas.admin import UpdateRoleRequest, UserAdminResponse, UserListResponse
from datetime import datetime, timezone
import uuid


def test_update_role_request_accepts_trader_and_admin():
    assert UpdateRoleRequest(role="trader").role == "trader"
    assert UpdateRoleRequest(role="admin").role == "admin"


def test_update_role_request_rejects_invalid_role():
    with pytest.raises(ValidationError):
        UpdateRoleRequest(role="superuser")
    with pytest.raises(ValidationError):
        UpdateRoleRequest(role="ADMIN")  # must be exact literal lower-case


def test_user_list_response_shape():
    item = UserAdminResponse(
        id=str(uuid.uuid4()),
        email="a@example.com",
        full_name="A",
        role="trader",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    body = UserListResponse(items=[item], total=1, page=1, size=20)
    assert body.total == 1
    assert body.items[0].role == "trader"
