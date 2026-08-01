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
    # Sprint 4: Authoritative Candle Store
    CANDLE_STORE_CACHE_HIT_TOTAL = Counter(
        "candle_store_cache_hit_total",
        "Authoritative candle store L1/L2 cache hits",
        ["tier"],
    )
    CANDLE_STORE_READ_SOURCE = Counter(
        "candle_store_read_source_distribution",
        "Candle store read source distribution",
        ["source"],
    )
    CANDLE_STORE_READ_LATENCY = Histogram(
        "candle_store_read_latency_seconds",
        "Candle store read latency by source",
        ["source"],
    )
    CANDLE_STORE_WRITE_TOTAL = Counter(
        "candle_store_write_total",
        "Candle store write operations",
        ["status"],
    )
    CANDLE_STORE_CONSISTENCY_FAILURES = Counter(
        "candle_store_consistency_failures_total",
        "Candle store consistency discrepancies repaired",
    )
    CANDLE_STORE_FEATURE_FLAG = Gauge(
        "candle_store_feature_flag_status",
        "AUTHORITATIVE_CANDLE_STORE_ENABLED (1=ON, 0=OFF)",
    )
    # Sprint 5: Scanner Single Final Write
    SCANNER_SINGLE_WRITE_DURATION = Histogram(
        "scanner_single_write_duration_seconds",
        "Single final write transaction duration in seconds",
    )
    SCANNER_ANALYSIS_DURATION = Histogram(
        "scanner_analysis_duration_seconds",
        "In-memory scanner analysis duration in seconds",
    )
    SCANNER_TRANSACTIONS_TOTAL = Counter(
        "scanner_transactions_total",
        "Total database transactions executed by scanner per run",
        ["mode"],
    )
    SCANNER_SINGLE_WRITE_FAILURES = Counter(
        "scanner_single_write_failures_total",
        "Failed single final write transactions total",
        ["reason"],
    )
    SCANNER_FEATURE_FLAG_SINGLE_WRITE = Gauge(
        "scanner_feature_flag_single_write",
        "Current SCANNER_SINGLE_FINAL_WRITE_ENABLED status (1=ON, 0=OFF)",
    )
else:
    ORDER_EXECUTIONS = DUPLICATE_EXECUTIONS = DB_COMMIT_LATENCY = WS_CLIENTS = LOGGER_QUEUE_DEPTH = None
    SCANNER_CACHE_HITS = SCANNER_CACHE_MISSES = SCANNER_CACHE_ERRORS = None
    SCANNER_CACHE_FORCE_REFRESHES = SCANNER_CACHE_HIT_RATIO = None
    LATEST_SCAN_SERVICE_INVOCATIONS = UNIFIED_LATEST_FALLBACKS = None
    SCANNER_WRITES_TOTAL = SCANNER_FEATURE_FLAG_MINIMAL_WRITES = SCANNER_PERSIST_LATENCY = None
    CANDLE_STORE_CACHE_HIT_TOTAL = CANDLE_STORE_READ_SOURCE = CANDLE_STORE_READ_LATENCY = None
    CANDLE_STORE_WRITE_TOTAL = CANDLE_STORE_CONSISTENCY_FAILURES = CANDLE_STORE_FEATURE_FLAG = None
    SCANNER_SINGLE_WRITE_DURATION = SCANNER_ANALYSIS_DURATION = SCANNER_TRANSACTIONS_TOTAL = None
    SCANNER_SINGLE_WRITE_FAILURES = SCANNER_FEATURE_FLAG_SINGLE_WRITE = None


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


def record_candle_store_metric(name: str, amount: int = 1) -> None:
    """Map internal candle-store counter names onto Prometheus series."""
    if name in {"l1_hits", "l2_hits"} and CANDLE_STORE_CACHE_HIT_TOTAL is not None:
        tier = "l1" if name == "l1_hits" else "l2"
        CANDLE_STORE_CACHE_HIT_TOTAL.labels(tier=tier).inc(amount)
        if CANDLE_STORE_READ_SOURCE is not None:
            CANDLE_STORE_READ_SOURCE.labels(source=tier).inc(amount)
    elif name == "l3_fetches" and CANDLE_STORE_READ_SOURCE is not None:
        CANDLE_STORE_READ_SOURCE.labels(source="l3").inc(amount)
    elif name == "legacy_fallbacks" and CANDLE_STORE_READ_SOURCE is not None:
        CANDLE_STORE_READ_SOURCE.labels(source="legacy").inc(amount)
    elif name == "writes_total" and CANDLE_STORE_WRITE_TOTAL is not None:
        CANDLE_STORE_WRITE_TOTAL.labels(status="ok").inc(amount)
    elif name == "write_errors" and CANDLE_STORE_WRITE_TOTAL is not None:
        CANDLE_STORE_WRITE_TOTAL.labels(status="error").inc(amount)
    elif name == "discrepancies_repaired" and CANDLE_STORE_CONSISTENCY_FAILURES is not None:
        CANDLE_STORE_CONSISTENCY_FAILURES.inc(amount)


def observe_candle_store_read_latency(source: str, seconds: float) -> None:
    if CANDLE_STORE_READ_LATENCY is not None:
        CANDLE_STORE_READ_LATENCY.labels(source=source).observe(max(0.0, float(seconds)))
    if CANDLE_STORE_FEATURE_FLAG is not None:
        try:
            from ..config.settings import settings

            CANDLE_STORE_FEATURE_FLAG.set(
                1 if settings.is_authoritative_candle_store_enabled() else 0
            )
        except Exception:
            pass


def set_single_final_write_flag_metric(enabled: bool) -> None:
    """Emit gauge for SCANNER_SINGLE_FINAL_WRITE_ENABLED (1=ON, 0=OFF)."""
    if SCANNER_FEATURE_FLAG_SINGLE_WRITE is not None:
        SCANNER_FEATURE_FLAG_SINGLE_WRITE.set(1 if enabled else 0)


def observe_single_write_duration(seconds: float) -> None:
    """Record single final write transaction duration."""
    if SCANNER_SINGLE_WRITE_DURATION is not None:
        SCANNER_SINGLE_WRITE_DURATION.observe(max(0.0, float(seconds)))


def observe_analysis_duration(seconds: float) -> None:
    """Record in-memory analysis duration."""
    if SCANNER_ANALYSIS_DURATION is not None:
        SCANNER_ANALYSIS_DURATION.observe(max(0.0, float(seconds)))


def record_scanner_transaction(mode: str = "single_final_write") -> None:
    """Count DB transactions executed per scan run."""
    if SCANNER_TRANSACTIONS_TOTAL is not None:
        SCANNER_TRANSACTIONS_TOTAL.labels(mode=mode).inc()


def record_single_write_failure(reason: str = "error") -> None:
    """Count failed single final write transaction attempts."""
    if SCANNER_SINGLE_WRITE_FAILURES is not None:
        SCANNER_SINGLE_WRITE_FAILURES.labels(reason=reason).inc()


def render_metrics() -> tuple[bytes, str]:
    if not Counter:
        return b"# prometheus_client unavailable\n", CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST
