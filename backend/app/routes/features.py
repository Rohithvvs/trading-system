"""Authenticated feature permission catalog (Sprint 5).

GET /features — any authenticated user may read the catalog so the frontend
can evaluate canAccess against live DB policy (AC-FEAT-05). Mutations remain
admin-only under /admin/features.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deps import get_current_active_user
from ..db.session import get_db
from ..models.auth import User
from ..schemas.admin import FeatureListResponse, FeaturePermissionResponse
from ..services import feature_permission_service

router = APIRouter(tags=["Features"])


def _to_feature_response(row) -> FeaturePermissionResponse:
    data = feature_permission_service.feature_to_dict(row)
    return FeaturePermissionResponse(**data)


@router.get(
    "/features",
    response_model=FeatureListResponse,
    status_code=status.HTTP_200_OK,
    summary="List feature permissions (authenticated)",
)
async def list_features_for_session(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Full feature permission catalog for the signed-in session.

    Traders and admins both receive DB-backed policy so Admin Panel changes
    apply on the next fetch/refetch (no client-only static matrix required).
    Soft-deleted / inactive principals are rejected by get_current_active_user.
    """
    # Explicit principal binding — dependency already enforced; keep for auditability
    if not user or not user.is_active:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    rows = await feature_permission_service.list_features(db)
    return FeatureListResponse(items=[_to_feature_response(r) for r in rows])
