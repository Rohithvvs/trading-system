"""
Feature permission catalog service (Sprint 3 + Sprint 5 API gates).

Helpers:
- can_access_feature / can_access_feature_sync — fail-closed (unknown roles deny;
  missing/inactive features deny; never clamp unknown roles to trader).
- Wired onto product surfaces via core.deps.require_feature (Sprint 5 M-5).

Hardening (audit):
- H-1: seed never commits the caller's request session (flush-only unless commit=True)
- M-1: concurrent seed races handled via savepoint + IntegrityError
- M-2: corrupt stored roles do not block description-only updates
- M-3: write path requires exact lower-case domain roles (no silent lowercasing of Admin)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..core.roles import VALID_ROLES, UserRole
from ..models.auth import AuditLog, User
from ..models.feature_permission import FeaturePermission

logger = logging.getLogger("app.services.feature_permission")

CRITICAL_FEATURE_KEYS = frozenset({"admin_panel", "user_management"})
EVENT_FEATURE_PERMISSION_CHANGE = "admin_feature_permission_change"

CANNOT_REMOVE_ADMIN = "Cannot remove admin from critical feature"
CANNOT_DEACTIVATE = "Cannot deactivate critical feature"

# FR-005 default seed (insert-if-not-exists)
DEFAULT_FEATURES: list[dict[str, Any]] = [
    {
        "feature_key": "admin_panel",
        "description": "Access to the administrative console",
        "allowed_roles": [UserRole.ADMIN.value],
        "is_active": True,
    },
    {
        "feature_key": "user_management",
        "description": "List users and change roles",
        "allowed_roles": [UserRole.ADMIN.value],
        "is_active": True,
    },
    {
        "feature_key": "system_logs",
        "description": "View system and operational logs",
        "allowed_roles": [UserRole.ADMIN.value],
        "is_active": True,
    },
    {
        "feature_key": "central_command",
        "description": "Operational central command console",
        "allowed_roles": [UserRole.ADMIN.value],
        "is_active": True,
    },
    {
        "feature_key": "export_data",
        "description": "Export data from the platform",
        "allowed_roles": [UserRole.ADMIN.value],
        "is_active": True,
    },
    {
        "feature_key": "watchlist",
        "description": "Watchlist management and views",
        "allowed_roles": [UserRole.TRADER.value, UserRole.ADMIN.value],
        "is_active": True,
    },
    {
        "feature_key": "portfolio_analytics",
        "description": "Portfolio analytics and reports",
        "allowed_roles": [UserRole.TRADER.value, UserRole.ADMIN.value],
        "is_active": True,
    },
    {
        "feature_key": "advanced_scanner",
        "description": "Advanced scanner tools and views",
        "allowed_roles": [UserRole.TRADER.value, UserRole.ADMIN.value],
        "is_active": True,
    },
    {
        "feature_key": "recommendation_lab",
        "description": "RE-001 Recommendation Lab comparison and detail surfaces",
        "allowed_roles": [UserRole.TRADER.value, UserRole.ADMIN.value],
        "is_active": True,
    },
]


def normalize_allowed_roles(roles: list[str]) -> list[str]:
    """
    Validate exact domain roles for writes, dedupe, order trader then admin.

    Exact match after strip only (M-3): \"Admin\" is rejected, not coerced.
    """
    if not isinstance(roles, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="allowed_roles must be an array",
        )
    seen: set[str] = set()
    for r in roles:
        if r is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="role must be 'trader' or 'admin'",
            )
        raw = str(r).strip()
        if raw not in VALID_ROLES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="role must be 'trader' or 'admin'",
            )
        seen.add(raw)
    result: list[str] = []
    if UserRole.TRADER.value in seen:
        result.append(UserRole.TRADER.value)
    if UserRole.ADMIN.value in seen:
        result.append(UserRole.ADMIN.value)
    return result


def coerce_stored_roles(roles: Any) -> list[str]:
    """
    Best-effort read of stored allowed_roles (M-2).

    Filters to valid domain values; does not raise HTTPException.
    """
    if not isinstance(roles, list):
        logger.warning(
            "FEATURE_PERMISSIONS_CORRUPT_ROLES | non-list allowed_roles type=%s",
            type(roles).__name__,
        )
        return []
    seen: set[str] = set()
    for r in roles:
        raw = str(r).strip() if r is not None else ""
        if raw in VALID_ROLES:
            seen.add(raw)
        elif raw:
            logger.warning(
                "FEATURE_PERMISSIONS_CORRUPT_ROLES | dropping invalid stored role=%r",
                raw,
            )
    result: list[str] = []
    if UserRole.TRADER.value in seen:
        result.append(UserRole.TRADER.value)
    if UserRole.ADMIN.value in seen:
        result.append(UserRole.ADMIN.value)
    return result


def resolve_feature_role(role: Any) -> Optional[str]:
    """
    Strip+lower domain role for access checks.

    Returns None for unknown roles — never clamps to trader (FR-028).
    """
    if role is None:
        return None
    raw = str(role).strip().lower()
    if raw not in VALID_ROLES:
        return None
    return raw


def feature_to_dict(row: FeaturePermission) -> dict:
    roles = coerce_stored_roles(row.allowed_roles)
    return {
        "id": str(row.id),
        "feature_key": row.feature_key,
        "description": row.description,
        "allowed_roles": roles,
        "is_active": bool(row.is_active),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def ensure_default_feature_permissions(
    db: AsyncSession,
    *,
    commit: bool = False,
) -> int:
    """
    Insert default features if missing (idempotent).

    Hardening H-1: never commit unless commit=True (startup dedicated session).
    Request paths must use commit=False and only flush so the caller's UoW owns commit.

    Hardening M-1: per-row savepoint absorbs concurrent unique races.
    """
    result = await db.execute(select(FeaturePermission.feature_key))
    existing = {r[0] for r in result.all()}
    inserted = 0
    now = datetime.now(timezone.utc)

    for item in DEFAULT_FEATURES:
        key = item["feature_key"]
        if key in existing:
            continue
        row = FeaturePermission(
            id=uuid.uuid4(),
            feature_key=key,
            description=item["description"],
            allowed_roles=list(item["allowed_roles"]),
            is_active=bool(item["is_active"]),
            created_at=now,
            updated_at=now,
        )
        try:
            # Nested transaction / savepoint when supported (Postgres, SQLite)
            async with db.begin_nested():
                db.add(row)
                await db.flush()
            inserted += 1
            existing.add(key)
        except IntegrityError:
            # M-1: concurrent insert of same feature_key
            logger.info(
                "FEATURE_PERMISSIONS_SEED | concurrent insert race on feature_key=%s ignored",
                key,
            )
            existing.add(key)

    if inserted:
        if commit:
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                logger.info(
                    "FEATURE_PERMISSIONS_SEED | commit race absorbed; treating as already seeded"
                )
                return 0
        else:
            # H-1: caller owns commit (request session) — flush only
            await db.flush()

    return inserted


def ensure_default_feature_permissions_sync(
    db: Session,
    *,
    commit: bool = False,
) -> int:
    """
    Sync counterpart of ensure_default_feature_permissions for paper-trading gates.

    Inserts missing DEFAULT_FEATURES rows (idempotent). Request paths should use
    commit=False so the caller's UoW owns the commit.
    """
    existing = {
        r[0]
        for r in db.execute(select(FeaturePermission.feature_key)).all()
    }
    inserted = 0
    now = datetime.now(timezone.utc)

    for item in DEFAULT_FEATURES:
        key = item["feature_key"]
        if key in existing:
            continue
        row = FeaturePermission(
            id=uuid.uuid4(),
            feature_key=key,
            description=item["description"],
            allowed_roles=list(item["allowed_roles"]),
            is_active=bool(item["is_active"]),
            created_at=now,
            updated_at=now,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            inserted += 1
            existing.add(key)
        except IntegrityError:
            logger.info(
                "FEATURE_PERMISSIONS_SEED_SYNC | concurrent insert race on feature_key=%s ignored",
                key,
            )
            existing.add(key)

    if inserted:
        if commit:
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                logger.info(
                    "FEATURE_PERMISSIONS_SEED_SYNC | commit race absorbed; treating as already seeded"
                )
                return 0
        else:
            db.flush()

    return inserted


async def assert_feature_permissions_table_ready(
    db: AsyncSession,
    *,
    fail_closed: bool = False,
) -> bool:
    """
    Verify feature_permissions is queryable (M-5).

    Returns True if ready. If fail_closed and table missing / unusable, raises.
    """
    try:
        await db.execute(select(FeaturePermission.feature_key).limit(1))
        return True
    except (ProgrammingError, OperationalError) as e:
        logger.error(
            "FEATURE_PERMISSIONS_TABLE_MISSING | error_type=%s | error=%s",
            type(e).__name__,
            str(e)[:300],
        )
        if fail_closed:
            raise RuntimeError(
                "feature_permissions table is not available. "
                "Run `alembic upgrade head` before starting in production/staging."
            ) from e
        return False
    except Exception as e:
        logger.warning(
            "FEATURE_PERMISSIONS_TABLE_CHECK | unexpected error: %s",
            e,
        )
        if fail_closed:
            raise
        return False


async def list_features(db: AsyncSession) -> list[FeaturePermission]:
    """All features (active + inactive), ordered by feature_key ASC."""
    await ensure_default_feature_permissions(db, commit=False)
    result = await db.execute(
        select(FeaturePermission).order_by(FeaturePermission.feature_key.asc())
    )
    return list(result.scalars().all())


async def get_by_key(
    db: AsyncSession, feature_key: str, *, for_update: bool = False
) -> FeaturePermission:
    await ensure_default_feature_permissions(db, commit=False)
    stmt = select(FeaturePermission).where(
        FeaturePermission.feature_key == feature_key
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found",
        )
    return row


def _evaluate_feature_row(row: FeaturePermission | None, role: Any) -> bool:
    """Shared fail-closed evaluation for async/sync accessors."""
    role_n = resolve_feature_role(role)
    if role_n is None:
        return False
    if row is None:
        return False
    if not row.is_active:
        return False
    roles = coerce_stored_roles(row.allowed_roles)
    return role_n in roles


async def _load_feature_row(
    db: AsyncSession, feature_key: str
) -> FeaturePermission | None:
    result = await db.execute(
        select(FeaturePermission).where(
            FeaturePermission.feature_key == feature_key
        )
    )
    return result.scalar_one_or_none()


async def can_access_feature(
    db: AsyncSession, feature_key: str, role: Any
) -> bool:
    """
    Fail-closed feature access check (FR-028).

    Unknown roles deny; missing/inactive features deny.
    Does not use normalize_role clamping to trader.
    Seeds missing defaults only when the requested key is absent (warm path skips seed).
    """
    if resolve_feature_role(role) is None:
        return False
    row = await _load_feature_row(db, feature_key)
    if row is None:
        # Cold/partial catalog: insert-if-missing then re-read this key only
        await ensure_default_feature_permissions(db, commit=False)
        row = await _load_feature_row(db, feature_key)
    return _evaluate_feature_row(row, role)


def can_access_feature_sync(db: Session, feature_key: str, role: Any) -> bool:
    """Sync variant for paper-trading and other sync FastAPI handlers (SQLAlchemy 2.x)."""
    try:
        if resolve_feature_role(role) is None:
            return False
        row = db.execute(
            select(FeaturePermission).where(
                FeaturePermission.feature_key == feature_key
            )
        ).scalar_one_or_none()
        if row is None:
            ensure_default_feature_permissions_sync(db, commit=False)
            row = db.execute(
                select(FeaturePermission).where(
                    FeaturePermission.feature_key == feature_key
                )
            ).scalar_one_or_none()
        return _evaluate_feature_row(row, role)
    except Exception as exc:
        # Fail closed if catalog is unavailable (e.g. schema not migrated on this engine)
        logger.warning(
            "can_access_feature_sync failed closed | feature=%s | err=%s",
            feature_key,
            exc,
        )
        return False


async def update_feature_permission(
    db: AsyncSession,
    *,
    actor: User,
    feature_key: str,
    allowed_roles: Optional[list[str]] = None,
    is_active: Optional[bool] = None,
    description: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> FeaturePermission:
    """Update feature permission with critical safety and audit on material change."""
    if allowed_roles is None and is_active is None and description is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of allowed_roles, is_active, description must be provided",
        )

    if description is not None and str(description).strip() == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="description must not be blank",
        )

    row = await get_by_key(db, feature_key, for_update=True)

    # M-2: never 422 on corrupt stored roles when reading previous state
    prev_roles = coerce_stored_roles(row.allowed_roles)
    prev_active = bool(row.is_active)
    prev_desc = row.description

    new_roles = prev_roles
    if allowed_roles is not None:
        new_roles = normalize_allowed_roles(allowed_roles)

    new_active = prev_active if is_active is None else bool(is_active)
    new_desc = prev_desc if description is None else str(description).strip()

    is_critical = feature_key in CRITICAL_FEATURE_KEYS

    if is_critical:
        if UserRole.ADMIN.value not in new_roles:
            logger.warning(
                "CRITICAL_FEATURE_PROTECTION | actor=%s feature_key=%s | refused remove admin",
                getattr(actor, "id", None),
                feature_key,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=CANNOT_REMOVE_ADMIN,
            )
        if new_active is False:
            logger.warning(
                "CRITICAL_FEATURE_PROTECTION | actor=%s feature_key=%s | refused deactivate",
                getattr(actor, "id", None),
                feature_key,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=CANNOT_DEACTIVATE,
            )

    # No-op
    if (
        new_roles == prev_roles
        and new_active == prev_active
        and new_desc == prev_desc
    ):
        return row

    row.allowed_roles = new_roles
    row.is_active = new_active
    row.description = new_desc
    row.updated_at = datetime.now(timezone.utc)

    actor_id: Optional[uuid.UUID]
    if isinstance(actor.id, uuid.UUID):
        actor_id = actor.id
    else:
        try:
            actor_id = uuid.UUID(str(actor.id))
        except Exception:
            actor_id = None

    metadata = {
        "actor_user_id": str(actor.id),
        "feature_key": feature_key,
        "previous_allowed_roles": prev_roles,
        "new_allowed_roles": new_roles,
        "previous_is_active": prev_active,
        "new_is_active": new_active,
        "previous_description": prev_desc,
        "new_description": new_desc,
    }
    audit = AuditLog(
        user_id=actor_id,
        event_type=EVENT_FEATURE_PERMISSION_CHANGE,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata_=metadata,
    )
    db.add(audit)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(
            "FEATURE_PERMISSION_UPDATE_FAILED | feature_key=%s actor=%s",
            feature_key,
            getattr(actor, "id", None),
        )
        raise
    await db.refresh(row)
    return row
