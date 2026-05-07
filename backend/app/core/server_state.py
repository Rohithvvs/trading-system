import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))


STATE_FILE = Path(__file__).resolve().parents[2] / "server_state.json"


def _read_state_file() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def read_last_shutdown() -> datetime | None:
    """Returns the last recorded shutdown time (UTC), or None if missing."""
    try:
        data = _read_state_file()
        ts = data.get("last_shutdown")
        if not ts:
            return None
        dt = datetime.fromisoformat(ts)
        # Normalize to UTC
        if dt.tzinfo is None:
            try:
                dt = dt.replace(tzinfo=IST).astimezone(timezone.utc)
            except Exception:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception as e:
        print(f"[server_state] Failed to read: {e}")
        return None


def write_shutdown_time() -> None:
    """Call this on app shutdown to record the shutdown timestamp (UTC)."""
    try:
        existing = _read_state_file()
        existing["last_shutdown"] = datetime.now(timezone.utc).isoformat()
        with STATE_FILE.open("w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2)
        print(f"[server_state] Shutdown time recorded: {existing['last_shutdown']}")
    except Exception as e:
        print(f"[server_state] Failed to write shutdown time: {e}")


def write_startup_time() -> None:
    """Call this on app startup after gap replay is done."""
    try:
        existing = _read_state_file()
        existing["last_startup"] = datetime.now(timezone.utc).isoformat()
        with STATE_FILE.open("w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2)
    except Exception as e:
        print(f"[server_state] Failed to write startup time: {e}")
