"""
Admin user directory and role-change business logic (Sprint 2).

FR/AC: list users, update role, last-admin protection, audit on real changes.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.roles import UserRole, normalize_role
from ..models.auth import AuditLog, User

logger = logging.getLogger("app.services.admin_user")

EVENT_ADMIN_ROLE_CHANGE = "admin_role_change"
LAST_ADMIN_DETAIL = "Cannot demote the last active admin"


def _eligible_user_filters():
    """Active, non-deleted users (directory + role-change targets + last-admin count)."""
    return (
        User.is_active.is_(True),
        User.deleted_at.is_(None),
    )


async def count_active_admins(db: AsyncSession) -> int:
    """Count active, non-deleted users with role=admin (FR-018/FR-020)."""
    result = await db.execute(
        select(func.count())
        .select_from(User)
        .where(
            User.role == UserRole.ADMIN.value,
            *_eligible_user_filters(),
        )
    )
    return int(result.scalar_one() or 0)


async def _lock_active_admins(db: AsyncSession) -> list[User]:
    """
    Load and row-lock active non-deleted admins (audit H-1 / FR-022).

    Serializes concurrent demotions: a second demotion waits for the first
    transaction to commit, then re-evaluates the count under the lock.
    SQLite may ignore FOR UPDATE; Postgres enforces it.
    """
    result = await db.execute(
        select(User)
        .where(
            User.role == UserRole.ADMIN.value,
            *_eligible_user_filters(),
        )
        .order_by(User.id)
        .with_for_update()
    )
    return list(result.scalars().all())


def user_to_admin_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": normalize_role(user.role),
        "is_active": bool(user.is_active),
        "created_at": user.created_at,
    }


async def list_users(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    role: Optional[str] = None,
) -> Tuple[list[User], int, int, int]:
    """
    Paginated admin directory of active, non-deleted users.

    Returns (items, total, page, size).
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="page must be >= 1",
        )
    if size < 1 or size > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="size must be between 1 and 100",
        )

    filters = list(_eligible_user_filters())

    if role is not None and str(role).strip() != "":
        normalized = normalize_role(role)
        # Only accept exact domain values; normalize_role clamps invalid → trader,
        # so reject values that are not already valid role literals.
        raw = str(role).strip().lower()
        if raw not in {UserRole.TRADER.value, UserRole.ADMIN.value}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="role filter must be 'trader' or 'admin'",
            )
        filters.append(User.role == normalized)

    q = str(search).strip() if search is not None else ""
    if q:
        pattern = f"%{q}%"
        filters.append(
            or_(
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
            )
        )

    count_stmt = select(func.count()).select_from(User).where(*filters)
    total = int((await db.execute(count_stmt)).scalar_one() or 0)

    offset = (page - 1) * size
    list_stmt = (
        select(User)
        .where(*filters)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    result = await db.execute(list_stmt)
    items = list(result.scalars().all())
    return items, total, page, size


async def _get_eligible_target(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> User:
    stmt = select(User).where(User.id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


async def update_user_role(
    db: AsyncSession,
    *,
    actor: User,
    target_id: uuid.UUID,
    new_role: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> User:
    """
    Change target user role with last-admin protection and audit on real changes.

    Hardening:
    - H-1 / FR-022: demotions lock active admin rows in stable id order (FOR UPDATE).
    - M-1: role mutation + audit row commit in a single transaction.
    """
    raw = str(new_role).strip().lower()
    if raw not in {UserRole.TRADER.value, UserRole.ADMIN.value}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="role must be 'trader' or 'admin'",
        )
    desired = raw

    # Peek without lock for no-op / demotion branch selection (cheap path).
    target_peek = await _get_eligible_target(db, target_id, for_update=False)
    previous_peek = normalize_role(target_peek.role)

    # Idempotent no-op (FR-017): success, no audit.
    if previous_peek == desired:
        return target_peek

    is_demotion = (
        previous_peek == UserRole.ADMIN.value and desired == UserRole.TRADER.value
    )

    if is_demotion:
        # Lock ALL active admins in id order first to avoid deadlocks (audit H-1).
        locked_admins = await _lock_active_admins(db)
        target = next((u for u in locked_admins if u.id == target_id), None)
        if target is None:
            # Concurrent change: reload under row lock (may already be trader → no-op).
            target = await _get_eligible_target(db, target_id, for_update=True)
            previous = normalize_role(target.role)
            if previous == desired:
                return target
            # Still an admin but missing from lock set is unexpected; re-lock path.
            if previous == UserRole.ADMIN.value and desired == UserRole.TRADER.value:
                locked_admins = await _lock_active_admins(db)
                if len(locked_admins) <= 1:
                    logger.warning(
                        "LAST_ADMIN_PROTECTION | actor=%s target=%s | refused demotion of last active admin",
                        actor.id,
                        target.id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=LAST_ADMIN_DETAIL,
                    )
        else:
            previous = normalize_role(target.role)
            if previous == desired:
                return target
            if (
                previous == UserRole.ADMIN.value
                and desired == UserRole.TRADER.value
                and len(locked_admins) <= 1
            ):
                logger.warning(
                    "LAST_ADMIN_PROTECTION | actor=%s target=%s | refused demotion of last active admin",
                    actor.id,
                    target.id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=LAST_ADMIN_DETAIL,
                )
    else:
        # Promote or non-admin mutation: lock only the target row.
        target = await _get_eligible_target(db, target_id, for_update=True)
        previous = normalize_role(target.role)
        if previous == desired:
            return target

    target.role = desired

    # Belt-and-suspenders for demotion on engines with weak FOR UPDATE (e.g. SQLite tests):
    # after flush, refuse if no active admin would remain (audit H-1 residual).
    if previous == UserRole.ADMIN.value and desired == UserRole.TRADER.value:
        await db.flush()
        remaining = await count_active_admins(db)
        if remaining < 1:
            await db.rollback()
            logger.warning(
                "LAST_ADMIN_PROTECTION | actor=%s target=%s | post-flush refuse zero admins",
                actor.id,
                target.id,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=LAST_ADMIN_DETAIL,
            )

    # Atomic audit with role change (audit M-1): one commit for both writes.
    actor_id: Optional[uuid.UUID]
    if isinstance(actor.id, uuid.UUID):
        actor_id = actor.id
    else:
        try:
            actor_id = uuid.UUID(str(actor.id))
        except Exception:
            actor_id = None

    db.add(
        AuditLog(
            user_id=actor_id,
            event_type=EVENT_ADMIN_ROLE_CHANGE,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_={
                "actor_user_id": str(actor.id),
                "target_user_id": str(target.id),
                "previous_role": previous,
                "new_role": desired,
                "target_email": target.email,
            },
        )
    )

    try:
        await db.commit()
        await db.refresh(target)
    except Exception:
        await db.rollback()
        logger.error(
            "ADMIN_ROLE_CHANGE_FAILED | actor=%s target=%s previous=%s new=%s",
            actor.id,
            target_id,
            previous,
            desired,
            exc_info=True,
        )
        raise

    logger.info(
        "ADMIN_ROLE_CHANGED | actor=%s target=%s previous=%s new=%s",
        actor.id,
        target.id,
        previous,
        desired,
    )
    return target
