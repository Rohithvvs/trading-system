from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime


def sanitize_for_json(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Mapping):
        return {key: sanitize_for_json(item) for key, item in value.items()}

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_for_json(item) for item in value]

    return value
