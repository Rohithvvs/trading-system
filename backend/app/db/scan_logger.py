import logging
from pathlib import Path

LOG_PATH = Path(__file__).parent / "latest_scan.log"


def get_scan_logger() -> logging.Logger:
    """Returns a logger that always overwrites the latest_scan.log file."""
    logger = logging.getLogger("scan.run")
    logger.setLevel(logging.INFO)

    # Remove old handlers to avoid duplicate writes
    logger.handlers.clear()

    # FileHandler with mode='w' overwrites on every new scan run
    fh = logging.FileHandler(LOG_PATH, mode='w', encoding='utf-8')
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.propagate = False
    return logger
