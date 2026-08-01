"""CLI runner for Sprint 4 automated Fyers token generation + DB persistence.

Uses application settings / AsyncSessionLocal (no hardcoded credentials or DB URLs).
Exit codes: 0 success, 1 failure (after Failed status is recorded when possible).

===========================================================================
BREAKING CHANGE vs pre-Sprint-4 script
===========================================================================
The previous root ``update_token.py`` wrote a hardcoded JWT into a local
SQLite ``fyers_auth`` table. That path is **retired** and is not supported.

Correct usage (dev and prod)::

    # Ensure DATABASE_URL + FYERS_* env vars are set (via .env / host secrets)
    python update_token.py

Optional timeouts (env)::

    FYERS_TOKEN_JOB_TIMEOUT_SEC=180
    FYERS_TOKEN_DB_WRITE_TIMEOUT_SEC=30

Hardening:
  - Session context always closed before process exit code is applied.
  - Stderr carries exception class + message only (no token material).
"""

from __future__ import annotations

import asyncio
import sys

from backend.app.db.session import AsyncSessionLocal
from backend.app.services.token_service import generate_and_persist_fyers_token


async def main() -> int:
    """Run one generation+persist job. Returns process exit code (0/1)."""
    try:
        async with AsyncSessionLocal() as db:
            result = await generate_and_persist_fyers_token(db)
        # Session disposed before stdout (resource cleanup guaranteed).
        preview = result.get("token_preview") or "unknown"
        # Never print full token; preview is already masked by the service.
        print("Token updated successfully. Masked token:", preview)
        return 0
    except Exception as e:
        # Keep operator-facing stderr short; full detail is in app.token logs.
        sys.stderr.write(f"Error: {e.__class__.__name__} - {str(e)}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
