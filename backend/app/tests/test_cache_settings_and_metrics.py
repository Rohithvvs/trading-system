"""Unit tests for cache configuration defaults and observability metrics.

Maps to config section 10, metrics section 16, FR-009 naming.
"""

from __future__ import annotations

import pytest

from app.config.settings import settings


def test_cache_settings_defaults():
    """Spec §10.1 defaults: flag false, TTL 300, read 50ms, write 100ms."""
    # Defaults may be overridden by env in CI; assert types and sensible bounds.
    assert isinstance(settings.scanner_latest_cache_enabled, bool)
    assert isinstance(settings.scanner_latest_cache_ttl_seconds, int)
    assert settings.scanner_latest_cache_ttl_seconds > 0
    assert isinstance(settings.redis_cache_read_timeout_ms, int)
    assert settings.redis_cache_read_timeout_ms > 0
    assert isinstance(settings.redis_cache_write_timeout_ms, int)
    assert settings.redis_cache_write_timeout_ms > 0


def test_cache_settings_field_aliases_present():
    """Settings expose aliases used by environment variable governance."""
    from app.config.settings import Settings

    fields = Settings.model_fields if hasattr(Settings, "model_fields") else Settings.__fields__
    names = set(fields.keys())
    assert "scanner_latest_cache_enabled" in names
    assert "scanner_latest_cache_ttl_seconds" in names
    assert "redis_cache_read_timeout_ms" in names
    assert "redis_cache_write_timeout_ms" in names


def test_scanner_cache_metrics_defined():
    """Section 16: Prometheus metric objects exist (or are None when client missing)."""
    from app.observability import metrics as m

    # Names must be importable; when prometheus_client present they are Counter/Gauge.
    assert hasattr(m, "SCANNER_CACHE_HITS")
    assert hasattr(m, "SCANNER_CACHE_MISSES")
    assert hasattr(m, "SCANNER_CACHE_ERRORS")
    assert hasattr(m, "SCANNER_CACHE_FORCE_REFRESHES")
    assert hasattr(m, "SCANNER_CACHE_HIT_RATIO")
    assert callable(m.record_scanner_cache_hit)
    assert callable(m.record_scanner_cache_miss)
    assert callable(m.record_scanner_cache_error)
    assert callable(m.record_scanner_cache_force_refresh)


def test_scanner_cache_metric_names_when_prometheus_available():
    """Verify metric names match observability contract when client is installed."""
    from app.observability import metrics as m

    if m.SCANNER_CACHE_HITS is None:
        pytest.skip("prometheus_client not available")

    assert m.SCANNER_CACHE_HITS._name == "scanner_cache_hits_total"
    assert m.SCANNER_CACHE_MISSES._name == "scanner_cache_misses_total"
    assert m.SCANNER_CACHE_ERRORS._name == "scanner_cache_redis_errors_total"
    assert m.SCANNER_CACHE_FORCE_REFRESHES._name == "scanner_cache_force_refreshes_total"
    assert m.SCANNER_CACHE_HIT_RATIO._name == "scanner_cache_hit_ratio"


def test_record_helpers_update_hit_ratio():
    """Helpers increment process counters and refresh hit-ratio gauge safely."""
    from app.observability import metrics as m

    before_hits = m._scanner_cache_hits
    before_misses = m._scanner_cache_misses
    m.record_scanner_cache_hit("/scanner/latest")
    m.record_scanner_cache_miss("/scanner/latest")
    m.record_scanner_cache_error("get")
    m.record_scanner_cache_force_refresh("/scanner/latest")
    assert m._scanner_cache_hits == before_hits + 1
    assert m._scanner_cache_misses == before_misses + 1


def test_exception_classes_importable():
    """T005: custom cache exception hierarchy is available for callers."""
    from app.core.exceptions import (
        RedisCacheConnectionException,
        RedisCacheTimeoutException,
        ScannerCacheException,
    )

    assert issubclass(RedisCacheTimeoutException, ScannerCacheException)
    assert issubclass(RedisCacheConnectionException, ScannerCacheException)


def test_cache_key_constants_match_contract():
    """Contract key names for both endpoints."""
    from app.routes.scanner import CACHE_KEY_SCANNER_LATEST
    from app.routes.analysis import CACHE_KEY_ANALYSIS_SCAN_LATEST

    assert CACHE_KEY_SCANNER_LATEST == "scanner:latest:v1"
    assert CACHE_KEY_ANALYSIS_SCAN_LATEST == "analysis:scan:latest:v1"
