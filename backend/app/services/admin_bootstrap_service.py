import logging
import os
import uuid
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.auth import User
from ..core.roles import UserRole
from ..core.security import get_password_hash, verify_password

logger = logging.getLogger("app.services.admin_bootstrap")

# Spec defaults (FR-012). Prefer env overrides in non-local deployments.
DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com").strip() or "admin@example.com"
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin@123")
DEFAULT_ADMIN_NAME = os.getenv("DEFAULT_ADMIN_NAME", "Default Admin").strip() or "Default Admin"

# Hardcoded bootstrap password from the specification (security monitor target).
_SPEC_DEFAULT_ADMIN_PASSWORD = "Admin@123"


async def warn_if_default_admin_password_in_use(db: AsyncSession) -> None:
    """
    Emit CRITICAL when any admin account still accepts the well-known bootstrap password (R-002 / M-1).
    Checks all role=admin users, not only the bootstrap email.
    """
    try:
        result = await db.execute(select(User).where(User.role == UserRole.ADMIN.value))
        admins = result.scalars().all()
        for admin in admins:
            if not admin.password_hash:
                continue
            if verify_password(_SPEC_DEFAULT_ADMIN_PASSWORD, admin.password_hash):
                logger.critical(
                    "ADMIN_DEFAULT_PASSWORD_IN_USE | email=%s | "
                    "An admin account still accepts the well-known bootstrap password Admin@123. "
                    "Change it immediately before production use.",
                    admin.email,
                )
    except Exception as e:
        logger.warning("ADMIN_DEFAULT_PASSWORD_CHECK_FAILED | error=%s", e)


async def count_admins(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(User).where(User.role == UserRole.ADMIN.value)
    )
    return int(result.scalar_one() or 0)


async def ensure_default_admin(db: AsyncSession) -> bool:
    """
    Checks if any account with role = 'admin' exists in the database.
    If 0 admin accounts exist, automatically creates the default administrator account.
    Returns True if default admin was seeded, False if an admin already exists / race lost.
    Idempotent and safe under multi-instance startup races (unique email).
    Raises on unexpected failures after rollback so callers can fail closed in production.
    """
    try:
        stmt = select(User).where(User.role == UserRole.ADMIN.value)
        result = await db.execute(stmt)
        existing_admin = result.scalars().first()

        if existing_admin:
            logger.info(
                "ADMIN_BOOTSTRAP | Admin user exists (%s), skipping bootstrap.",
                existing_admin.email,
            )
            await warn_if_default_admin_password_in_use(db)
            return False

        logger.warning(
            "ADMIN_BOOTSTRAP | Zero admin users found. Seeding default administrator account..."
        )
        admin_user = User(
            id=uuid.uuid4(),
            email=DEFAULT_ADMIN_EMAIL,
            full_name=DEFAULT_ADMIN_NAME,
            password_hash=get_password_hash(DEFAULT_ADMIN_PASSWORD),
            role=UserRole.ADMIN.value,
            is_active=True,
            is_email_verified=True,
            provider="email",
        )
        db.add(admin_user)
        try:
            await db.commit()
            await db.refresh(admin_user)
        except IntegrityError:
            # Concurrent pod already created admin@... (or another unique collision).
            await db.rollback()
            logger.info(
                "ADMIN_BOOTSTRAP | Concurrent create detected for %s; treating as idempotent skip.",
                DEFAULT_ADMIN_EMAIL,
            )
            await warn_if_default_admin_password_in_use(db)
            return False

        logger.info(
            "ADMIN_BOOTSTRAP_SUCCESS | Created default admin account (%s).",
            DEFAULT_ADMIN_EMAIL,
        )
        if DEFAULT_ADMIN_PASSWORD == _SPEC_DEFAULT_ADMIN_PASSWORD:
            logger.critical(
                "ADMIN_DEFAULT_PASSWORD_IN_USE | email=%s | "
                "Seeded with well-known bootstrap password. Change it immediately before production use.",
                DEFAULT_ADMIN_EMAIL,
            )
        else:
            # Still scan in case of race-created default account.
            await warn_if_default_admin_password_in_use(db)
        return True
    except Exception as e:
        await db.rollback()
        logger.error("ADMIN_BOOTSTRAP_FAILED | Error seeding default admin: %s", e)
        raise


async def ensure_default_admin_safe(db: AsyncSession, *, fail_closed: bool = False) -> bool:
    """
    Wrapper used at startup.
    - fail_closed=False (dev/test): log and continue on failure.
    - fail_closed=True (production/staging): re-raise if bootstrap fails and no admin remains.
    """
    try:
        return await ensure_default_admin(db)
    except Exception:
        if not fail_closed:
            logger.warning("ADMIN_BOOTSTRAP | Continuing without fail-closed (non-production).")
            return False
        # Verify whether any admin exists despite the error.
        try:
            n = await count_admins(db)
        except Exception:
            n = 0
        if n == 0:
            logger.critical(
                "ADMIN_BOOTSTRAP_FATAL | Bootstrap failed and zero admin users exist. "
                "Refusing to start in production/staging."
            )
            raise
        logger.warning(
            "ADMIN_BOOTSTRAP | Bootstrap error but %s admin(s) already exist; continuing.",
            n,
        )
        return False
