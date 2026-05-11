import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


# Prefer a test-controlled artifacts directory when running tests. Tests set
# the `TEST_ARTIFACT_DIR` env var (conftest.py) so logs are written under
# `tests/artifacts/...` for each run. Otherwise fall back to backend/logs.
ENV_ARTIFACT_DIR = os.environ.get("TEST_ARTIFACT_DIR")
DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
if ENV_ARTIFACT_DIR:
    LOG_DIR = Path(ENV_ARTIFACT_DIR) / "logs"
else:
    LOG_DIR = DEFAULT_LOG_DIR
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Per-run identifier used to create timestamped log filenames. Tests may set
# `RUN_ID` to keep artifacts predictable; otherwise use UTC timestamp.
RUN_ID = os.environ.get("RUN_ID") or datetime.utcnow().strftime("%Y%m%dT%H%M%S")


def _file_for(filename: str, keep_latest_scan: bool = False) -> Path:
    base = Path(filename).stem
    if keep_latest_scan:
        return LOG_DIR / f"{base}.log"
    return LOG_DIR / f"{base}-{RUN_ID}.log"


def _create_rotating_logger(name: str, filename: str, level: int = logging.INFO, max_bytes: int = 5 * 1024 * 1024, backup_count: int = 3) -> logging.Logger:
    path = _file_for(filename)
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Clear existing handlers to avoid duplicate writes when reloading
    logger.handlers.clear()

    handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    handler.setLevel(level)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _create_overwrite_logger(name: str, filename: str, level: int = logging.INFO) -> logging.Logger:
    path = _file_for(filename, keep_latest_scan=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Clear existing handlers to avoid duplicate writes when reloading
    logger.handlers.clear()

    handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    handler.setLevel(level)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


# Public loggers used across the app
# The scan log is overwritten each run to keep the latest scan easily inspectable.
scanner_logger = _create_overwrite_logger("app.scanner", "latest_scan.log")
fyers_logger = _create_rotating_logger("app.fyers_api", "fyers_api.log")
trading_logger = _create_rotating_logger("app.paper_trading", "paper_trading.log")
# HTTP / API request/response logger (separate file per run)
http_logger = _create_rotating_logger("app.http", "api.log")
# Error-only logger (separate file per run)
error_logger = _create_rotating_logger("app.errors", "errors.log", level=logging.ERROR)
