"""Unit/service tests for feature_permission_service (Sprint 3 US3/US4)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.feature_permission import FeaturePermission  # noqa: F401 — register
from app.models.auth import User, AuditLog  # noqa: F401
from app.services import feature_permission_service as fps
from app.core.roles import UserRole


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def async_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _prep():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run(_prep())
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker

    async def _dispose():
        await engine.dispose()

    _run(_dispose())


def test_normalize_allowed_roles_order_and_dedupe():
    assert fps.normalize_allowed_roles(["admin", "trader", "admin"]) == [
        "trader",
        "admin",
    ]
    assert fps.normalize_allowed_roles(["admin"]) == ["admin"]
    assert fps.normalize_allowed_roles([]) == []


def test_resolve_feature_role_domain_only():
    assert fps.resolve_feature_role("Admin") == "admin"
    assert fps.resolve_feature_role("TRADER") == "trader"
    assert fps.resolve_feature_role("superuser") is None
    assert fps.resolve_feature_role("") is None
    assert fps.resolve_feature_role(None) is None


def test_can_access_feature_matrix(async_session_factory):
    async def _body():
        async with async_session_factory() as db:
            await fps.ensure_default_feature_permissions(db)
            # trader on watchlist (allowed)
            assert await fps.can_access_feature(db, "watchlist", "trader") is True
            assert await fps.can_access_feature(db, "watchlist", "admin") is True
            # trader not on admin_panel
            assert await fps.can_access_feature(db, "admin_panel", "trader") is False
            assert await fps.can_access_feature(db, "admin_panel", "admin") is True
            # missing key
            assert await fps.can_access_feature(db, "no_such_feature", "admin") is False
            # unknown role never clamps to trader
            assert (
                await fps.can_access_feature(db, "watchlist", "superuser") is False
            )
            # inactive
            row = await fps.get_by_key(db, "export_data", for_update=True)
            row.is_active = False
            await db.commit()
            assert await fps.can_access_feature(db, "export_data", "admin") is False

    _run(_body())


def test_can_access_reflects_patch(async_session_factory):
    async def _body():
        async with async_session_factory() as db:
            await fps.ensure_default_feature_permissions(db)
            actor = User(
                id=uuid.uuid4(),
                email=f"a_{uuid.uuid4().hex[:8]}@example.com",
                full_name="Actor",
                password_hash="x",
                role=UserRole.ADMIN.value,
                is_active=True,
            )
            db.add(actor)
            await db.commit()
            await db.refresh(actor)

            assert await fps.can_access_feature(db, "watchlist", "trader") is True
            await fps.update_feature_permission(
                db,
                actor=actor,
                feature_key="watchlist",
                allowed_roles=["admin"],
            )
            assert await fps.can_access_feature(db, "watchlist", "trader") is False
            assert await fps.can_access_feature(db, "watchlist", "admin") is True

    _run(_body())


def test_seed_idempotent_no_duplicate_keys(async_session_factory):
    """Edge: re-running ensure_default does not duplicate feature_key rows."""
    async def _body():
        async with async_session_factory() as db:
            n1 = await fps.ensure_default_feature_permissions(db)
            n2 = await fps.ensure_default_feature_permissions(db)
            assert n1 >= 7
            assert n2 == 0
            rows = await fps.list_features(db)
            keys = [r.feature_key for r in rows]
            assert len(keys) == len(set(keys))
            assert len(keys) >= 7

    _run(_body())


def test_helper_accepts_case_normalized_domain_roles(async_session_factory):
    """Edge: helper strip+lower — 'Admin'/'TRADER' match domain; SuperUser denies."""
    async def _body():
        async with async_session_factory() as db:
            await fps.ensure_default_feature_permissions(db)
            assert await fps.can_access_feature(db, "watchlist", "Admin") is True
            assert await fps.can_access_feature(db, "watchlist", "TRADER") is True
            assert await fps.can_access_feature(db, "watchlist", "SuperUser") is False
            assert await fps.can_access_feature(db, "watchlist", "  admin  ") is True

    _run(_body())


def test_normalize_roles_rejects_invalid():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        fps.normalize_allowed_roles(["superuser"])
    assert ei.value.status_code == 422


def test_critical_safety_helpers(async_session_factory):
    async def _body():
        async with async_session_factory() as db:
            await fps.ensure_default_feature_permissions(db)
            actor = User(
                id=uuid.uuid4(),
                email=f"a_{uuid.uuid4().hex[:8]}@example.com",
                full_name="Actor",
                password_hash="x",
                role=UserRole.ADMIN.value,
                is_active=True,
            )
            db.add(actor)
            await db.commit()
            await db.refresh(actor)

            from fastapi import HTTPException

            with pytest.raises(HTTPException) as ei:
                await fps.update_feature_permission(
                    db,
                    actor=actor,
                    feature_key="admin_panel",
                    allowed_roles=["trader"],
                )
            assert ei.value.status_code == 400

            with pytest.raises(HTTPException) as ei2:
                await fps.update_feature_permission(
                    db,
                    actor=actor,
                    feature_key="user_management",
                    is_active=False,
                )
            assert ei2.value.status_code == 400

    _run(_body())
