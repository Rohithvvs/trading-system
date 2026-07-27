from __future__ import annotations

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
except Exception:  # pragma: no cover
    Counter = Gauge = Histogram = None  # type: ignore[assignment]
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"


if Counter:
    ORDER_EXECUTIONS = Counter("trading_order_executions_total", "Order execution events", ["event_type", "symbol"])
    DUPLICATE_EXECUTIONS = Counter("trading_duplicate_execution_suppressed_total", "Suppressed duplicate executions", ["kind"])
    DB_COMMIT_LATENCY = Histogram("trading_db_commit_seconds", "Database commit latency")
    WS_CLIENTS = Gauge("trading_ws_clients", "Connected websocket clients", ["stream"])
    LOGGER_QUEUE_DEPTH = Gauge("trading_logger_queue_depth", "Logger queue depth")

    # Scanner Cache Metrics (Sprint 1 / feature 017)
    SCANNER_CACHE_HITS = Counter("scanner_cache_hits_total", "Scanner cache hit count", ["endpoint"])
    SCANNER_CACHE_MISSES = Counter("scanner_cache_misses_total", "Scanner cache miss count", ["endpoint"])
    SCANNER_CACHE_ERRORS = Counter("scanner_cache_redis_errors_total", "Scanner cache Redis error count", ["op"])
    SCANNER_CACHE_FORCE_REFRESHES = Counter(
        "scanner_cache_force_refreshes_total",
        "Scanner cache force-refresh count",
        ["endpoint"],
    )
    SCANNER_CACHE_HIT_RATIO = Gauge("scanner_cache_hit_ratio", "Scanner cache hit ratio (0.0 to 1.0)")
    LATEST_SCAN_SERVICE_INVOCATIONS = Counter(
        "latest_scan_service_invocations_total",
        "Invocations of LatestScanService.get_latest_scan",
        ["format"],
    )
    UNIFIED_LATEST_FALLBACKS = Counter(
        "unified_latest_fallback_total",
        "Unified latest-scan path failures that fell back to legacy",
        ["endpoint"],
    )
    # Sprint 3: Reduce Scan-Result Fan-out
    SCANNER_WRITES_TOTAL = Counter(
        "scanner_writes_total",
        "Scanner persistence write operations by table and status",
        ["table_name", "status"],
    )
    SCANNER_FEATURE_FLAG_MINIMAL_WRITES = Gauge(
        "scanner_feature_flag_minimal_writes",
        "Current SCAN_RESULT_MINIMAL_WRITES status (1=ON, 0=OFF)",
    )
    SCANNER_PERSIST_LATENCY = Histogram(
        "scanner_persist_latency_seconds",
        "Scanner persistence duration",
        ["mode"],
    )
else:
    ORDER_EXECUTIONS = DUPLICATE_EXECUTIONS = DB_COMMIT_LATENCY = WS_CLIENTS = LOGGER_QUEUE_DEPTH = None
    SCANNER_CACHE_HITS = SCANNER_CACHE_MISSES = SCANNER_CACHE_ERRORS = None
    SCANNER_CACHE_FORCE_REFRESHES = SCANNER_CACHE_HIT_RATIO = None
    LATEST_SCAN_SERVICE_INVOCATIONS = UNIFIED_LATEST_FALLBACKS = None
    SCANNER_WRITES_TOTAL = SCANNER_FEATURE_FLAG_MINIMAL_WRITES = SCANNER_PERSIST_LATENCY = None


# Process-local totals for hit-ratio gauge when Prometheus is available or for tests.
_scanner_cache_hits: int = 0
_scanner_cache_misses: int = 0
_latest_scan_service_invocations: int = 0
_unified_latest_fallbacks: int = 0
_scanner_writes: dict[tuple[str, str], int] = {}


def _update_scanner_cache_hit_ratio() -> None:
    total = _scanner_cache_hits + _scanner_cache_misses
    if SCANNER_CACHE_HIT_RATIO is None:
        return
    if total <= 0:
        SCANNER_CACHE_HIT_RATIO.set(0.0)
    else:
        SCANNER_CACHE_HIT_RATIO.set(_scanner_cache_hits / total)


def record_scanner_cache_hit(endpoint: str) -> None:
    global _scanner_cache_hits
    _scanner_cache_hits += 1
    if SCANNER_CACHE_HITS is not None:
        SCANNER_CACHE_HITS.labels(endpoint=endpoint).inc()
    _update_scanner_cache_hit_ratio()


def record_scanner_cache_miss(endpoint: str) -> None:
    global _scanner_cache_misses
    _scanner_cache_misses += 1
    if SCANNER_CACHE_MISSES is not None:
        SCANNER_CACHE_MISSES.labels(endpoint=endpoint).inc()
    _update_scanner_cache_hit_ratio()


def record_scanner_cache_error(op: str) -> None:
    if SCANNER_CACHE_ERRORS is not None:
        SCANNER_CACHE_ERRORS.labels(op=op).inc()


def record_scanner_cache_force_refresh(endpoint: str) -> None:
    if SCANNER_CACHE_FORCE_REFRESHES is not None:
        SCANNER_CACHE_FORCE_REFRESHES.labels(endpoint=endpoint).inc()


def record_latest_scan_service_invocation(format_type: str) -> None:
    """Count canonical LatestScanService.get_latest_scan invocations by format."""
    global _latest_scan_service_invocations
    _latest_scan_service_invocations += 1
    if LATEST_SCAN_SERVICE_INVOCATIONS is not None:
        LATEST_SCAN_SERVICE_INVOCATIONS.labels(format=format_type).inc()


def record_unified_latest_fallback(endpoint: str) -> None:
    """Count unified-path failures that fell back to legacy handlers."""
    global _unified_latest_fallbacks
    _unified_latest_fallbacks += 1
    if UNIFIED_LATEST_FALLBACKS is not None:
        UNIFIED_LATEST_FALLBACKS.labels(endpoint=endpoint).inc()


def record_scanner_write(table_name: str, status: str = "ok") -> None:
    """Count scanner DB write operations by table and outcome (ok|skipped|failed)."""
    key = (table_name, status)
    _scanner_writes[key] = _scanner_writes.get(key, 0) + 1
    if SCANNER_WRITES_TOTAL is not None:
        SCANNER_WRITES_TOTAL.labels(table_name=table_name, status=status).inc()


def set_minimal_writes_flag_metric(enabled: bool) -> None:
    """Emit gauge for SCAN_RESULT_MINIMAL_WRITES (1=ON, 0=OFF)."""
    if SCANNER_FEATURE_FLAG_MINIMAL_WRITES is not None:
        SCANNER_FEATURE_FLAG_MINIMAL_WRITES.set(1 if enabled else 0)


def observe_scanner_persist_latency(mode: str, seconds: float) -> None:
    """Record persistence latency histogram for minimal vs legacy mode."""
    if SCANNER_PERSIST_LATENCY is not None:
        SCANNER_PERSIST_LATENCY.labels(mode=mode).observe(max(0.0, float(seconds)))


def render_metrics() -> tuple[bytes, str]:
    if not Counter:
        return b"# prometheus_client unavailable\n", CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST
