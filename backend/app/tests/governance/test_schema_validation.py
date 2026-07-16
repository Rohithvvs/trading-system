"""Unit tests for input validation schemas — FR-014, spec edge cases.

Verifies:
  - MetricObservationCreate: name regex, finite value, timestamp skew/future
  - LogEventCreate: level enum, source length, message length
  - AlertCreate: metric_name regex, finite metric_value
  - LogFilterParams: limit bounds
  - ExperimentFilterParams: limit bounds
  - AlertFilterParams: severity enum, since datetime
"""
from __future__ import annotations

import math
import warnings
from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

from app.observability.schema import (
    MetricObservationCreate,
    LogEventCreate,
    LogLevel,
    AlertCreate,
    AlertSeverity,
    AlertCondition,
    LogFilterParams,
    AlertFilterParams,
    ExperimentFilterParams,
)


# ---------------------------------------------------------------------------
# MetricObservationCreate
# ---------------------------------------------------------------------------

class TestMetricObservationCreate:
    def test_valid_metric(self):
        m = MetricObservationCreate(name="cpu_usage", value=45.2)
        assert m.name == "cpu_usage"
        assert m.value == 45.2

    def test_valid_metric_with_tags_and_unit(self):
        m = MetricObservationCreate(
            name="latency_ms", value=12.3, unit="ms",
            tags={"host": "srv1"},
        )
        assert m.tags == {"host": "srv1"}
        assert m.unit == "ms"

    def test_invalid_metric_name_uppercase(self):
        """FR-014: metric name must match ^[a-z][a-z0-9_]{1,99}$."""
        with pytest.raises(ValidationError):
            MetricObservationCreate(name="CPU_Usage", value=1.0)

    def test_invalid_metric_name_starts_with_digit(self):
        with pytest.raises(ValidationError):
            MetricObservationCreate(name="2cpu", value=1.0)

    def test_invalid_metric_name_empty(self):
        with pytest.raises(ValidationError):
            MetricObservationCreate(name="", value=1.0)

    def test_invalid_metric_name_too_long(self):
        """Edge: metric name over 100 chars is rejected."""
        with pytest.raises(ValidationError):
            MetricObservationCreate(name="a" * 101, value=1.0)

    def test_metric_value_nan_rejected(self):
        """Edge: NaN value is rejected."""
        with pytest.raises(ValidationError):
            MetricObservationCreate(name="cpu", value=float("nan"))

    def test_metric_value_inf_rejected(self):
        """Edge: Infinity value is rejected."""
        with pytest.raises(ValidationError):
            MetricObservationCreate(name="cpu", value=float("inf"))

    def test_metric_value_negative_inf_rejected(self):
        with pytest.raises(ValidationError):
            MetricObservationCreate(name="cpu", value=float("-inf"))

    def test_metric_value_zero_accepted(self):
        """Edge: zero is a valid finite value."""
        m = MetricObservationCreate(name="cpu", value=0.0)
        assert m.value == 0.0

    def test_metric_value_negative_accepted(self):
        m = MetricObservationCreate(name="offset", value=-42.5)
        assert m.value == -42.5

    def test_timestamp_future_rejected(self):
        """Edge: future timestamps are rejected."""
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        with pytest.raises(ValidationError):
            MetricObservationCreate(name="cpu", value=1.0, timestamp=future)

    def test_timestamp_within_skew_allowed(self):
        """Edge: timestamps within 5s skew are accepted (with a warning)."""
        past = datetime.now(timezone.utc) - timedelta(seconds=3)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = MetricObservationCreate(name="cpu", value=1.0, timestamp=past)
        assert m.timestamp == past


# ---------------------------------------------------------------------------
# LogEventCreate
# ---------------------------------------------------------------------------

class TestLogEventCreate:
    def test_valid_log_event(self):
        e = LogEventCreate(
            level=LogLevel.INFO,
            source="governance.experiment",
            message="Experiment started",
        )
        assert e.level == LogLevel.INFO
        assert e.source == "governance.experiment"

    def test_all_log_levels(self):
        """Edge: all five log levels are valid."""
        for level in [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]:
            e = LogEventCreate(level=level, source="s", message="m")
            assert e.level == level

    def test_empty_source_rejected(self):
        """FR-014: source must not be empty."""
        with pytest.raises(ValidationError):
            LogEventCreate(level=LogLevel.INFO, source="", message="m")

    def test_source_too_long_rejected(self):
        """Edge: source over 200 chars is rejected."""
        with pytest.raises(ValidationError):
            LogEventCreate(level=LogLevel.INFO, source="x" * 201, message="m")

    def test_empty_message_rejected(self):
        with pytest.raises(ValidationError):
            LogEventCreate(level=LogLevel.INFO, source="s", message="")

    def test_message_too_long_rejected(self):
        """Edge: message over 10000 chars is rejected."""
        with pytest.raises(ValidationError):
            LogEventCreate(level=LogLevel.INFO, source="s", message="x" * 10001)

    def test_invalid_level_enum_rejected(self):
        """FR-014: invalid log level is rejected."""
        with pytest.raises(ValidationError):
            LogEventCreate(level="trace", source="s", message="m")

    def test_metadata_preserved(self):
        e = LogEventCreate(
            level=LogLevel.INFO, source="s", message="m",
            metadata={"key": "val"},
        )
        assert e.metadata == {"key": "val"}


