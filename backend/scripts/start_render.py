#!/usr/bin/env python3
"""Render / production process entrypoint.

Always:
  1. Run production-safe migrations (widen version_num, remap ghost stamps)
  2. Start uvicorn

Use this as the Render **Start Command** so a dashboard override cannot
fall back to bare ``alembic upgrade head`` (which historically failed with
StringDataRightTruncationError on long revision ids).

Render dashboard Start Command (recommended)::

    python backend/scripts/start_render.py

Equivalent explicit form (also fine)::

    python backend/scripts/run_migrations.py && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
RUN_MIGRATIONS = SCRIPT_DIR / "run_migrations.py"


def main() -> int:
    os.chdir(REPO_ROOT)

    if not RUN_MIGRATIONS.is_file():
        print(f"ERROR: migration runner missing: {RUN_MIGRATIONS}", file=sys.stderr)
        return 1

    print("start_render: running migrations ...")
    mig = subprocess.run(
        [sys.executable, str(RUN_MIGRATIONS)],
        cwd=str(REPO_ROOT),
        check=False,
    )
    if mig.returncode != 0:
        print(
            f"start_render: migrations failed with exit {mig.returncode}",
            file=sys.stderr,
        )
        return mig.returncode

    port = os.environ.get("PORT", "8000")
    print(f"start_render: starting uvicorn on 0.0.0.0:{port} ...")
    # Replace this process so signals (SIGTERM from Render) reach uvicorn.
    os.execvp(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
    )
    return 0  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
