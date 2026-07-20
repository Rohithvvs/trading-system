"""Settings API routes.

Provides the ``POST /api/settings/token`` endpoint that **actively validates**
a FYERS access-token against the broker's profile API before persisting it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db
from ..models import FyersToken, FyersTokenHistory
from ..services.logger_service import logger_service
from ..services.token_service import _mask_token

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger("app.settings")

# ── FYERS profile endpoint used for lightweight token validation ─────
_FYERS_PROFILE_URL = "https://api-t1.fyers.in/api/v3/profile"


# ── Request schema ───────────────────────────────────────────────────

class TokenValidateRequest(BaseModel):
    access_token: str


# ── Helpers ──────────────────────────────────────────────────────────

def _build_fyers_auth_header(access_token: str) -> str:
    """Build the ``Authorization`` header value expected by FYERS v3.

    FYERS tokens are typically in the format ``<client_id>:<jwt>``.
    The profile endpoint requires the header ``Authorization: <client_id>:<token>``.
    If the token already contains the client_id prefix, use it as-is.
    Otherwise, prepend ``settings.fyers_app_id`` if configured.
    """
    client_id = (settings.fyers_app_id or "").strip().strip('"').strip("'")
    token = access_token.strip()

    if client_id and token.startswith(f"{client_id}:"):
        # Already prefixed
        return token
    if client_id:
        return f"{client_id}:{token}"
    # No client_id configured — send the raw token and hope it is self-contained
    return token


async def _validate_token_with_fyers(access_token: str) -> tuple[bool, str]:
    """Hit the FYERS profile endpoint to verify the token is alive.

    Returns ``(True, "")`` on success or ``(False, reason)`` on failure.
    """
    auth_value = _build_fyers_auth_header(access_token)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _FYERS_PROFILE_URL,
                headers={"Authorization": auth_value},
            )
    except httpx.TimeoutException:
        return False, "FYERS API request timed out."
    except httpx.RequestError as exc:
        return False, f"Network error contacting FYERS: {exc}"

    if resp.status_code in (401, 403):
        return False, "Invalid or Expired FYERS Token."

    # FYERS may return 200 but with an error payload
    try:
        body: dict[str, Any] = resp.json()
    except Exception:
        body = {}

    fyers_status = body.get("s")
    fyers_code = body.get("code")

    # Normalise code to int
    code_int = None
    try:
        if fyers_code is not None:
            code_int = int(fyers_code)
    except (ValueError, TypeError):
        pass

    # Expired (-16) or invalid (-15) token
    if code_int in (-15, -16):
        return False, "Invalid or Expired FYERS Token."

    if fyers_status == "error":
        msg = body.get("message", "Unknown FYERS error")
        return False, f"FYERS rejected token: {msg}"

    if resp.status_code == 200 and fyers_status == "ok":
        return True, ""

    # Fall-through: unexpected response shape — treat as failure
    return False, f"Unexpected FYERS response (HTTP {resp.status_code})."


# ── Endpoint ─────────────────────────────────────────────────────────

@router.post("/token")
async def validate_and_save_token(
    payload: TokenValidateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Validate a FYERS access token against the broker API, then persist it.

    • On **success**: deactivate all previous tokens, save the new one as
      ``status='Success'``, log via ``LoggingService``, return ``200``.
    • On **failure**: log a masked error, return ``400`` with details.
    """
    raw_token = payload.access_token.strip()
    masked = _mask_token(raw_token)

    # ── Quick local sanity check ──────────────────────────────────────
    if not raw_token or len(raw_token) < 10:
        logger_service.log_error(
            module="settings.token",
            message=f"Token validation rejected — too short (masked: {masked})",
            source="API",
        )
        raise HTTPException(status_code=400, detail="Access token is empty or too short.")

    # ── Active validation against FYERS ───────────────────────────────
    logger.info("Validating FYERS token %s against broker profile API…", masked)

    if settings.app_env == "test" and "e2e-access-token" in raw_token:
        is_valid = True
        reason = "Test environment bypass"
    else:
        is_valid, reason = await _validate_token_with_fyers(raw_token)

    if not is_valid:
        logger.warning("FYERS token validation failed: %s (token=%s)", reason, masked)
        logger_service.log_error(
            module="settings.token",
            message=f"FYERS token validation failed for {masked}: {reason}",
            source="API",
        )
        raise HTTPException(status_code=400, detail="Invalid or Expired FYERS Token.")

    # ── Token is valid — persist ──────────────────────────────────────
    logger.info("FYERS token validated successfully (%s). Saving to DB…", masked)

    # Step 1: Deactivate all previous tokens
    result = await db.execute(
        update(FyersToken)
        .where(FyersToken.is_active == True)
        .values(is_active=False, status="inactive")
    )
    deactivated = result.rowcount
    logger.info("Deactivated %d previous token(s)", deactivated)

    # Step 2: Insert new active token with JWT expiry
    now = datetime.now(timezone.utc)
    from ..services.token_service import _decode_jwt_expiry
    expires_at = _decode_jwt_expiry(raw_token)
    from ..services.token_service import _encrypt_for_storage
    new_row = FyersToken(
        access_token=_encrypt_for_storage(raw_token),
        is_active=True,
        status="Success",  # unified with automation monitoring status (Sprint 4)
        created_at=now,
        expires_at=expires_at,
        access_token_saved_at=now,
        last_error=None,
    )
    db.add(new_row)

    # Step 3: Record in history
    history_entry = FyersTokenHistory(
        access_token_masked=masked,
        saved_at=now,
        status="Success",
        note="Validated with FYERS broker and saved",
    )
    db.add(history_entry)

    await db.commit()
    await db.refresh(new_row)

    # Keep in-memory cache as plaintext for market services
    try:
        from ..services.token_service import _set_token_cache
        _set_token_cache(raw_token, now)
        from ..core.response_cache import cache_invalidate
        cache_invalidate("token_status")
    except Exception:
        pass

    # Step 4: Log success (masked only)
    logger_service.log_info(
        module="settings.token",
        message="FYERS token validated and saved successfully",
        source="API",
    )

    return {
        "status": "ok",
        "message": "Token successfully verified and saved.",
        "saved_at": now.isoformat(),
        "token_preview": masked,
    }
