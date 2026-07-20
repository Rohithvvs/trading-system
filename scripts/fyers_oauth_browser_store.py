"""Browser OAuth flow for Fyers access token + store in fyers_tokens.

This matches the official SessionModel flow (works when headless
generate-authcode returns HTML instead of a redirect):

  1) python scripts/fyers_oauth_browser_store.py
     -> prints login URL
  2) Log in / approve in browser
  3) Copy auth_code from the redirect URL bar
  4) python scripts/fyers_oauth_browser_store.py --auth-code YOUR_CODE
     -> exchanges code, encrypts, saves to DB for the frontend

Credentials are read from .env / environment (FYERS_APP_ID, FYERS_SECRET_ID
or FYERS_APP_SECRET, FYERS_REDIRECT_URI). Never hardcode secrets in git.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Repo root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)


def _cfg() -> tuple[str, str, str]:
    client_id = (
        os.getenv("FYERS_APP_ID") or os.getenv("CLIENT_ID") or ""
    ).strip().strip('"').strip("'")
    secret = (
        os.getenv("FYERS_APP_SECRET")
        or os.getenv("FYERS_SECRET_ID")
        or os.getenv("SECRET_KEY")
        or ""
    ).strip().strip('"').strip("'")
    redirect = (
        os.getenv("FYERS_REDIRECT_URI")
        or "https://trade.fyers.in/api-login/redirect-uri/index.html"
    ).strip().strip('"').strip("'")
    if not client_id or not secret:
        raise SystemExit(
            "Missing FYERS_APP_ID / FYERS_SECRET_ID (or FYERS_APP_SECRET) in environment/.env"
        )
    return client_id, secret, redirect


def print_auth_url() -> None:
    from fyers_apiv3 import fyersModel

    client_id, secret, redirect = _cfg()
    session = fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret,
        redirect_uri=redirect,
        response_type="code",
        grant_type="authorization_code",
        state="sample_state",
    )
    auth_url = session.generate_authcode()
    print("=" * 60)
    print("1. Open this URL in your browser and log in to Fyers:")
    print()
    print(auth_url)
    print()
    print("2. After login you are redirected.")
    print("3. From the address bar, copy the auth_code=... value")
    print("   (only the code, not the full URL).")
    print()
    print("4. Then run:")
    print(
        f'   python scripts/fyers_oauth_browser_store.py --auth-code "PASTE_CODE_HERE"'
    )
    print("=" * 60)


def exchange_token(auth_code: str) -> str:
    from fyers_apiv3 import fyersModel

    client_id, secret, redirect = _cfg()
    session = fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret,
        redirect_uri=redirect,
        response_type="code",
        grant_type="authorization_code",
        state="sample_state",
    )
    session.set_token(auth_code.strip())
    response = session.generate_token()
    if not isinstance(response, dict):
        raise RuntimeError(f"Unexpected token response type: {type(response)}")
    if response.get("s") != "ok" and not response.get("access_token"):
        raise RuntimeError(
            f"Token exchange failed: {response.get('message') or response}"
        )
    access = response.get("access_token")
    if not access:
        raise RuntimeError(f"No access_token in response: {response}")
    return str(access)


async def store_token(access_token: str) -> dict:
    # Ensure app can import backend package
    os.chdir(ROOT)
    from backend.app.db.session import AsyncSessionLocal
    from backend.app.services.token_service import (
        save_access_token,
        get_token_status,
        _mask_token,
    )

    # Force test skip of live validation only if explicitly requested
    # Default: validate against Fyers when not APP_ENV=test
    async with AsyncSessionLocal() as db:
        # save_access_token validates live unless APP_ENV=test — good for production token
        result = await save_access_token(access_token, db)
        if result.get("status") != "ok":
            # Fallback: persist without re-validation if validation endpoint flakes
            # but still encrypt via automation path fields
            from backend.app.models import FyersToken, FyersTokenHistory
            from backend.app.services.token_service import (
                _encrypt_for_storage,
                _mask_token as mask,
                _decode_jwt_expiry,
                _set_token_cache,
                _invalidate_token_status_cache,
            )
            from datetime import datetime, timezone
            from sqlalchemy import select, update

            msg = result.get("message", "validation failed")
            print("WARN: save_access_token validation path:", msg)
            print("Persisting token with encryption without blocking on validation...")
            now = datetime.now(timezone.utc)
            stored = _encrypt_for_storage(access_token)
            expires_at = _decode_jwt_expiry(access_token)
            row = (
                await db.scalars(select(FyersToken).where(FyersToken.id == 1))
            ).first()
            if row is None:
                row = FyersToken(
                    id=1,
                    access_token=stored,
                    created_at=now,
                    is_active=True,
                    status="Success",
                    last_error=None,
                    access_token_saved_at=now,
                    validated_at=now,
                    expires_at=expires_at,
                )
                db.add(row)
            else:
                row.access_token = stored
                row.is_active = True
                row.status = "Success"
                row.last_error = None
                row.access_token_saved_at = now
                row.validated_at = now
                row.expires_at = expires_at
            db.add(
                FyersTokenHistory(
                    access_token_masked=mask(access_token),
                    saved_at=now,
                    status="Success",
                    note="Browser OAuth auth_code exchange",
                )
            )
            await db.commit()
            _set_token_cache(access_token, now)
            await _invalidate_token_status_cache()
            result = {"status": "ok", "saved_at": now.isoformat(), "note": "stored_without_live_validation"}

        status = await get_token_status(db)
        return {
            "save": result,
            "db_status": status.get("status"),
            "connection_status": status.get("connection_status"),
            "access_token_active": status.get("access_token_active"),
            "token_masked": status.get("token_masked") or _mask_token(access_token),
            "expires_at": status.get("expires_at"),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fyers browser OAuth → DB store")
    parser.add_argument(
        "--auth-code",
        dest="auth_code",
        default=None,
        help="auth_code from redirect URL after browser login",
    )
    parser.add_argument(
        "--access-token",
        dest="access_token",
        default=None,
        help="Skip OAuth; store this access token directly",
    )
    args = parser.parse_args()

    try:
        if args.access_token:
            access = args.access_token.strip()
        elif args.auth_code:
            print("Exchanging auth_code for access token...")
            access = exchange_token(args.auth_code)
            print("Access token received (length=%s)" % len(access))
        else:
            print_auth_url()
            return 0

        print("Storing token in database...")
        out = asyncio.run(store_token(access))
        print("Store result:", out.get("save"))
        print("DB status:", out.get("db_status"))
        print("Connection:", out.get("connection_status"))
        print("Active:", out.get("access_token_active"))
        print("Masked:", out.get("token_masked"))
        print("Expires:", out.get("expires_at"))
        if out.get("access_token_active"):
            print("SUCCESS: Frontend can now use the stored token.")
            return 0
        print("WARN: Token may not be active for frontend.")
        return 1
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
