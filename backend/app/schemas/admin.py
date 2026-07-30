"""Admin API schemas (Sprint 2 user management + Sprint 3 feature permissions)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class UserAdminResponse(BaseModel):
    """Single user row returned by admin directory / role-change APIs."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    role: Literal["trader", "admin"]
    is_active: bool
    created_at: datetime


class UserListResponse(BaseModel):
    """Paginated admin user directory."""

    items: List[UserAdminResponse]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    size: int = Field(..., ge=1, le=100)


class UpdateRoleRequest(BaseModel):
    """Body for PATCH /admin/users/{user_id}/role."""

    role: Literal["trader", "admin"]


# --- Sprint 3: Feature Permissions ---


class FeaturePermissionResponse(BaseModel):
    """Single feature permission row."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    feature_key: str
    description: str
    allowed_roles: List[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FeatureListResponse(BaseModel):
    """Admin feature permission catalog."""

    items: List[FeaturePermissionResponse]


class UpdateFeaturePermissionRequest(BaseModel):
    """Body for PATCH /admin/features/{feature_key}."""

    allowed_roles: Optional[List[Literal["trader", "admin"]]] = None
    is_active: Optional[bool] = None
    description: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateFeaturePermissionRequest":
        if (
            self.allowed_roles is None
            and self.is_active is None
            and self.description is None
        ):
            raise ValueError(
                "At least one of allowed_roles, is_active, description must be provided"
            )
        if self.description is not None and str(self.description).strip() == "":
            raise ValueError("description must not be blank")
        return self
