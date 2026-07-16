from __future__ import annotations

import os
import psutil
from datetime import datetime, timezone
from typing import Any


class ResourceTracker:
    def __init__(self) -> None:
        self._pid = os.getpid()
        try:
            self._process = psutil.Process(self._pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self._process = None
        self._last_io = None
        self._last_io_time = datetime.now(timezone.utc)
        if self._process is not None:
            try:
                # hasattr is not enough — some platforms expose the method but raise
                self._last_io = self._process.io_counters()
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, NotImplementedError):
                self._last_io = None

    def get_system_cpu_percent(self, interval: float = 0.0) -> float:
        """Non-blocking by default (interval=0) to avoid scheduler stalls."""
        try:
            return float(psutil.cpu_percent(interval=interval))
        except Exception:
            return 0.0

    def get_system_memory_percent(self) -> float:
        try:
            return float(psutil.virtual_memory().percent)
        except Exception:
            return 0.0

    def get_system_memory_used_mb(self) -> float:
        try:
            return float(psutil.virtual_memory().used / (1024 * 1024))
        except Exception:
            return 0.0

    def get_process_cpu_percent(self, interval: float = 0.0) -> float:
        if self._process is None:
            return 0.0
        try:
            return float(self._process.cpu_percent(interval=interval))
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            return 0.0

    def get_process_memory_percent(self) -> float:
        if self._process is None:
            return 0.0
        try:
            return float(self._process.memory_percent())
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            return 0.0

    def get_process_memory_used_mb(self) -> float:
        if self._process is None:
            return 0.0
        try:
            return float(self._process.memory_info().rss / (1024 * 1024))
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            return 0.0

    def get_io_counters(self) -> dict[str, float]:
        result: dict[str, float] = {
            "read_bytes_per_sec": 0.0,
            "write_bytes_per_sec": 0.0,
        }
        if self._process is None:
            return result
        try:
            current = self._process.io_counters()
            now = datetime.now(timezone.utc)
            if self._last_io is not None:
                elapsed = (now - self._last_io_time).total_seconds()
                if elapsed > 0:
                    result["read_bytes_per_sec"] = (
                        current.read_bytes - self._last_io.read_bytes
                    ) / elapsed
                    result["write_bytes_per_sec"] = (
                        current.write_bytes - self._last_io.write_bytes
                    ) / elapsed
            self._last_io = current
            self._last_io_time = now
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, NotImplementedError):
            pass
        return result

    def get_snapshot(self) -> dict[str, Any]:
        # interval=0 is non-blocking (uses last sample); prime once if needed
        io = self.get_io_counters()
        return {
            "cpu_percent": self.get_system_cpu_percent(interval=0.0),
            "memory_percent": self.get_system_memory_percent(),
            "memory_used_mb": self.get_system_memory_used_mb(),
            "process_cpu_percent": self.get_process_cpu_percent(interval=0.0),
            "process_memory_percent": self.get_process_memory_percent(),
            "process_memory_used_mb": self.get_process_memory_used_mb(),
            "io_read_bytes_per_sec": io["read_bytes_per_sec"],
            "io_write_bytes_per_sec": io["write_bytes_per_sec"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_process_snapshot(self) -> dict[str, Any]:
        io = self.get_io_counters()
        return {
            "cpu_percent": self.get_process_cpu_percent(interval=0.0),
            "memory_percent": self.get_process_memory_percent(),
            "memory_used_mb": self.get_process_memory_used_mb(),
            "io_read_bytes_per_sec": io["read_bytes_per_sec"],
            "io_write_bytes_per_sec": io["write_bytes_per_sec"],
        }
