"""Probe DATABASE_URL candidates from repo .env (does not print secrets)."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def load_urls() -> list[str]:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    urls: list[str] = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if "DATABASE_URL" not in s:
            continue
        raw = s.lstrip("#").strip()
        if not raw.startswith("DATABASE_URL="):
            continue
        urls.append(raw.split("=", 1)[1].strip().strip("\"'"))
    return urls


async def probe(url: str) -> tuple[bool, str, str | None]:
    u = url
    if u.startswith("postgresql://"):
        u = u.replace("postgresql://", "postgresql+asyncpg://", 1)
    host_m = re.search(r"@([^/]+)/", url)
    host = host_m.group(1) if host_m else "unknown"
    eng = create_async_engine(u, pool_pre_ping=True)
    try:
        async with eng.connect() as c:
            await c.scalar(text("select 1"))
        return True, host, None
    except Exception as e:  # noqa: BLE001
        return False, host, f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        await eng.dispose()


async def main() -> None:
    urls = load_urls()
    print(f"candidates={len(urls)}")
    for url in urls:
        ok, host, err = await probe(url)
        print(("OK" if ok else "FAIL"), host)
        if err:
            print(" ", err)


if __name__ == "__main__":
    asyncio.run(main())
