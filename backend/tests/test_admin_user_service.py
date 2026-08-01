"""Service-level tests for admin_user_service (Sprint 2)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.roles import UserRole
from app.core.security import get_password_hash
from app.models.auth import AuditLog, User
from app.services.admin_user_service import (
    EVENT_ADMIN_ROLE_CHANGE,
    count_active_admins,
    list_users,
    update_user_role,
)


def _user(**kwargs) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        email=f"s_{uuid.uuid4().hex[:8]}@example.com",
        full_name="Svc User",
        password_hash=get_password_hash("Password123!"),
        role=UserRole.TRADER.value,
        is_active=True,
        provider="email",
        deleted_at=None,
    )
    defaults.update(kwargs)
    return User(**defaults)


@pytest.mark.asyncio
async def test_count_active_admins_excludes_inactive_and_deleted(async_db_session):
    active_admin = _user(role=UserRole.ADMIN.value, email="active_admin@example.com")
    inactive_admin = _user(
        role=UserRole.ADMIN.value,
        email="inactive_admin@example.com",
        is_active=False,
    )
    deleted_admin = _user(
        role=UserRole.ADMIN.value,
        email="deleted_admin@example.com",
        deleted_at=datetime.now(timezone.utc),
    )
    trader = _user(role=UserRole.TRADER.value)
    async_db_session.add_all([active_admin, inactive_admin, deleted_admin, trader])
    await async_db_session.commit()

    assert await count_active_admins(async_db_session) == 1


@pytest.mark.asyncio
async def test_list_users_defaults_and_search(async_db_session):
    u1 = _user(email="alice@example.com", full_name="Alice Trader")
    u2 = _user(email="bob@example.com", full_name="Bob Admin", role=UserRole.ADMIN.value)
    inactive = _user(email="gone@example.com", is_active=False)
    async_db_session.add_all([u1, u2, inactive])
    await async_db_session.commit()

    items, total, page, size = await list_users(async_db_session, page=1, size=20)
    assert page == 1 and size == 20
    assert total == 2
    assert all(u.is_active for u in items)

    items_s, total_s, _, _ = await list_users(async_db_session, search="alice")
    assert total_s == 1
    assert items_s[0].email == "alice@example.com"

    items_r, total_r, _, _ = await list_users(async_db_session, role="admin")
    assert total_r == 1
    assert items_r[0].role == UserRole.ADMIN.value

    items_name, total_name, _, _ = await list_users(async_db_session, search="ALICE")
    assert total_name == 1
    assert items_name[0].full_name == "Alice Trader"

    items_tr, total_tr, _, _ = await list_users(async_db_session, role="trader")
    assert total_tr == 1
    assert items_tr[0].role == UserRole.TRADER.value


@pytest.mark.asyncio
async def test_list_users_invalid_page_size_and_role(async_db_session):
    """Unit/boundary: invalid page, size, and role filter raise 422."""
    with pytest.raises(HTTPException) as e1:
        await list_users(async_db_session, page=0)
    assert e1.value.status_code == 422

    with pytest.raises(HTTPException) as e2:
        await list_users(async_db_session, size=101)
    assert e2.value.status_code == 422

    with pytest.raises(HTTPException) as e3:
        await list_users(async_db_session, size=0)
    assert e3.value.status_code == 422

    with pytest.raises(HTTPException) as e4:
        await list_users(async_db_session, role="superuser")
    assert e4.value.status_code == 422


@pytest.mark.asyncio
async def test_list_users_excludes_soft_deleted(async_db_session):
    active = _user(email="alive@example.com")
    deleted = _user(
        email="dead@example.com",
        deleted_at=datetime.now(timezone.utc),
    )
    async_db_session.add_all([active, deleted])
    await async_db_session.commit()
    items, total, _, _ = await list_users(async_db_session)
    assert total == 1
    assert items[0].email == "alive@example.com"


@pytest.mark.asyncio
async def test_update_role_missing_target_404(async_db_session):
    actor = _user(role=UserRole.ADMIN.value, email="actor404@example.com")
    async_db_session.add(actor)
    await async_db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await update_user_role(
            async_db_session,
            actor=actor,
            target_id=uuid.uuid4(),
            new_role="admin",
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_role_noop_no_audit(async_db_session):
    actor = _user(role=UserRole.ADMIN.value, email="actor@example.com")
    target = _user(role=UserRole.TRADER.value, email="target@example.com")
    async_db_session.add_all([actor, target])
    await async_db_session.commit()

    out = await update_user_role(
        async_db_session, actor=actor, target_id=target.id, new_role="trader"
    )
    assert out.role == UserRole.TRADER.value
    logs = (
        await async_db_session.execute(
            select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)
        )
    ).scalars().all()
    assert len(logs) == 0


@pytest.mark.asyncio
async def test_update_role_last_admin_blocked(async_db_session):
    sole = _user(role=UserRole.ADMIN.value, email="sole@example.com")
    async_db_session.add(sole)
    await async_db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await update_user_role(
            async_db_session, actor=sole, target_id=sole.id, new_role="trader"
        )
    assert exc.value.status_code == 400
    await async_db_session.refresh(sole)
    assert sole.role == UserRole.ADMIN.value


@pytest.mark.asyncio
async def test_update_role_promote_writes_audit(async_db_session):
    actor = _user(role=UserRole.ADMIN.value, email="promoter@example.com")
    target = _user(role=UserRole.TRADER.value, email="promotee@example.com")
    async_db_session.add_all([actor, target])
    await async_db_session.commit()

    out = await update_user_role(
        async_db_session, actor=actor, target_id=target.id, new_role="admin"
    )
    assert out.role == UserRole.ADMIN.value
    log = (
        await async_db_session.execute(
            select(AuditLog).where(AuditLog.event_type == EVENT_ADMIN_ROLE_CHANGE)
        )
    ).scalar_one()
    assert log.metadata_["previous_role"] == "trader"
    assert log.metadata_["new_role"] == "admin"
    assert log.metadata_["target_user_id"] == str(target.id)


def test_lock_active_admins_statement_uses_for_update():
    """Audit H-1 / M-2: demotion lock query requests FOR UPDATE (Postgres enforces)."""
    from sqlalchemy.dialects import postgresql
    from app.models.auth import User
    from app.core.roles import UserRole
    from sqlalchemy import select

    stmt = (
        select(User)
        .where(
            User.role == UserRole.ADMIN.value,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .order_by(User.id)
        .with_for_update()
    )
    compiled = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}))
    assert "FOR UPDATE" in compiled.upper()


@pytest.mark.asyncio
async def test_sequential_demote_second_of_two_then_last_blocked(async_db_session):
    """Audit M-2: after demoting one of two admins, demoting the last is refused."""
    a1 = _user(role=UserRole.ADMIN.value, email="a1_seq@example.com")
    a2 = _user(role=UserRole.ADMIN.value, email="a2_seq@example.com")
    async_db_session.add_all([a1, a2])
    await async_db_session.commit()

    out = await update_user_role(
        async_db_session, actor=a1, target_id=a2.id, new_role="trader"
    )
    assert out.role == UserRole.TRADER.value

    with pytest.raises(HTTPException) as exc:
        await update_user_role(
            async_db_session, actor=a1, target_id=a1.id, new_role="trader"
        )
    assert exc.value.status_code == 400
    await async_db_session.refresh(a1)
    assert a1.role == UserRole.ADMIN.value
