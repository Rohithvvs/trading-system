"""Alembic environment.

Uses a *synchronous* SQLAlchemy engine for online migrations. Async/asyncpg is
intentionally avoided here: Neon/PgBouncer poolers frequently raise
InvalidCachedStatementError after DDL on alembic_version, which breaks
`alembic current` / `upgrade` even when statement_cache_size=0 is set via
SQLAlchemy's async dialect. Sync psycopg2 is the stable path for migration
commands while the app continues to use asyncpg at runtime.

Also hardens production deploys that still run bare::

    alembic -c backend/alembic.ini upgrade head

by (1) forcing absolute script/version paths, (2) widening version_num, and
(3) remapping / recovering ghost stamps before Alembic reads alembic_version.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import engine_from_config, pool, text

from alembic import context
from alembic.script import ScriptDirectory

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# backend/alembic/env.py → backend/
_ALEMBIC_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_ALEMBIC_DIR)
_VERSIONS_DIR = os.path.join(_ALEMBIC_DIR, "versions")
sys.path.insert(0, _BACKEND_DIR)

# Always resolve scripts relative to this file — never cwd. Prevents Render
# from loading an empty/wrong versions tree when cwd or %(here)s is ambiguous.
config.set_main_option("script_location", _ALEMBIC_DIR)
config.set_main_option("version_locations", _VERSIONS_DIR)

from app.db.base import Base
from app.config import settings

# Import models to ensure they are registered with Base.metadata
from app.models import analysis  # noqa: F401
from app.models import paper_trading  # noqa: F401
from app.models import stock  # noqa: F401
from app.models import fyers_token  # noqa: F401
from app.models import workstation  # noqa: F401
from app.models import market_data  # noqa: F401
from app.models import system_log  # noqa: F401
from app.models import infrastructure  # noqa: F401
from app.models import research  # noqa: F401
from app.models import auth  # noqa: F401  # users / sessions / audit_logs
from app.models import feature_permission  # noqa: F401  # Sprint 3 feature_permissions

# Historical revision renames (old id in DB -> current id in this tree)
REVISION_ALIASES: dict[str, str] = {
    "20260728_001_rbac_role_normalization": "20260728_001_rbac_role_norm",
}


def _sync_database_url(raw_database_url: str) -> str:
    """Convert app DATABASE_URL to a sync SQLAlchemy URL for Alembic.

    - postgresql+asyncpg → postgresql+psycopg2 (or plain postgresql)
    - strip channel_binding (not accepted by psycopg2)
    - preserve sslmode for Neon
    """
    parsed = urlsplit(raw_database_url)
    scheme = parsed.scheme

    if scheme == "sqlite" or scheme.startswith("sqlite+"):
        # Offline/local sqlite — keep as-is (sync)
        return raw_database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)

    if scheme in {"postgresql+asyncpg", "postgres", "postgresql"}:
        scheme = "postgresql+psycopg2"
    elif scheme == "postgresql+psycopg2":
        pass
    # else leave custom schemes alone

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    filtered: list[tuple[str, str]] = []
    for key, value in query_pairs:
        if key == "channel_binding":
            continue
        filtered.append((key, value))

    return urlunsplit(
        (
            scheme,
            parsed.netloc,
            parsed.path,
            urlencode(filtered, doseq=True),
            parsed.fragment,
        )
    )


database_url = _sync_database_url(settings.database_url)
# configparser interpolates '%' — escape for set_main_option
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def _ensure_alembic_version_width(connection, *, label: str = "pre") -> None:
    """Widen alembic_version.version_num before/after revision stamps.

    Default Alembic column is VARCHAR(32). Historical revision IDs in this
    project exceed that (e.g. ``20260728_001_rbac_role_normalization`` = 36
    chars). Alembic updates version_num *after* each upgrade() step; if the
    column is still VARCHAR(32), deploy fails with::

        StringDataRightTruncationError: value too long for type character varying(32)

    Idempotent. Safe when the table does not exist yet (empty DB).
    """
    try:
        dialect = connection.dialect.name
    except Exception:
        return
    if dialect != "postgresql":
        return
    sql = text(
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
                RAISE NOTICE 'alembic_version.version_num widened to VARCHAR(128)';
            END IF;
        END $$;
        """
    )
    try:
        connection.execute(sql)
        connection.commit()
        print(f"alembic env: version_num width check ok ({label})")
    except Exception as exc:
        # Table may not exist yet (empty DB) — baseline migration creates it.
        try:
            connection.rollback()
        except Exception:
            pass
        print(f"alembic env: version_num width check skipped ({label}): {exc!r}")


