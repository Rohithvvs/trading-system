import logging
import logging.handlers
from pathlib import Path

LOG_PATH = Path(__file__).parent / "latest_scan.log"


def get_scan_logger() -> logging.Logger:
    """Returns a logger that always overwrites the latest_scan.log file."""
    logger = logging.getLogger("scan.run")
    logger.setLevel(logging.INFO)

    # Remove old handlers to avoid duplicate writes
    logger.handlers.clear()

    # FileHandler replaced with RotatingFileHandler to bound physical disk footprint
    fh = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=20 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.propagate = False
    return logger
