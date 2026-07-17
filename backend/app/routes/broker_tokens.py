"""REST API for encrypted broker access tokens (Capital page)."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TypeVar

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deps import get_current_user
from ..db.session import AsyncSessionLocal, dispose_async_pool, is_stale_prepared_plan_error
from ..models.auth import User
from ..services import broker_token_service as bts

router = APIRouter(prefix="/api/broker-tokens", tags=["broker-tokens"])
logger = logging.getLogger("app.broker_tokens")

T = TypeVar("T")


def _error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        content={"success": False, "message": message},
        status_code=status_code,
    )


def _ok(data: dict | None = None) -> JSONResponse:
    result = {"success": True}
    if data:
        result.update(data)
    return JSONResponse(content=result)


async def _with_db_retry(op: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run DB work; on stale asyncpg plan after DDL, dispose pool and retry once."""
    async with AsyncSessionLocal() as db:
        try:
            return await op(db)
        except Exception as exc:
            if not is_stale_prepared_plan_error(exc):
                raise
            try:
                await db.rollback()
            except Exception:
                pass
            logger.warning("Broker token DB op hit stale prepared plan; disposing pool and retrying once")
    await dispose_async_pool(reason="broker_tokens_stale_plan")
    async with AsyncSessionLocal() as db:
        return await op(db)


class BrokerTokenPayload(BaseModel):
    broker: str = Field(default="FYERS")
    access_token: str = Field(min_length=1)
    api_key: str | None = None
    api_secret: str | None = None
    token_expiry: datetime | None = None
    notes: str | None = None
    run_validation: bool = Field(default=True, alias="validate")

    model_config = {"populate_by_name": True}


class BrokerTestPayload(BaseModel):
    broker: str = Field(default="FYERS")
    access_token: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    run_validation: bool = Field(default=True, alias="validate")

    model_config = {"populate_by_name": True}


class BrokerTokenUpdatePayload(BaseModel):
    broker: str = Field(default="FYERS")
    access_token: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    token_expiry: datetime | None = None
    notes: str | None = None
    run_validation: bool = Field(default=True, alias="validate")

    model_config = {"populate_by_name": True}


class BrokerQuery(BaseModel):
    broker: str = "FYERS"


@router.get("")
async def get_broker_token(
    broker: str = "FYERS",
    user: User = Depends(get_current_user),
):
    """Return masked token metadata for the logged-in user (never plaintext)."""
    logger.info("BROKER_TOKEN_GET_REQUEST | user_id=%s broker=%s", user.id, broker)
    try:
        data = await _with_db_retry(lambda db: bts.get_token(db, user.id, broker=broker))
        logger.info("BROKER_TOKEN_GET_RESPONSE | user_id=%s broker=%s exists=%s", user.id, broker, data.get("exists"))
        return _ok(data)
    except Exception as exc:
        logger.error("BROKER_TOKEN_GET_EXCEPTION | user_id=%s broker=%s error=%s", user.id, broker, exc, exc_info=True)
        return _error("Unable to load token information.", 500)


@router.get("/list")
async def list_broker_tokens(
    user: User = Depends(get_current_user),
):
    try:
        items = await _with_db_retry(lambda db: bts.list_tokens(db, user.id))
        return _ok({"items": items})
    except Exception as exc:
        logger.error("Failed to list broker tokens: %s", exc, exc_info=True)
        return _error("Unable to list tokens.", 500)


