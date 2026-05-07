import logging
import logging.handlers
import os
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

TOKEN_LOG_FILE = LOG_DIR / "token_operations.log"
APP_LOG_FILE   = LOG_DIR / "app.log"
ERROR_LOG_FILE = LOG_DIR / "errors.log"

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
