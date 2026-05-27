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
else:
    ORDER_EXECUTIONS = DUPLICATE_EXECUTIONS = DB_COMMIT_LATENCY = WS_CLIENTS = LOGGER_QUEUE_DEPTH = None


def render_metrics() -> tuple[bytes, str]:
    if not Counter:
        return b"# prometheus_client unavailable\n", CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST

