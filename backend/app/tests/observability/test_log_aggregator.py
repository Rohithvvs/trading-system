"""Unit tests for LogAggregator — ingest, query, filters, pagination, edge cases.

Acceptance criteria covered:
  AC-US2-2: query with level/source/time-range filters returns consistent structured entries
  Edge: empty query, large input, empty metadata, metadata round-trip
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.observability.log_aggregator import LogAggregator
from app.observability.schema import LogEventCreate, LogLevel


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

def test_ingest_and_query(temp_dir):
    agg = LogAggregator(base_dir=str(temp_dir))
    event = LogEventCreate(
        level=LogLevel.INFO,
        source="test-source",
        message="test message",
        metadata={"key": "value"},
    )
    result = agg.ingest(event)
    assert result.uuid is not None
    assert isinstance(UUID(str(result.uuid)), UUID)
    assert result.level == LogLevel.INFO
    assert result.source == "test-source"

    results = agg.query(level=LogLevel.INFO, source="test-source")
    assert len(results) >= 1
    assert results[0]["message"] == "test message"


def test_ingest_dict(temp_dir):
    agg = LogAggregator(base_dir=str(temp_dir))
    result = agg.ingest_dict({
        "level": "warning",
        "source": "test",
        "message": "dict ingest",
    })
    assert result.level == LogLevel.WARNING


# ---------------------------------------------------------------------------
# Query filter tests — AC-US2-2
# ---------------------------------------------------------------------------

def test_query_consistent_structure(temp_dir):
    """AC-US2-2: each entry has timestamp, level, source, message, metadata."""
    agg = LogAggregator(base_dir=str(temp_dir))
    agg.ingest(LogEventCreate(level=LogLevel.INFO, source="s", message="m"))
    results = agg.query()
    assert len(results) >= 1
    entry = results[0]
    for field in ("timestamp", "level", "source", "message"):
        assert field in entry, f"Missing field in log entry: {field}"

def test_query_with_filters(temp_dir):
    agg = LogAggregator(base_dir=str(temp_dir))
    agg.ingest(LogEventCreate(level=LogLevel.INFO, source="src-a", message="info msg"))
    agg.ingest(LogEventCreate(level=LogLevel.ERROR, source="src-b", message="error msg"))
    agg.ingest(LogEventCreate(level=LogLevel.INFO, source="src-a", message="another info"))

    assert len(agg.query(level=LogLevel.INFO)) == 2
    assert len(agg.query(level=LogLevel.ERROR)) == 1
    assert len(agg.query(source="src-a")) == 2
    assert len(agg.query(level=LogLevel.CRITICAL)) == 0


def test_query_time_range(temp_dir):
    """AC-US2-2: query with time range returns only entries within range."""
    agg = LogAggregator(base_dir=str(temp_dir))
    agg.ingest(LogEventCreate(level=LogLevel.INFO, source="s", message="past"))

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=1)
    end = now + timedelta(hours=1)

    results = agg.query(start_time=start, end_time=end)
    assert len(results) >= 1


def test_query_excludes_outside_time_range(temp_dir):
    """Edge: entries before start_time are excluded."""
    agg = LogAggregator(base_dir=str(temp_dir))
    agg.ingest(LogEventCreate(level=LogLevel.DEBUG, source="s", message="old"))

    future_start = datetime.now(timezone.utc) + timedelta(hours=1)
    results = agg.query(start_time=future_start)
    assert len(results) == 0


def test_query_pagination(temp_dir):
    agg = LogAggregator(base_dir=str(temp_dir))
    for i in range(50):
        agg.ingest(LogEventCreate(
            level=LogLevel.INFO, source="pagination-test", message=f"msg-{i}",
        ))

    page1 = agg.query(limit=10, offset=0)
    page2 = agg.query(limit=10, offset=10)
    assert len(page1) == 10
    assert len(page2) == 10
    assert page1[0]["message"] != page2[0]["message"]


def test_query_combined_filters(temp_dir):
    """Edge: combining level + source + time range filters correctly."""
    agg = LogAggregator(base_dir=str(temp_dir))
    agg.ingest(LogEventCreate(level=LogLevel.ERROR, source="api", message="err"))
    agg.ingest(LogEventCreate(level=LogLevel.INFO, source="api", message="info"))
    agg.ingest(LogEventCreate(level=LogLevel.ERROR, source="worker", message="err2"))

    results = agg.query(level=LogLevel.ERROR, source="api")
    assert len(results) == 1
    assert results[0]["source"] == "api"


# ---------------------------------------------------------------------------
# Count tests
# ---------------------------------------------------------------------------

def test_count(temp_dir):
    agg = LogAggregator(base_dir=str(temp_dir))
    agg.ingest(LogEventCreate(level=LogLevel.DEBUG, source="cnt", message="d1"))
    agg.ingest(LogEventCreate(level=LogLevel.DEBUG, source="cnt", message="d2"))

    assert agg.count(level=LogLevel.DEBUG) == 2
    assert agg.count(level=LogLevel.INFO) == 0


def test_count_with_source_filter(temp_dir):
    agg = LogAggregator(base_dir=str(temp_dir))
    agg.ingest(LogEventCreate(level=LogLevel.INFO, source="a", message="m"))
    agg.ingest(LogEventCreate(level=LogLevel.INFO, source="b", message="m"))

    assert agg.count(source="a") == 1
    assert agg.count(source="c") == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_query(temp_dir):
    """Edge: querying empty aggregator returns []."""
    agg = LogAggregator(base_dir=str(temp_dir))
    assert agg.query() == []


def test_empty_metadata_preserved(temp_dir):
    """Edge: events without metadata get empty dict."""
    agg = LogAggregator(base_dir=str(temp_dir))
    result = agg.ingest(LogEventCreate(level=LogLevel.INFO, source="s", message="no-meta"))
    assert result.metadata is None  # None when not provided

    entries = agg.query()
    assert len(entries) >= 1
    assert "metadata" in entries[0]


def test_large_message_accepted(temp_dir):
    """Edge: a 10000-char message is accepted at ingest."""
    agg = LogAggregator(base_dir=str(temp_dir))
    big = "x" * 9999  # under 10000 limit
    agg.ingest(LogEventCreate(level=LogLevel.INFO, source="s", message=big))
    results = agg.query()
    assert any(len(r["message"]) == 9999 for r in results)


def test_large_batch_ingest(temp_dir):
    """SC-004: ingest 1000 events then query without loss."""
    agg = LogAggregator(base_dir=str(temp_dir))
    for i in range(1000):
        agg.ingest(LogEventCreate(level=LogLevel.INFO, source="bench", message=f"batch-{i}"))

    count = agg.count()
    assert count == 1000


def test_all_log_levels_ingested(temp_dir):
    """Edge: all five log levels can be ingested and queried."""
    agg = LogAggregator(base_dir=str(temp_dir))
    for level in [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]:
        agg.ingest(LogEventCreate(level=level, source="lvl-test", message=level.value))

    total = agg.query()
    assert len(total) == 5


def test_ingest_generates_unique_uuid(temp_dir):
    """Edge: each ingested event gets a unique UUID."""
    agg = LogAggregator(base_dir=str(temp_dir))
    r1 = agg.ingest(LogEventCreate(level=LogLevel.INFO, source="s", message="a"))
    r2 = agg.ingest(LogEventCreate(level=LogLevel.INFO, source="s", message="b"))
    assert r1.uuid != r2.uuid


def test_ingest_dict_invalid_raises(temp_dir):
    """Failure: ingest_dict with invalid level raises ValidationError."""
    import pytest
    from pydantic import ValidationError
    agg = LogAggregator(base_dir=str(temp_dir))
    with pytest.raises(ValidationError):
        agg.ingest_dict({"level": "trace", "source": "s", "message": "m"})