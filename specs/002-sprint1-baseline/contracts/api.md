# API Contracts: Diagnostics Dashboard

## Endpoints

### GET /api/v1/dashboard/metrics

Return current system metrics and experiment resource usage.

**Response 200:**
```json
{
  "system": {
    "cpu_percent": 45.2,
    "memory_percent": 62.1,
    "memory_used_mb": 1024,
    "request_rate_per_sec": 15.3,
    "error_rate_per_sec": 0.1
  },
  "experiment": {
    "id": "uuid-here",
    "name": "test-exp",
    "cpu_percent": 12.3,
    "memory_percent": 8.7,
    "io_read_bytes_per_sec": 1024,
    "io_write_bytes_per_sec": 512
  }
}
```

### GET /api/v1/dashboard/logs

Query aggregated logs. Supports pagination and filtering.

**Query Params:**
- `level` (optional): `debug` | `info` | `warning` | `error` | `critical`
- `source` (optional): string filter
- `start_time` (optional): ISO 8601 timestamp
- `end_time` (optional): ISO 8601 timestamp
- `limit` (optional, default 100): max results
- `offset` (optional, default 0): pagination offset

**Response 200:**
```json
{
  "entries": [
    {
      "timestamp": "2026-07-16T10:00:00Z",
      "level": "info",
      "source": "governance.experiment",
      "message": "Experiment 'test-exp' started",
      "metadata": { "experiment_id": "uuid" }
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

### GET /api/v1/dashboard/alerts

Return active/recent alerts.

**Query Params:**
- `severity` (optional): `info` | `warning` | `critical`
- `since` (optional): ISO 8601 timestamp

**Response 200:**
```json
{
  "alerts": [
    {
      "uuid": "alert-uuid",
      "rule_name": "high-cpu",
      "severity": "warning",
      "metric_name": "cpu_percent",
      "metric_value": 85.0,
      "threshold": 80.0,
      "message": "CPU usage exceeded 80% threshold",
      "timestamp": "2026-07-16T10:00:00Z"
    }
  ]
}
```

### POST /api/v1/dashboard/logs/ingest

Ingest a log event from a source component.

**Request Body:**
```json
{
  "level": "info",
  "source": "governance.experiment",
  "message": "Experiment started",
  "metadata": { "experiment_id": "uuid" }
}
```

**Response 201:**
```json
{
  "status": "accepted",
  "uuid": "log-entry-uuid"
}
```
