"""Guardrails for Alembic revision identifiers.

Postgres alembic_version.version_num defaults to VARCHAR(32). Stamping a longer
id fails deploy with StringDataRightTruncationError (seen on Render for
``20260728_001_rbac_role_normalization``).
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
# Keep under historical Alembic default column width (VARCHAR(32)).
MAX_REVISION_ID_LEN = 32


def _script() -> ScriptDirectory:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_all_revision_ids_fit_alembic_version_default_width() -> None:
    script = _script()
    too_long = [
        (rev.revision, len(rev.revision))
        for rev in script.walk_revisions()
        if len(rev.revision) > MAX_REVISION_ID_LEN
    ]
    assert too_long == [], (
        f"Revision id(s) longer than {MAX_REVISION_ID_LEN} chars will fail "
        f"on VARCHAR(32) alembic_version: {too_long}"
    )


def test_single_head() -> None:
    heads = list(_script().get_heads())
    assert len(heads) == 1, f"Expected single migration head, got {heads}"


def test_renamed_rbac_revision_is_short() -> None:
    """Historical long id must not be the live revision identifier."""
    revs = {r.revision for r in _script().walk_revisions()}
    assert "20260728_001_rbac_role_normalization" not in revs
    assert "20260728_001_rbac_role_norm" in revs
    assert len("20260728_001_rbac_role_norm") <= MAX_REVISION_ID_LEN
