"""Recursively convert Python objects into JSON-serializable primitives.

Used at the API response layer so domain/ORM types (Decimal, datetime, numpy,
Pydantic models, etc.) never leak into json.dumps / FastAPI JSONResponse.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

logger = logging.getLogger("app.json_sanitize")

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore


def sanitize_for_json(value: Any) -> Any:
    """Recursively convert *value* into JSON-safe primitives."""
    # None / bool / str / int first (bool is subclass of int — handled fine)
    if value is None or isinstance(value, (str, int, bool)):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0

    # Decimal (including subclasses)
    if isinstance(value, Decimal):
        # Preserve NaN/Inf as 0.0 for JSON; otherwise float
        try:
            f = float(value)
        except Exception:
            return 0.0
        return f if math.isfinite(f) else 0.0

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Enum):
        return sanitize_for_json(value.value)

    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}

    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.hex()

    # numpy scalars / arrays
    if np is not None:
        if isinstance(value, np.generic):
            return sanitize_for_json(value.item())
        if isinstance(value, np.ndarray):
            return sanitize_for_json(value.tolist())

    # pandas
    if pd is not None:
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, pd.Timedelta):
            return value.total_seconds()
        if isinstance(value, (pd.Series, pd.Index)):
            return sanitize_for_json(value.tolist())
        if isinstance(value, pd.DataFrame):
            return sanitize_for_json(value.to_dict(orient="records"))
        # pandas NA
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

    # Pydantic v2 / v1
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        try:
            return sanitize_for_json(value.model_dump(mode="python"))
        except TypeError:
            return sanitize_for_json(value.model_dump())
    if hasattr(value, "dict") and callable(getattr(value, "dict")) and not isinstance(value, type):
        # Avoid calling dict() on plain types; only pydantic v1 style models
        try:
            return sanitize_for_json(value.dict())
        except Exception:
            pass

    # dataclasses
    if is_dataclass(value) and not isinstance(value, type):
        return sanitize_for_json(asdict(value))

    # Mapping (dict and dict-like)
    if isinstance(value, Mapping):
        return {str(key): sanitize_for_json(item) for key, item in value.items()}

    # set / frozenset
    if isinstance(value, (set, frozenset)):
        return [sanitize_for_json(item) for item in value]

    # Sequence (list, tuple) but not str/bytes
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_for_json(item) for item in value]

    # SQLAlchemy Row / namedtuple-ish
    if hasattr(value, "_asdict") and callable(getattr(value, "_asdict")):
        try:
            return sanitize_for_json(value._asdict())
        except Exception:
            pass

    # Fallback: leave as-is (may still fail JSON encode — caller should validate)
    return value


def find_non_jsonable(value: Any, path: str = "root") -> list[str]:
    """Return dotted paths of values that json.dumps cannot encode."""
    import json

    problems: list[str] = []

    def _walk(obj: Any, current: str) -> None:
        if obj is None or isinstance(obj, (str, int, bool)):
            return
        if isinstance(obj, float):
            if not math.isfinite(obj):
                problems.append(f"{current} (non-finite float)")
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                _walk(v, f"{current}.{k}" if current else str(k))
            return
        if isinstance(obj, list):
            for i, v in enumerate(obj):
                _walk(v, f"{current}[{i}]")
            return
        # Try encode single leaf
        try:
            json.dumps(obj)
        except TypeError:
            problems.append(f"{current} ({type(obj).__name__}: {obj!r})")

    _walk(value, path)
    return problems


def assert_json_serializable(value: Any, root_name: str = "response") -> Any:
    """Sanitize, validate with json.dumps, log remaining bad types/paths.

    Returns the sanitized value. Raises TypeError if still not serializable.
    """
    import json

    sanitized = sanitize_for_json(value)

    try:
        json.dumps(sanitized)
        return sanitized
    except TypeError as exc:
        paths = find_non_jsonable(sanitized, root_name)
        if paths:
            for p in paths:
                logger.error("JSON_SERIALIZE_UNSUPPORTED | path=%s", p)
        else:
            logger.error(
                "JSON_SERIALIZE_FAILED | root=%s | error=%s | type=%s",
                root_name,
                exc,
                type(sanitized).__name__,
            )
        # Attempt path-level binary search via re-encode of leaves already done
        raise TypeError(
            f"Object not JSON serializable after sanitize_for_json. "
            f"Paths: {paths or [str(exc)]}"
        ) from exc


def collect_decimal_paths(value: Any, path: str = "root") -> list[str]:
    """Debug helper: locate every Decimal still present in a nested structure."""
    found: list[str] = []

    def _walk(obj: Any, current: str) -> None:
        if isinstance(obj, Decimal):
            found.append(current)
            return
        if isinstance(obj, Mapping):
            for k, v in obj.items():
                _walk(v, f"{current}.{k}")
            return
        if isinstance(obj, (list, tuple, set, frozenset)):
            for i, v in enumerate(obj):
                _walk(v, f"{current}[{i}]")
            return
        if is_dataclass(obj) and not isinstance(obj, type):
            _walk(asdict(obj), current)

    _walk(value, path)
    return found
