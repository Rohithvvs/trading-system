import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


# Create backend/logs directory (sibling of app)
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _create_rotating_logger(name: str, filename: str, level: int = logging.INFO, max_bytes: int = 5 * 1024 * 1024, backup_count: int = 3) -> logging.Logger:
    path = LOG_DIR / filename
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
    path = LOG_DIR / filename
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
