from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertCondition(str, Enum):
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    EQ = "eq"


class ExperimentStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


METRIC_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,99}$")


class MetricObservationCreate(BaseModel):
    experiment_id: UUID | None = None
    name: str
    value: float
    unit: str | None = None
    tags: dict[str, str] | None = None
    timestamp: datetime | None = None

    @field_validator("name")
    @classmethod
    def validate_metric_name(cls, v: str) -> str:
        if not METRIC_NAME_RE.match(v):
            raise ValueError(
                f"Metric name '{v}' must match ^[a-z][a-z0-9_]{{1,99}}$"
            )
        return v

    @field_validator("value")
    @classmethod
    def validate_finite(cls, v: float) -> float:
        import math
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Metric value must be a finite number")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        now = datetime.now(timezone.utc)
        # Normalize to aware UTC for safe comparison
        if v.tzinfo is None:
            v_cmp = v.replace(tzinfo=timezone.utc)
        else:
            v_cmp = v.astimezone(timezone.utc)
        skew = abs((now - v_cmp).total_seconds())
        if skew > 5:
            import warnings
            warnings.warn(
                f"Timestamp skew of {skew:.1f}s exceeds 5s limit",
                UserWarning,
                stacklevel=2,
            )
        # Allow up to 5s clock skew into the future; reject beyond that
        if (v_cmp - now).total_seconds() > 5:
            raise ValueError("Timestamp must not be in the future")
        return v


class MetricObservation(MetricObservationCreate):
    uuid: UUID = Field(default_factory=uuid4)


class LogEventCreate(BaseModel):
    level: LogLevel
    source: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=10000)
    metadata: dict[str, Any] | None = None


class LogEvent(LogEventCreate):
    uuid: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AlertCreate(BaseModel):
    rule_name: str = Field(..., min_length=1, max_length=100)
    severity: AlertSeverity
    metric_name: str
    metric_value: float
    threshold: float
    message: str | None = None

    @field_validator("metric_value")
    @classmethod
    def validate_finite(cls, v: float) -> float:
        import math
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Metric value must be a finite number")
        return v

    @field_validator("metric_name")
    @classmethod
    def validate_metric_name(cls, v: str) -> str:
        if not METRIC_NAME_RE.match(v):
            raise ValueError(
                f"Metric name '{v}' must match ^[a-z][a-z0-9_]{{1,99}}$"
            )
        return v


class Alert(AlertCreate):
    uuid: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditEventCreate(BaseModel):
    actor: str = Field(..., min_length=1, max_length=100)
    action: str = Field(..., min_length=1, max_length=100)
    target_type: str = Field(..., min_length=1, max_length=50)
    target_id: str | None = None
    outcome: str = Field(default="success")
    details: dict[str, Any] | None = None


class AuditEvent(AuditEventCreate):
    uuid: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    previous_hash: str | None = None


class LogFilterParams(BaseModel):
    level: LogLevel | None = None
    source: str | None = Field(None, min_length=1, max_length=200)
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AlertFilterParams(BaseModel):
    severity: AlertSeverity | None = None
    since: datetime | None = None


class ExperimentFilterParams(BaseModel):
    status: ExperimentStatus | None = None
    since: datetime | None = None
    name: str | None = Field(None, min_length=1, max_length=255)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
