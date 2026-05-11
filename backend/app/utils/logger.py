from __future__ import annotations

import logging
import os
from pathlib import Path
from datetime import datetime


# Allow tests to override where logs are written by setting TEST_ARTIFACT_DIR.
_env = os.environ.get("TEST_ARTIFACT_DIR")
if _env:
    LOG_DIR = Path(_env) / "logs"
else:
    LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

RUN_ID = os.environ.get("RUN_ID") or datetime.utcnow().strftime("%Y%m%dT%H%M%S")
LOG_FILE = LOG_DIR / f"trading_system-{RUN_ID}.log"


def configure_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    root_logger.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger.addHandler(stream_handler)

    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    except OSError as exc:
        root_logger.warning("File logging disabled | path=%s | error=%s", LOG_FILE, exc)
        return

    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
