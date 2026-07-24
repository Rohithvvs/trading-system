"""Probe DATABASE_URL candidates with the same asyncpg SSL handling as the app."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def load_urls() -> list[str]:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    urls: list[str] = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "DATABASE_URL=" not in line or "postgres" not in line.lower():
            continue
        raw = line.lstrip("#").strip()
        if not raw.startswith("DATABASE_URL="):
            continue
        urls.append(raw.split("=", 1)[1].strip().strip("\"'"))
    return urls


def prepare(url: str) -> tuple[str, dict]:
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    parsed = urlsplit(url)
    pairs: list[tuple[str, str]] = []
    ssl = False
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key == "sslmode":
            if value.lower() != "disable":
                ssl = True
            continue
        if key == "channel_binding":
            continue
        pairs.append((key, value))
    cleaned = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), parsed.fragment)
    )
    args: dict = {"statement_cache_size": 0}
    if ssl:
        args["ssl"] = True
    return cleaned, args


async def main() -> None:
    urls = load_urls()
    print(f"candidates={len(urls)}")
    for url in urls:
        host_m = re.search(r"@([^/]+)/", url)
        host = host_m.group(1) if host_m else "unknown"
        u, args = prepare(url)
        eng = create_async_engine(u, connect_args=args, pool_pre_ping=True)
        try:
            async with eng.connect() as c:
                await c.scalar(text("select 1"))
            print("OK", host)
        except Exception as e:  # noqa: BLE001
            print("FAIL", host, type(e).__name__, str(e)[:180])
        finally:
            await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
