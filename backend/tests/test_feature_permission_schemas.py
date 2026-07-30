"""Schema smoke tests for UpdateFeaturePermissionRequest (Sprint 3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.admin import (
    FeatureListResponse,
    FeaturePermissionResponse,
    UpdateFeaturePermissionRequest,
)


def test_update_allowed_roles_valid():
    body = UpdateFeaturePermissionRequest(allowed_roles=["admin"])
    assert body.allowed_roles == ["admin"]


def test_update_both_roles_valid():
    body = UpdateFeaturePermissionRequest(allowed_roles=["trader", "admin"])
    assert body.allowed_roles == ["trader", "admin"]


def test_update_empty_roles_list_allowed_by_schema():
    body = UpdateFeaturePermissionRequest(allowed_roles=[])
    assert body.allowed_roles == []


def test_update_is_active_only():
    body = UpdateFeaturePermissionRequest(is_active=False)
    assert body.is_active is False


def test_update_description_only():
    body = UpdateFeaturePermissionRequest(description="Updated")
    assert body.description == "Updated"


def test_update_empty_body_rejected():
    with pytest.raises(ValidationError):
        UpdateFeaturePermissionRequest()


def test_update_invalid_role_rejected():
    with pytest.raises(ValidationError):
        UpdateFeaturePermissionRequest(allowed_roles=["superuser"])  # type: ignore[list-item]


def test_update_mixed_case_role_rejected_by_literal():
    with pytest.raises(ValidationError):
        UpdateFeaturePermissionRequest(allowed_roles=["Admin"])  # type: ignore[list-item]


def test_feature_list_response_shape():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    item = FeaturePermissionResponse(
        id="11111111-1111-4111-8111-111111111111",
        feature_key="watchlist",
        description="Watchlist",
        allowed_roles=["trader", "admin"],
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    lst = FeatureListResponse(items=[item])
    assert len(lst.items) == 1
    assert lst.items[0].feature_key == "watchlist"
