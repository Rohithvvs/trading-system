"""Integration tests for Sprint 4 – DB storage + monitoring
(feature: 009-db-storage-monitoring).

Complements root tests/test_token_persistence.py with backend-suite markers
and reuse of the shared async session patterns used by other integration tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.pool import StaticPool

from backend.app.core.token_crypto import is_encrypted
from backend.app.db.base import Base
from backend.app.models import FyersToken
from backend.app.services.token_service import (
    _decrypt_from_storage,
    _encrypt_for_storage,
    generate_and_persist_fyers_token,
)
from fyers_token import FyersAuthError


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "CHAR(36)"


@pytest.fixture()
async def db_maker():
    """Session factory over isolated in-memory SQLite (APP_ENV=test)."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    with mock.patch(
        "backend.app.services.token_service.settings.app_env",
        "test",
    ):
        yield maker
    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fr007_success_fields_committed_atomically(db_maker):
    """FR-007: after success, token + status + last_error + timestamp are consistent."""
    token = "atomic_success_token_001"

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value=token,
    ):
        async with db_maker() as db:
            result = await generate_and_persist_fyers_token(db)

    assert result["status"] == "Success"
    assert result.get("token_preview")
    assert token not in str(result["token_preview"])
    async with db_maker() as db:
        row = (await db.scalars(select(FyersToken).where(FyersToken.id == 1))).first()
    assert row is not None
    assert row.status == "Success"
    assert row.last_error is None
    assert is_encrypted(row.access_token)
    assert _decrypt_from_storage(row.access_token) == token
    assert row.access_token_saved_at is not None
    assert row.is_active is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fr007_failure_fields_committed_atomically(db_maker):
    """FR-007: failure write keeps token and sets status+error together."""
    now = datetime.now(timezone.utc)
    async with db_maker() as db:
        db.add(
            FyersToken(
                id=1,
                access_token=_encrypt_for_storage("pre_existing"),
                status="Success",
                is_active=True,
                access_token_saved_at=now,
                created_at=now,
            )
        )
        await db.commit()

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        side_effect=FyersAuthError("atomic fail message"),
    ):
        async with db_maker() as db:
            with pytest.raises(FyersAuthError):
                await generate_and_persist_fyers_token(db)

    async with db_maker() as db:
        row = (await db.scalars(select(FyersToken).where(FyersToken.id == 1))).first()
    assert row is not None
    assert row.status == "Failed"
    assert "atomic fail message" in (row.last_error or "")
    assert _decrypt_from_storage(row.access_token) == "pre_existing"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reuse_existing_models_and_session(db_maker):
    """FR-006: persistence operates on existing FyersToken model + AsyncSession."""
    assert FyersToken.__tablename__ == "fyers_tokens"

    with mock.patch(
        "fyers_token.generate_fyers_access_token",
        return_value="reuse_models_token",
    ):
        async with db_maker() as db:
            await generate_and_persist_fyers_token(db)

    async with db_maker() as db:
        row = (await db.scalars(select(FyersToken).where(FyersToken.id == 1))).first()
    assert isinstance(row, FyersToken)
    assert row.status == "Success"
