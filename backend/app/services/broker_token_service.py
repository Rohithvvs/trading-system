"""User-scoped broker token management with encryption at rest.

Persists credentials in ``broker_tokens`` (never returns full secrets) and
mirrors the active FYERS access token into ``fyers_tokens`` so existing market
data services keep working.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.token_crypto import decrypt_secret, encrypt_secret, mask_secret
from ..models.broker_token import BrokerToken
from ..models.fyers_token import FyersToken
from ..models.fyers_token_history import FyersTokenHistory
from ..services.token_service import (
    _decode_jwt_expiry,
    _mask_token,
    _set_token_cache,
    _clear_token_cache,
)

logger = logging.getLogger("app.broker_token")

SUPPORTED_BROKERS = {"FYERS", "ZERODHA", "UPSTOX", "ANGEL", "OTHER"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _connection_status(row: BrokerToken | None) -> str:
    if row is None or not row.is_active:
        return "Disconnected"
    if (row.status or "").lower() in ("invalid", "error"):
        return "Invalid Token"
    exp = row.token_expiry
    if exp is not None:
        exp_aware = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
        remaining = (exp_aware - _now()).total_seconds()
        if remaining <= 0:
            return "Expired"
        if remaining < 3600:
            return "Expiring Soon"
    if (row.status or "").lower() == "active":
        return "Connected"
    return row.status or "Disconnected"


def _public_view(row: BrokerToken) -> dict[str, Any]:
    exp = row.token_expiry
    expires_in = None
    if exp is not None:
        exp_aware = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
        expires_in = max(0, int((exp_aware - _now()).total_seconds()))
    return {
        "id": row.id,
        "broker": row.broker,
        "token_masked": row.token_masked or mask_secret("xxxx"),
        "has_api_key": bool(row.encrypted_api_key),
        "has_api_secret": bool(row.encrypted_api_secret),
        "token_expiry": exp.isoformat() if exp else None,
        "expires_in_seconds": expires_in,
        "notes": row.notes,
        "status": row.status,
        "connection_status": _connection_status(row),
        "is_active": bool(row.is_active),
        "last_validated_at": row.last_validated_at.isoformat() if row.last_validated_at else None,
        "last_error": row.last_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        # Never include plaintext token / api_secret / api_key
    }


async def get_token(db: AsyncSession, user_id: UUID, broker: str = "FYERS") -> dict[str, Any]:
    broker = (broker or "FYERS").upper()
    row = (
        await db.scalars(
            select(BrokerToken).where(
                BrokerToken.user_id == user_id,
                BrokerToken.broker == broker,
            )
        )
    ).first()
    if not row:
        logger.info("BROKER_TOKEN_GET_NOT_FOUND | user=%s broker=%s query_params=[user_id=%s, broker=%s]",
                     str(user_id)[:8], broker, user_id, broker)
        return {
            "exists": False,
            "broker": broker,
            "connection_status": "Disconnected",
            "token_masked": None,
        }
    logger.info("BROKER_TOKEN_GET_FOUND | user=%s broker=%s row_id=%d masked=%s",
                str(user_id)[:8], broker, row.id, row.token_masked)
    view = _public_view(row)
    view["exists"] = True
    return view


async def list_tokens(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    rows = (
        await db.scalars(
            select(BrokerToken).where(BrokerToken.user_id == user_id).order_by(BrokerToken.updated_at.desc())
        )
    ).all()
    return [_public_view(r) for r in rows]


async def _validate_fyers(access_token: str) -> tuple[bool, str]:
    """Validate against FYERS profile API when broker is FYERS."""
    try:
        from ..routes.settings import _validate_token_with_fyers
        from ..config import settings

        if settings.app_env == "test" and "e2e-access-token" in access_token:
            return True, "Test environment bypass"
        return await _validate_token_with_fyers(access_token)
    except Exception as exc:
        logger.warning("Broker validation error: %s", type(exc).__name__, exc_info=True)
        return False, "Token validation failed. Please check your token and try again."


async def _mirror_to_fyers_tokens(db: AsyncSession, access_token: str, expires_at: datetime | None) -> None:
    """Keep system-wide FYERS token in sync for market data (encrypted at rest)."""
    now = _now()
    encrypted = encrypt_secret(access_token)
    await db.execute(
        update(FyersToken)
        .where(FyersToken.is_active == True)  # noqa: E712
        .values(is_active=False, status="inactive")
    )
    row = (await db.scalars(select(FyersToken).filter(FyersToken.id == 1))).one_or_none()
    if row:
        row.access_token = encrypted
        row.is_active = True
        row.status = "active"
        row.access_token_saved_at = now
        row.validated_at = now
        row.expires_at = expires_at
        row.last_error = None
        db.add(row)
    else:
        db.add(
            FyersToken(
                id=1,
                access_token=encrypted,
                created_at=now,
                is_active=True,
                status="active",
                access_token_saved_at=now,
                validated_at=now,
                expires_at=expires_at,
            )
        )
    history = FyersTokenHistory(
        access_token_masked=_mask_token(access_token),
        saved_at=now,
        status="active",
        note="Saved via Capital / broker token API",
    )
    db.add(history)
    _set_token_cache(access_token, now)
    try:
        from ..core.response_cache import cache_invalidate
        cache_invalidate("token_status")
    except Exception:
        pass


async def save_token(
    db: AsyncSession,
    user_id: UUID,
    *,
    broker: str,
    access_token: str,
    api_key: str | None = None,
    api_secret: str | None = None,
    token_expiry: datetime | None = None,
    notes: str | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    broker = (broker or "FYERS").upper().strip()
    if broker not in SUPPORTED_BROKERS:
        logger.warning("BROKER_TOKEN_SAVE_UNSUPPORTED | user=%s broker=%s", str(user_id)[:8], broker)
        return {"status": "error", "message": f"Unsupported broker: {broker}"}
    token = (access_token or "").strip()
    if not token:
        logger.warning("BROKER_TOKEN_SAVE_EMPTY | user=%s broker=%s", str(user_id)[:8], broker)
        return {"status": "error", "message": "Access token cannot be empty"}
    if len(token) < 10:
        logger.warning("BROKER_TOKEN_SAVE_TOO_SHORT | user=%s broker=%s len=%d", str(user_id)[:8], broker, len(token))
        return {"status": "error", "message": "Access token is too short"}

    logger.info("BROKER_TOKEN_SAVE_START | user=%s broker=%s token_len=%d validate=%s", str(user_id)[:8], broker, len(token), validate)

    # Prevent obvious duplicates: same masked token already active for user+broker
    # Short fixed mask only (never hundreds of '*'); hard-cap for schema safety
    masked = (mask_secret(token) or "")[:100] or None
    existing = (
        await db.scalars(
            select(BrokerToken).where(
                BrokerToken.user_id == user_id,
                BrokerToken.broker == broker,
                BrokerToken.is_active == True,  # noqa: E712
            )
        )
    ).first()
    if existing and existing.token_masked == masked and existing.encrypted_token:
        logger.info("BROKER_TOKEN_SAVE_DUPLICATE_MASK | user=%s broker=%s masked=%s - allowing re-encrypt", str(user_id)[:8], broker, masked)

    expires_at = token_expiry or _decode_jwt_expiry(token)
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is not None and expires_at < _now():
        logger.warning("BROKER_TOKEN_SAVE_EXPIRED | user=%s broker=%s expiry=%s", str(user_id)[:8], broker, expires_at)
        return {"status": "error", "message": "Token expiry is in the past"}

    last_error = None
    status = "active"
    if validate and broker == "FYERS":
        ok, reason = await _validate_fyers(token)
        if not ok:
            logger.warning("BROKER_TOKEN_SAVE_VALIDATION_FAILED | user=%s broker=%s reason=%s", str(user_id)[:8], broker, reason)
            return {"status": "error", "message": reason or "Token validation failed"}
        logger.info("BROKER_TOKEN_SAVE_VALIDATION_OK | user=%s broker=%s", str(user_id)[:8], broker)
    elif validate and broker != "FYERS":
        pass

    now = _now()
    enc_token = encrypt_secret(token)
    logger.info("BROKER_TOKEN_SAVE_ENCRYPTED | user=%s broker=%s enc_token_len=%d", str(user_id)[:8], broker, len(enc_token) if enc_token else 0)
    enc_key = encrypt_secret(api_key.strip()) if api_key and api_key.strip() else None
    enc_secret = encrypt_secret(api_secret.strip()) if api_secret and api_secret.strip() else None

    row = (
        await db.scalars(
            select(BrokerToken).where(
                BrokerToken.user_id == user_id,
                BrokerToken.broker == broker,
            )
        )
    ).first()

    if row:
        logger.info("BROKER_TOKEN_SAVE_UPDATING | user=%s broker=%s row_id=%d", str(user_id)[:8], broker, row.id)
        row.encrypted_token = enc_token
        if enc_key is not None:
            row.encrypted_api_key = enc_key
        if enc_secret is not None:
            row.encrypted_api_secret = enc_secret
        row.token_expiry = expires_at
        row.notes = notes
        row.status = status
        row.is_active = True
        row.last_validated_at = now
        row.last_error = last_error
        row.token_masked = masked
        row.updated_at = now
    else:
        logger.info("BROKER_TOKEN_SAVE_INSERTING | user=%s broker=%s", str(user_id)[:8], broker)
        row = BrokerToken(
            user_id=user_id,
            broker=broker,
            encrypted_token=enc_token,
            encrypted_api_key=enc_key,
            encrypted_api_secret=enc_secret,
            token_expiry=expires_at,
            notes=notes,
            status=status,
            is_active=True,
            last_validated_at=now,
            last_error=last_error,
            token_masked=masked,
            created_at=now,
            updated_at=now,
        )
        db.add(row)

    if broker == "FYERS":
        await _mirror_to_fyers_tokens(db, token, expires_at)
        logger.info("BROKER_TOKEN_SAVE_MIRRORED | user=%s broker=%s", str(user_id)[:8], broker)

    await db.commit()
    logger.info("BROKER_TOKEN_SAVE_COMMITTED | user=%s broker=%s", str(user_id)[:8], broker)
    await db.refresh(row)
    logger.info(
        "BROKER_TOKEN_SAVED | user=%s broker=%s masked=%s row_id=%d",
        str(user_id)[:8],
        broker,
        masked,
        row.id,
    )
    view = _public_view(row)
    return {
        "status": "ok",
        "message": "Token saved successfully.",
        "token": view,
    }


async def update_token(
    db: AsyncSession,
    user_id: UUID,
    *,
    broker: str = "FYERS",
    access_token: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    token_expiry: datetime | None = None,
    notes: str | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    broker = (broker or "FYERS").upper()
    row = (
        await db.scalars(
            select(BrokerToken).where(
                BrokerToken.user_id == user_id,
                BrokerToken.broker == broker,
            )
        )
    ).first()
    if not row:
        if not access_token:
            return {"status": "error", "message": "No token found to update"}
        return await save_token(
            db,
            user_id,
            broker=broker,
            access_token=access_token,
            api_key=api_key,
            api_secret=api_secret,
            token_expiry=token_expiry,
            notes=notes,
            validate=validate,
        )

    token_plain = access_token.strip() if access_token else decrypt_secret(row.encrypted_token)
    if not token_plain:
        return {"status": "error", "message": "Access token cannot be empty"}

    return await save_token(
        db,
        user_id,
        broker=broker,
        access_token=token_plain,
        api_key=api_key if api_key is not None else (
            decrypt_secret(row.encrypted_api_key) if row.encrypted_api_key else None
        ),
        api_secret=api_secret if api_secret is not None else (
            decrypt_secret(row.encrypted_api_secret) if row.encrypted_api_secret else None
        ),
        token_expiry=token_expiry if token_expiry is not None else row.token_expiry,
        notes=notes if notes is not None else row.notes,
        validate=validate and bool(access_token),
    )


async def delete_token(db: AsyncSession, user_id: UUID, broker: str = "FYERS") -> dict[str, Any]:
    broker = (broker or "FYERS").upper()
    row = (
        await db.scalars(
            select(BrokerToken).where(
                BrokerToken.user_id == user_id,
                BrokerToken.broker == broker,
            )
        )
    ).first()
    if not row:
        return {"status": "ok", "message": "No token to delete", "deleted": False}

    await db.delete(row)
    if broker == "FYERS":
        await db.execute(
            update(FyersToken)
            .where(FyersToken.is_active == True)  # noqa: E712
            .values(is_active=False, status="inactive")
        )
        _clear_token_cache()
        try:
            from ..core.response_cache import cache_invalidate
            cache_invalidate("token_status")
        except Exception:
            pass
    await db.commit()
    logger.info("BROKER_TOKEN_DELETED | user=%s broker=%s", str(user_id)[:8], broker)
    return {"status": "ok", "message": "Token deleted", "deleted": True}


async def validate_token(db: AsyncSession, user_id: UUID, broker: str = "FYERS") -> dict[str, Any]:
    broker = (broker or "FYERS").upper()
    row = (
        await db.scalars(
            select(BrokerToken).where(
                BrokerToken.user_id == user_id,
                BrokerToken.broker == broker,
                BrokerToken.is_active == True,  # noqa: E712
            )
        )
    ).first()
    if not row:
        return {"status": "error", "message": "No active token", "connection_status": "Disconnected"}

    try:
        plain = decrypt_secret(row.encrypted_token)
    except Exception:
        row.status = "invalid"
        row.last_error = "Decrypt failed"
        await db.commit()
        return {"status": "error", "message": "Stored token could not be decrypted", "connection_status": "Invalid Token"}

    if broker == "FYERS":
        ok, reason = await _validate_fyers(plain or "")
    else:
        ok, reason = (bool(plain and len(plain) >= 10), "OK" if plain else "Empty token")

    now = _now()
    if ok:
        row.status = "active"
        row.last_validated_at = now
        row.last_error = None
        row.token_expiry = row.token_expiry or _decode_jwt_expiry(plain or "")
        await db.commit()
        return {
            "status": "ok",
            "message": "Connected Successfully",
            "connection_status": _connection_status(row),
            "token": _public_view(row),
        }

    row.status = "invalid"
    row.last_error = reason
    await db.commit()
    return {
        "status": "error",
        "message": reason or "Invalid Token",
        "connection_status": "Invalid Token",
        "token": _public_view(row),
    }


async def get_decrypted_access_token(db: AsyncSession, user_id: UUID, broker: str = "FYERS") -> str | None:
    """Internal only — never expose via HTTP."""
    row = (
        await db.scalars(
            select(BrokerToken).where(
                BrokerToken.user_id == user_id,
                BrokerToken.broker == (broker or "FYERS").upper(),
                BrokerToken.is_active == True,  # noqa: E712
            )
        )
    ).first()
    if not row:
        return None
    return decrypt_secret(row.encrypted_token)
