"""Admin user-management API schemas (Sprint 2)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
