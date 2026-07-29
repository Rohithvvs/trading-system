"""Tests for get_current_admin_user live-store admin gate (Sprint 2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin_user
from app.core.roles import UserRole
from app.core.security import get_password_hash
from app.models.auth import User


def _make_user(**kwargs) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        email=f"u_{uuid.uuid4().hex[:8]}@example.com",
        full_name="Test User",
        password_hash=get_password_hash("Password123!"),
        role=UserRole.TRADER.value,
        is_active=True,
        provider="email",
        deleted_at=None,
    )
    defaults.update(kwargs)
    return User(**defaults)


@pytest.mark.asyncio
async def test_get_current_admin_user_allows_active_admin():
    admin = _make_user(role=UserRole.ADMIN.value, email="admin_gate@example.com")
    out = await get_current_admin_user(current_user=admin)
    assert out.role == UserRole.ADMIN.value
    assert out.id == admin.id


@pytest.mark.asyncio
async def test_get_current_admin_user_rejects_trader():
    trader = _make_user(role=UserRole.TRADER.value)
    with pytest.raises(HTTPException) as exc:
        await get_current_admin_user(current_user=trader)
    assert exc.value.status_code == 403
    assert "Admin" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_current_admin_user_rejects_soft_deleted_admin():
    admin = _make_user(
        role=UserRole.ADMIN.value,
        deleted_at=datetime.now(timezone.utc),
    )
    with pytest.raises(HTTPException) as exc:
        await get_current_admin_user(current_user=admin)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_active_user_rejects_inactive_before_admin_gate():
    """Inactive users never reach admin role check (403 from active gate)."""
    from app.core.deps import get_current_active_user

    inactive = _make_user(role=UserRole.ADMIN.value, is_active=False)
    with pytest.raises(HTTPException) as exc:
        await get_current_active_user(current_user=inactive)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_active_user_rejects_soft_deleted():
    """Audit L-4: soft-deleted accounts cannot use protected APIs."""
    from app.core.deps import get_current_active_user

    deleted = _make_user(
        role=UserRole.TRADER.value,
        is_active=True,
        deleted_at=datetime.now(timezone.utc),
    )
    with pytest.raises(HTTPException) as exc:
        await get_current_active_user(current_user=deleted)
    assert exc.value.status_code == 403
    assert "unavailable" in str(exc.value.detail).lower()
