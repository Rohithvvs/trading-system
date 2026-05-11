import logging
import logging.handlers
import os
from pathlib import Path
from datetime import datetime

# Use TEST_ARTIFACT_DIR (set by tests) when present so test runs write logs
# into the per-run artifacts folder. Otherwise fall back to backend/logs.
_env_artifacts = os.environ.get("TEST_ARTIFACT_DIR")
_default_logs = Path(__file__).resolve().parent.parent.parent / "logs"
if _env_artifacts:
    LOG_DIR = Path(_env_artifacts) / "logs"
else:
    LOG_DIR = _default_logs
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Run id (timestamp) appended to per-run log files. Tests may set RUN_ID.
RUN_ID = os.environ.get("RUN_ID") or datetime.utcnow().strftime("%Y%m%dT%H%M%S")

def _named(fname: str) -> Path:
    base = Path(fname).stem
    return LOG_DIR / f"{base}-{RUN_ID}.log"


TOKEN_LOG_FILE = _named("token_operations.log")
APP_LOG_FILE = _named("app.log")
ERROR_LOG_FILE = _named("errors.log")

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # ── Console handler ──────────────────────────────
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(console)

    # ── Main app rotating file ────────────────────────
    app_handler = logging.handlers.RotatingFileHandler(
        APP_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    app_handler.setLevel(logging.DEBUG)
    app_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(app_handler)

    # ── Token-specific rotating file ─────────────────
    token_handler = logging.handlers.RotatingFileHandler(
        TOKEN_LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    token_handler.setLevel(logging.DEBUG)
    token_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    token_logger = logging.getLogger("app.token")
    token_logger.addHandler(token_handler)
    token_logger.propagate = True

    # ── Error-only rotating file ──────────────────────
    error_handler = logging.handlers.RotatingFileHandler(
        ERROR_LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(error_handler)

    return root_logger
