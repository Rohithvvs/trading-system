"""Admin user-management routes (Sprint 2). Prefix: /admin"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deps import get_current_admin_user
from ..db.session import get_db
from ..models.auth import User
from ..schemas.admin import UpdateRoleRequest, UserAdminResponse, UserListResponse
from ..services import admin_user_service

router = APIRouter()


def _to_response(user: User) -> UserAdminResponse:
    data = admin_user_service.user_to_admin_dict(user)
    return UserAdminResponse(**data)


@router.get(
    "/users",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    summary="List users (admin only)",
)
async def list_users(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (≥ 1)"),
    size: int = Query(20, ge=1, le=100, description="Page size (1–100)"),
    search: Optional[str] = Query(None, description="Partial match on email or full_name"),
    role: Optional[str] = Query(None, description="Filter: trader or admin"),
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Paginated directory of active, non-deleted users."""
    _ = admin  # authorization via dependency
    _ = request
    items, total, page_out, size_out = await admin_user_service.list_users(
        db,
        page=page,
        size=size,
        search=search,
        role=role,
    )
    return UserListResponse(
        items=[_to_response(u) for u in items],
        total=total,
        page=page_out,
        size=size_out,
    )


@router.patch(
    "/users/{user_id}/role",
    response_model=UserAdminResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user role (admin only)",
)
async def update_user_role(
    user_id: uuid.UUID,
    body: UpdateRoleRequest,
    request: Request,
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Promote/demote user with last-admin protection and audit on real changes."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    user = await admin_user_service.update_user_role(
        db,
        actor=admin,
        target_id=user_id,
        new_role=body.role,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return _to_response(user)
