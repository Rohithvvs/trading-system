"""Unit / service tests for default admin bootstrap (US3)."""

import uuid

import pytest
from sqlalchemy import select, func

from app.services.admin_bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_NAME,
    ensure_default_admin,
    ensure_default_admin_safe,
    warn_if_default_admin_password_in_use,
    _SPEC_DEFAULT_ADMIN_PASSWORD,
)
from app.core.roles import UserRole
from app.core.security import verify_password, get_password_hash
from app.models.auth import User


def test_admin_bootstrap_constants():
    """AC-ADM-01 constants match specification defaults."""
    assert DEFAULT_ADMIN_EMAIL == "admin@example.com"
    assert DEFAULT_ADMIN_PASSWORD == "Admin@123"
    assert DEFAULT_ADMIN_NAME == "Default Admin"
    assert _SPEC_DEFAULT_ADMIN_PASSWORD == "Admin@123"


@pytest.mark.asyncio
async def test_ensure_default_admin_seeds_account(async_db_session):
    """AC-ADM-01: creates admin@example.com with hashed Admin@123 and role admin."""
    created = await ensure_default_admin(async_db_session)
    assert created is True

    result = await async_db_session.execute(
        select(User).where(User.email == DEFAULT_ADMIN_EMAIL)
    )
    admin = result.scalar_one()
    assert admin.role == UserRole.ADMIN.value
    assert admin.full_name == DEFAULT_ADMIN_NAME
    assert verify_password(DEFAULT_ADMIN_PASSWORD, admin.password_hash)


@pytest.mark.asyncio
async def test_ensure_default_admin_idempotent(async_db_session):
    """AC-ADM-02: second call is a no-op."""
    assert await ensure_default_admin(async_db_session) is True
    assert await ensure_default_admin(async_db_session) is False

    count = await async_db_session.execute(
        select(func.count()).select_from(User).where(User.email == DEFAULT_ADMIN_EMAIL)
    )
    assert count.scalar_one() == 1


@pytest.mark.asyncio
async def test_ensure_default_admin_skips_when_any_admin_exists(async_db_session):
    """AC-ADM-02: any admin role prevents default seed."""
    async_db_session.add(
        User(
            id=uuid.uuid4(),
            email="ops@example.com",
            full_name="Ops Admin",
            password_hash=get_password_hash("OpsAdmin1!"),
            role=UserRole.ADMIN.value,
            is_active=True,
            provider="email",
        )
    )
    await async_db_session.commit()

    assert await ensure_default_admin(async_db_session) is False
    result = await async_db_session.execute(
        select(User).where(User.email == DEFAULT_ADMIN_EMAIL)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_warn_scans_all_admins_with_default_password(async_db_session, caplog):
    """M-1: default password check covers any admin email, not only bootstrap email."""
    async_db_session.add(
        User(
            id=uuid.uuid4(),
            email="other-admin@example.com",
            full_name="Other Admin",
            password_hash=get_password_hash(_SPEC_DEFAULT_ADMIN_PASSWORD),
            role=UserRole.ADMIN.value,
            is_active=True,
            provider="email",
        )
    )
    await async_db_session.commit()

    import logging

    with caplog.at_level(logging.CRITICAL, logger="app.services.admin_bootstrap"):
        await warn_if_default_admin_password_in_use(async_db_session)
    assert any("ADMIN_DEFAULT_PASSWORD_IN_USE" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_ensure_default_admin_safe_non_prod_swallows(async_db_session, monkeypatch):
    """M-4: safe wrapper continues in non-production on unexpected errors."""

    async def boom(_db):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "app.services.admin_bootstrap_service.ensure_default_admin",
        boom,
    )
    # fail_closed=False should not raise
    assert await ensure_default_admin_safe(async_db_session, fail_closed=False) is False