def _read_stamps(connection) -> list[str]:
    try:
        exists = connection.execute(
            text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
        ).scalar()
    except Exception:
        return []
    if not exists:
        return []
    rows = connection.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    return [str(r[0]).strip() for r in rows if r[0] is not None]


def _write_stamps(connection, stamps: list[str]) -> None:
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(128) NOT NULL"
            ")"
        )
    )
    connection.execute(text("DELETE FROM alembic_version"))
    for stamp in stamps:
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
            {"v": stamp},
        )
    connection.commit()


def _repair_alembic_stamps(connection) -> None:
    """Remap renamed revisions and recover ghost stamps before upgrade.

    Prevents bare ``alembic upgrade head`` from dying with::

        Can't locate revision identified by '20260723_widen_reason_codes'

    when the DB stamp is unknown to the *deployed* script tree (branch skew,
    wrong versions path, or a revision file missing from that deploy).
    """
    script = ScriptDirectory.from_config(config)
    known = {rev.revision for rev in script.walk_revisions()}
    version_files = sorted(
        f for f in os.listdir(_VERSIONS_DIR) if f.endswith(".py") and not f.startswith("__")
    )
    print("alembic env: script_location =", _ALEMBIC_DIR)
    print("alembic env: version_locations =", _VERSIONS_DIR)
    print("alembic env: version files =", len(version_files))
    print("alembic env: loaded revisions =", len(known))
    print("alembic env: heads =", list(script.get_heads()))
    print(
        "alembic env: has 20260723_widen_reason_codes =",
        "20260723_widen_reason_codes" in known,
    )
    if "20260723_widen_reason_codes_text.py" in version_files:
        print("alembic env: file present: 20260723_widen_reason_codes_text.py")
    else:
        print("alembic env: MISSING FILE: 20260723_widen_reason_codes_text.py")
        print("alembic env: files sample =", version_files[:15])

    stamps = _read_stamps(connection)
    print("alembic env: db stamps =", stamps)
    if not stamps:
        return

    remapped: list[str] = []
    changed = False
    for stamp in stamps:
        if stamp in REVISION_ALIASES:
            target = REVISION_ALIASES[stamp]
            print(f"alembic env: REMAP stamp {stamp!r} -> {target!r}")
            remapped.append(target)
            changed = True
        else:
            remapped.append(stamp)

    unknown = [s for s in remapped if s not in known]
    if unknown:
        heads = list(script.get_heads())
        if len(heads) != 1:
            raise RuntimeError(
                f"alembic env: unknown stamp(s) {unknown} and cannot auto-recover "
                f"(expected 1 head, got {heads}). Check that backend/alembic/versions "
                f"is deployed and version_locations resolves correctly."
            )
        head = heads[0]
        print(
            f"alembic env: RECOVERY stamping DB to head {head!r} because "
            f"deployed scripts do not contain {unknown!r}. "
            "Unblocks boot when alembic_version is a ghost/orphan stamp."
        )
        _write_stamps(connection, [head])
        return

    if changed:
        _write_stamps(connection, remapped)
        print("alembic env: stamps after remap =", _read_stamps(connection))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a sync engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Separate connection + commit so widen/repair are durable before Alembic
    # begins its migration transaction and reads/writes version_num.
    with connectable.connect() as bootstrap_conn:
        _ensure_alembic_version_width(bootstrap_conn, label="pre-upgrade")
        _repair_alembic_stamps(bootstrap_conn)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    # If alembic_version was first created mid-upgrade as VARCHAR(32), widen
    # it now so a later deploy with a longer revision id cannot fail on stamp.
    with connectable.connect() as bootstrap_conn:
        _ensure_alembic_version_width(bootstrap_conn, label="post-upgrade")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
