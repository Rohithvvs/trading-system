from __future__ import annotations

import os
import shutil
import warnings
from pathlib import Path

WARN_THRESHOLD_MB = 100


def _resolve_disk_path(path: str | Path) -> str:
    """Resolve *path* to a valid path for shutil.disk_usage on any OS."""
    p = str(path)
    if not p:
        return os.getcwd()
    if os.path.isfile(p):
        return os.path.dirname(p) or os.getcwd()
    return p


def check_disk_space(path: str | Path, threshold_mb: int = WARN_THRESHOLD_MB) -> bool:
    """Check if the disk containing *path* has at least *threshold_mb* free.
    Returns True if space is sufficient, False otherwise.
    """
    try:
        disk_path = _resolve_disk_path(path)
        usage = shutil.disk_usage(disk_path)
        free_mb = usage.free / (1024 * 1024)
        if free_mb < threshold_mb:
            warnings.warn(
                f"Low disk space: {free_mb:.0f} MB free on {path} "
                f"(threshold: {threshold_mb} MB)",
                ResourceWarning,
                stacklevel=2,
            )
            return False
        return True
    except (OSError, ValueError):
        return True


def ensure_disk_space(
    path: str | Path,
    threshold_mb: int = WARN_THRESHOLD_MB,
) -> None:
    if not check_disk_space(path, threshold_mb):
        raise OSError(
            f"Insufficient disk space on {path}: "
            f"less than {threshold_mb} MB available"
        )