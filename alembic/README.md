# Retired root Alembic tree

**Do not use these scripts for new migrations.**

The canonical Alembic configuration is:

| Item | Path |
|------|------|
| Config | `backend/alembic.ini` |
| Env | `backend/alembic/env.py` |
| Versions | `backend/alembic/versions/` |

Repo-root `alembic.ini` now points `script_location` at `backend/alembic` so
`alembic upgrade head` from the repository root resolves the same revision
graph (including `20260723_widen_reason_codes` and later heads).

The files under `alembic/versions/` here are **historical only** (early
execution-safety / scan-snapshot experiments) and are no longer part of the
active migration DAG.
