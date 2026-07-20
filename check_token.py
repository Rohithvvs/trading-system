"""Local diagnostic: print monitoring fields for fyers_tokens id=1 only.

Hardening: never SELECT access_token (no secret material on stdout).
Dev/ops tool only — not a production service entrypoint.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from backend.app.db.session import AsyncSessionLocal


async def main() -> int:
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                text(
                    "SELECT id, status, last_error, access_token_saved_at, is_active "
                    "FROM fyers_tokens WHERE id = 1"
                )
            )
            rows = res.fetchall()
            print("Row 1 monitoring fields:", rows)
            return 0
    except Exception as e:
        sys.stderr.write(f"Error: {e.__class__.__name__} - {e}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