@router.post("")
async def create_broker_token(
    payload: BrokerTokenPayload,
    user: User = Depends(get_current_user),
):
    """Validate (optional), encrypt, and save broker token for current user."""
    logger.info(
        "BROKER_TOKEN_SAVE_REQUEST | user_id=%s broker=%s validate=%s token_len=%d",
        user.id, payload.broker, payload.run_validation, len(payload.access_token) if payload.access_token else 0,
    )
    try:
        result = await _with_db_retry(
            lambda db: bts.save_token(
                db,
                user.id,
                broker=payload.broker,
                access_token=payload.access_token,
                api_key=payload.api_key,
                api_secret=payload.api_secret,
                token_expiry=payload.token_expiry,
                notes=payload.notes,
                validate=payload.run_validation,
            )
        )
        if result.get("status") == "error":
            logger.warning(
                "BROKER_TOKEN_SAVE_FAILED | user_id=%s broker=%s reason=%s",
                user.id, payload.broker, result.get("message"),
            )
            return _error(result.get("message") or "Unable to save broker token.")
        response_data = dict(result)
        response_data["message"] = result.get("message") or "Token saved successfully."
        logger.info(
            "BROKER_TOKEN_SAVE_SUCCESS | user_id=%s broker=%s masked=%s",
            user.id, payload.broker, result.get("token", {}).get("token_masked"),
        )
        return _ok(response_data)
    except Exception as exc:
        logger.error("BROKER_TOKEN_SAVE_EXCEPTION | user_id=%s broker=%s error=%s", user.id, payload.broker, exc, exc_info=True)
        return _error("Unable to save broker token.", 500)


@router.put("")
async def update_broker_token(
    payload: BrokerTokenUpdatePayload,
    user: User = Depends(get_current_user),
):
    try:
        result = await _with_db_retry(
            lambda db: bts.update_token(
                db,
                user.id,
                broker=payload.broker,
                access_token=payload.access_token,
                api_key=payload.api_key,
                api_secret=payload.api_secret,
                token_expiry=payload.token_expiry,
                notes=payload.notes,
                validate=payload.run_validation,
            )
        )
        if result.get("status") == "error":
            return _error(result.get("message") or "Unable to save broker token.")
        response_data = dict(result)
        response_data["message"] = result.get("message") or "Token saved successfully."
        return _ok(response_data)
    except Exception as exc:
        logger.error("Failed to update broker token: %s", exc, exc_info=True)
        return _error("Unable to save broker token.", 500)


@router.delete("")
async def delete_broker_token(
    broker: str = "FYERS",
    user: User = Depends(get_current_user),
):
    try:
        result = await _with_db_retry(lambda db: bts.delete_token(db, user.id, broker=broker))
        return _ok(result)
    except Exception as exc:
        logger.error("Failed to delete broker token: %s", exc, exc_info=True)
        return _error("Unable to delete access token.", 500)


@router.post("/validate")
async def validate_broker_token(
    broker: str = "FYERS",
    user: User = Depends(get_current_user),
):
    """Test connection / re-validate stored token against broker."""
    try:
        result = await _with_db_retry(lambda db: bts.validate_token(db, user.id, broker=broker))
        if result.get("status") == "error":
            return _error(result.get("message") or "Validation failed.")
        return _ok(result)
    except Exception as exc:
        logger.error("Failed to validate broker token: %s", exc, exc_info=True)
        return _error("Unable to validate access token.", 500)


@router.post("/test-connection")
async def test_broker_connection(
    payload: BrokerTestPayload | None = None,
    broker: str = "FYERS",
    user: User = Depends(get_current_user),
):
    """
    Test connection. If body includes access_token, validate that token without
    requiring a prior save. Otherwise validate the stored token.
    """
    try:
        body = payload or BrokerTestPayload()
        use_broker = (body.broker or broker or "FYERS").upper()
        if body.access_token and body.access_token.strip():
            if use_broker == "FYERS":
                ok, reason = await bts._validate_fyers(body.access_token.strip())
                if not ok:
                    return _error(reason or "Connection failed.")
                return _ok({"message": "Connected Successfully", "connection_status": "Connected"})
            return _ok({"message": "Connected Successfully", "connection_status": "Connected"})

        result = await _with_db_retry(lambda db: bts.validate_token(db, user.id, broker=use_broker))
        if result.get("status") == "error":
            return _error(result.get("message") or "Connection failed.")
        return _ok({
            "message": "Connected Successfully",
            "connection_status": result.get("connection_status"),
            "token": result.get("token"),
        })
    except Exception as exc:
        logger.error("Failed to test broker connection: %s", exc, exc_info=True)
        return _error("Unable to test connection.", 500)
