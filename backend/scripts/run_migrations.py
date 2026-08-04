#!/usr/bin/env python3
"""Production-safe Alembic upgrade for Render / Neon.

Why this exists
---------------
Plain ``alembic upgrade head`` fails on Render when:

1. ``alembic_version.version_num`` is still VARCHAR(32) and a revision id is longer
2. ``alembic_version`` points at a revision id that is not present in the *deployed*
   script tree (ghost stamp / branch skew) — classic error::

       Can't locate revision identified by '20260723_widen_reason_codes'

3. Working directory / relative ``script_location`` resolution is ambiguous

This runner always uses absolute paths under ``backend/``, widens
``version_num``, remaps known renamed revisions, and only then runs upgrade.
If the DB stamp is still unknown after remap, stamps to the single head so
the process can boot (schema is expected to already match from prior deploys).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# backend/ on sys.path so `app.*` imports work whether cwd is repo root or backend/
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.chdir(BACKEND_DIR)

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from app.config import settings

ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
SCRIPT_LOCATION = BACKEND_DIR / "alembic"
VERSIONS_DIR = SCRIPT_LOCATION / "versions"

# Historical revision renames (old id -> current id in this tree)
REVISION_ALIASES: dict[str, str] = {
    "20260728_001_rbac_role_normalization": "20260728_001_rbac_role_norm",
}


def _sync_url(raw: str) -> str:
    url = raw.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    # psycopg2 does not accept channel_binding
    if "channel_binding=" in url:
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        p = urlsplit(url)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k != "channel_binding"]
        url = urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), p.fragment))
    return url


def _make_config() -> Config:
    if not ALEMBIC_INI.is_file():
        raise SystemExit(f"alembic.ini not found at {ALEMBIC_INI}")
    if not VERSIONS_DIR.is_dir():
        raise SystemExit(f"versions dir not found at {VERSIONS_DIR}")

    cfg = Config(str(ALEMBIC_INI))
    # Force absolute locations — do not rely on cwd-relative resolution.
    cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
    cfg.set_main_option("version_locations", str(VERSIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", _sync_url(settings.database_url).replace("%", "%%"))
    return cfg


def _engine():
    return create_engine(_sync_url(settings.database_url), pool_pre_ping=True)


def _widen_version_column(eng) -> None:
    """Widen version_num when it is still the Alembic default VARCHAR(32)."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                DECLARE
                    maxlen int;
                BEGIN
                    SELECT character_maximum_length INTO maxlen
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'alembic_version'
                      AND column_name = 'version_num';

                    IF maxlen IS NOT NULL AND maxlen < 128 THEN
                        ALTER TABLE public.alembic_version
                            ALTER COLUMN version_num TYPE VARCHAR(128);
                    END IF;
                END $$;
                """
            )
        )
    print("OK: alembic_version.version_num width check (VARCHAR(128), idempotent)")


def _read_stamps(eng) -> list[str]:
    with eng.connect() as conn:
        exists = conn.execute(
            text(
                "SELECT to_regclass('public.alembic_version') IS NOT NULL"
            )
        ).scalar()
        if not exists:
            return []
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        return [str(r[0]).strip() for r in rows if r[0] is not None]


def _write_stamp(eng, revision: str) -> None:
    with eng.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(128) NOT NULL"
                ")"
            )
        )
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
            {"v": revision},
        )
    print(f"OK: alembic_version stamped to {revision!r}")


def _diag(script: ScriptDirectory, stamps: list[str]) -> set[str]:
    revs = {s.revision for s in script.walk_revisions()}
    files = sorted(p.name for p in VERSIONS_DIR.glob("*.py"))
    print("=== migration diagnostics ===")
    print(f"BACKEND_DIR     = {BACKEND_DIR}")
    print(f"SCRIPT_LOCATION = {SCRIPT_LOCATION}")
    print(f"VERSIONS_DIR    = {VERSIONS_DIR}")
    print(f"version files   = {len(files)}")
    print(f"loaded revisions= {len(revs)}")
    print(f"heads           = {list(script.get_heads())}")
    print(f"db stamps       = {stamps}")
    print(f"has 20260723_widen_reason_codes = {'20260723_widen_reason_codes' in revs}")
    if "20260723_widen_reason_codes_text.py" in files:
        print("file present: 20260723_widen_reason_codes_text.py")
    else:
        print("MISSING FILE: 20260723_widen_reason_codes_text.py")
        print("files:", files)
    return revs


def main() -> None:
    print("run_migrations: starting")
    cfg = _make_config()
    script = ScriptDirectory.from_config(cfg)
    eng = _engine()

    try:
        _widen_version_column(eng)
    except Exception as e:
        print(f"WARN: could not widen alembic_version (may be empty DB): {e!r}")

    stamps = _read_stamps(eng)
    revs = _diag(script, stamps)

    # Remap known renamed revision ids in-place
    remapped = False
    new_stamps: list[str] = []
    for s in stamps:
        if s in REVISION_ALIASES:
            target = REVISION_ALIASES[s]
            print(f"REMAP stamp {s!r} -> {target!r}")
            new_stamps.append(target)
            remapped = True
        else:
            new_stamps.append(s)
    if remapped:
        if len(new_stamps) == 1:
            _write_stamp(eng, new_stamps[0])
        else:
            # Multi-head rare; write first and let upgrade reconcile
            _write_stamp(eng, new_stamps[0])
        stamps = _read_stamps(eng)

    unknown = [s for s in stamps if s not in revs]
    if unknown:
        print(f"ERROR: unknown revision(s) in DB: {unknown}")
        heads = list(script.get_heads())
        if len(heads) != 1:
            raise SystemExit(f"Cannot auto-recover: expected 1 head, got {heads}")
        head = heads[0]
        print(
            f"RECOVERY: stamping DB to head {head!r} because deployed migration "
            f"scripts do not contain {unknown!r}. "
            "This unblocks boot when alembic_version is a ghost/orphan stamp."
        )
        _write_stamp(eng, head)
        stamps = _read_stamps(eng)

    # Final sanity: every stamp must be known before upgrade
    stamps = _read_stamps(eng)
    still_unknown = [s for s in stamps if s not in revs]
    if still_unknown:
        raise SystemExit(f"Still unknown after recovery: {still_unknown}")

    print("Running alembic upgrade head ...")
    command.upgrade(cfg, "head")
    print("OK: alembic upgrade head completed")
    print("final stamps:", _read_stamps(eng))


if __name__ == "__main__":
    main()