# ---------------------------------------------------------------------------
# AlertCreate
# ---------------------------------------------------------------------------

class TestAlertCreate:
    def test_valid_alert(self):
        a = AlertCreate(
            rule_name="high-cpu",
            severity=AlertSeverity.WARNING,
            metric_name="cpu_percent",
            metric_value=90.0,
            threshold=80.0,
        )
        assert a.rule_name == "high-cpu"
        assert a.severity == AlertSeverity.WARNING

    def test_alert_value_nan_rejected(self):
        with pytest.raises(ValidationError):
            AlertCreate(
                rule_name="r", severity=AlertSeverity.INFO,
                metric_name="cpu", metric_value=float("nan"), threshold=80.0,
            )

    def test_alert_invalid_metric_name(self):
        with pytest.raises(ValidationError):
            AlertCreate(
                rule_name="r", severity=AlertSeverity.INFO,
                metric_name="UPPER", metric_value=1.0, threshold=80.0,
            )

    def test_alert_rule_name_empty_rejected(self):
        with pytest.raises(ValidationError):
            AlertCreate(
                rule_name="", severity=AlertSeverity.INFO,
                metric_name="cpu", metric_value=1.0, threshold=80.0,
            )


# ---------------------------------------------------------------------------
# AlertCondition enum
# ---------------------------------------------------------------------------

class TestAlertCondition:
    def test_all_conditions_valid(self):
        for cond in [AlertCondition.GT, AlertCondition.LT, AlertCondition.GTE,
                     AlertCondition.LTE, AlertCondition.EQ]:
            assert cond is not None

    def test_condition_from_string(self):
        assert AlertCondition("gt") == AlertCondition.GT
        assert AlertCondition("lt") == AlertCondition.LT


class TestAlertSeverity:
    def test_all_severities_valid(self):
        for sev in [AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.CRITICAL]:
            assert sev is not None

    def test_severity_from_string(self):
        assert AlertSeverity("info") == AlertSeverity.INFO
        assert AlertSeverity("critical") == AlertSeverity.CRITICAL

    def test_invalid_severity_rejected(self):
        with pytest.raises(ValueError):
            AlertSeverity("emergency")


# ---------------------------------------------------------------------------
# LogFilterParams
# ---------------------------------------------------------------------------

class TestLogFilterParams:
    def test_defaults(self):
        p = LogFilterParams()
        assert p.limit == 100
        assert p.offset == 0

    def test_limit_at_min(self):
        p = LogFilterParams(limit=1)
        assert p.limit == 1

    def test_limit_at_max(self):
        p = LogFilterParams(limit=1000)
        assert p.limit == 1000

    def test_limit_below_min_rejected(self):
        with pytest.raises(ValidationError):
            LogFilterParams(limit=0)

    def test_limit_above_max_rejected(self):
        with pytest.raises(ValidationError):
            LogFilterParams(limit=1001)

    def test_negative_offset_rejected(self):
        with pytest.raises(ValidationError):
            LogFilterParams(offset=-1)


# ---------------------------------------------------------------------------
# AlertFilterParams
# ---------------------------------------------------------------------------

class TestAlertFilterParams:
    def test_defaults(self):
        p = AlertFilterParams()
        assert p.severity is None
        assert p.since is None

    def test_valid_severity(self):
        p = AlertFilterParams(severity="warning")
        assert p.severity == AlertSeverity.WARNING

    def test_invalid_severity_rejected(self):
        with pytest.raises(ValidationError):
            AlertFilterParams(severity="emergency")


# ---------------------------------------------------------------------------
# ExperimentFilterParams
# ---------------------------------------------------------------------------

class TestExperimentFilterParams:
    def test_defaults(self):
        p = ExperimentFilterParams()
        assert p.limit == 20
        assert p.offset == 0

    def test_limit_at_max(self):
        p = ExperimentFilterParams(limit=100)
        assert p.limit == 100

    def test_limit_above_max_rejected(self):
        with pytest.raises(ValidationError):
            ExperimentFilterParams(limit=101)

    def test_empty_name_rejected(self):
        """Edge: name filter must be at least 1 char if provided."""
        with pytest.raises(ValidationError):
            ExperimentFilterParams(name="")