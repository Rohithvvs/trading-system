"""Compatibility wrapper so `uvicorn main:app` works when run from the `backend/` folder.

This imports the FastAPI `app` created in `backend/app/main.py` (module `backend.app.main`).
"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path so subprocesses spawned by the reloader
# can import the top-level `backend` package even when cwd is `backend/`.
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
	# Preferred import when running from the repository root:
	from backend.app.main import app
except Exception:
	# Backwards-compatible fallback when running `uvicorn main:app` from inside `backend/`:
	from app.main import app
