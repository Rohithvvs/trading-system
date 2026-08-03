"""
Recovery script to force-stamp the alembic_version table to the current head.

Run from the backend/ directory (after activating venv) when you see:

  SCHEMA VALIDATION FAILED
  Database Revision: ['20260706_001']
  Expected Revision: ['7b6abc0bf8bc']

This happens when migration files were deleted/renamed on disk but the DB stamp
was left pointing at a now-unknown revision (common in active dev).

USAGE (recommended):
  cd backend
  .\\venv\\Scripts\\Activate.ps1
  python fix_remote_db.py

This uses the official alembic stamp command under the hood.

WARNING: Only for local/dev databases. Verify with `alembic current` / `alembic heads`
afterward. Do not use in production without understanding the schema state.
"""

import sys
import os
from pathlib import Path

# Make 'app' importable and set CWD so relative alembic.ini resolves
HERE = Path(__file__).resolve().parent
os.chdir(HERE)
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from alembic.config import Config
from alembic import command

from app.config.settings import settings  # noqa: F401  (ensures settings are loadable)


def _get_current_head():
    """Dynamically read the head from alembic scripts (avoids stale hardcode)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(HERE / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        print("WARNING: Multiple heads detected in migrations:", heads)
    return heads[0] if heads else "7b6abc0bf8bc"


def main():
    alembic_ini = HERE / "alembic.ini"
    if not alembic_ini.exists():
        print(f"ERROR: alembic.ini not found at {alembic_ini}")
        sys.exit(1)

    cfg = Config(str(alembic_ini))

    target = _get_current_head()
    # alembic reads sqlalchemy.url from the ini, but env.py overrides using settings.
    # We just need to stamp.
    print(f"Stamping database to revision: {target}")
    print("Using alembic config:", alembic_ini)

    try:
        command.stamp(cfg, target)
        print("SUCCESS: Database stamped to", target)
        print("Now restart uvicorn / the backend.")
    except Exception as e:
        print("Stamp via alembic API failed:", repr(e))
        print("Falling back to direct DB update (raw).")
        # Fallback using asyncpg direct
        try:
            import asyncio
            import asyncpg

            async def _direct_stamp():
                url = settings.database_url.replace("+asyncpg", "")
                conn = await asyncpg.connect(url)
                try:
                    await conn.execute(
                        "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(128) NOT NULL)"
                    )
                    await conn.execute("DELETE FROM alembic_version")  # ensure single row
                    await conn.execute(
                        "INSERT INTO alembic_version (version_num) VALUES ($1)", target
                    )
                    cur = await conn.fetchval("SELECT version_num FROM alembic_version")
                    print("Direct stamp success. Current:", cur)
                finally:
                    await conn.close()

            asyncio.run(_direct_stamp())
            print("SUCCESS (fallback). Now restart the server.")
        except Exception as e2:
            print("FALLBACK ALSO FAILED:", repr(e2))
            print("Manual recovery:")
            print(f"  psql ... -c \"UPDATE alembic_version SET version_num = '{target}';\"")
            print("  OR (preferred): alembic stamp head")
            sys.exit(1)


if __name__ == "__main__":
    main()
