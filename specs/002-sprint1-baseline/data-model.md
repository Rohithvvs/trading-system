# Data Model: Sprint 1 – Baseline & Diagnostics (Phase 0)

## Experiment

Persisted to PostgreSQL via SQLAlchemy model.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK, auto-generated | Unique experiment identifier |
| `name` | VARCHAR(255) | NOT NULL, UNIQUE | Human-readable experiment name |
| `status` | ENUM(`active`, `paused`, `completed`, `failed`) | NOT NULL, DEFAULT `active` | Current lifecycle state |
| `started_at` | TIMESTAMPTZ | NOT NULL | When the experiment was created/activated |
| `ended_at` | TIMESTAMPTZ | NULL | When the experiment was completed/failed |
| `duration_seconds` | INTEGER | NULL, computed | `ended_at - started_at` |
| `metadata` | JSONB | NULL | Arbitrary key-value metadata |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Record creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Record last-updated timestamp |

**State Machine:**
```
 [create] → active → paused ⇄ active → completed
            ↓                              ↓
          failed                        (terminal)
            ↓
        (terminal)
```
- Forward-only: `completed` and `failed` are terminal states.
- Only one experiment may be `active` at any time.
- `paused` → `active` transition is allowed (resume).

**Validation Rules:**
- Name must be unique (case-insensitive).
- Cannot create a second experiment while one is `active`.
- Cannot transition from `completed` or `failed` to any other state.

## MetricObservation

Persisted to file-based JSONL (one JSON object per line).

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `uuid` | UUID | Auto-generated | Unique observation identifier |
| `experiment_id` | UUID | NULL (system metrics) | Associated experiment, if any |
| `name` | VARCHAR(100) | NOT NULL | Metric name (e.g., `cpu_usage`) |
| `value` | FLOAT | NOT NULL | Numeric observation value |
| `unit` | VARCHAR(50) | NULL | Unit of measurement (e.g., `%`, `ms`) |
| `tags` | JSONB | NULL | Optional key-value dimensions |
| `timestamp` | TIMESTAMPTZ | NOT NULL | When the observation was recorded |

**Validation Rules:**
- `name` must match `^[a-z][a-z0-9_]{1,99}$` schema.
- `value` must be a finite number (no NaN, Infinity).
- `timestamp` must not be in the future (>5s skew allowed).

## Alert

Persisted to file-based JSONL.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `uuid` | UUID | Auto-generated | Unique alert identifier |
| `rule_name` | VARCHAR(100) | NOT NULL | Name of the alert rule that triggered |
| `severity` | ENUM(`info`, `warning`, `critical`) | NOT NULL | Alert severity level |
| `metric_name` | VARCHAR(100) | NOT NULL | The metric that breached the threshold |
| `metric_value` | FLOAT | NOT NULL | Observed value at time of breach |
| `threshold` | FLOAT | NOT NULL | The configured threshold value |
| `message` | TEXT | NULL | Human-readable alert description |
| `timestamp` | TIMESTAMPTZ | NOT NULL | When the alert was generated |

**Validation Rules:**
- Deduplication: if the same rule triggers repeatedly for the same metric within 60 seconds, only the first alert is logged; subsequent breaches update the last occurrence timestamp of the existing alert.

## AuditEvent

Persisted to append-only JSON file with hash chaining.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `uuid` | UUID | Auto-generated | Unique audit event identifier |
| `actor` | VARCHAR(100) | NOT NULL | Identity of the acting user/system |
| `action` | VARCHAR(100) | NOT NULL | Action performed (e.g., `experiment.start`, `experiment.complete`, `config.change`) |
| `target_type` | VARCHAR(50) | NOT NULL | Type of resource acted upon (e.g., `experiment`, `config`) |
| `target_id` | VARCHAR(255) | NULL | Identifier of the specific resource |
| `outcome` | ENUM(`success`, `failure`) | NOT NULL | Whether the action succeeded |
| `details` | JSONB | NULL | Additional context (request params, error message) |
| `timestamp` | TIMESTAMPTZ | NOT NULL | When the action occurred |
| `previous_hash` | VARCHAR(64) | NULL (first entry) | SHA-256 hex digest of the previous audit event (hash chain) |

**Immutability:**
- Each event includes `previous_hash` linking to the SHA-256 of the previous event's JSON (canonical serialization).
- Tampering with any entry breaks the chain; verification re-hashes all entries and compares links.
- Storage: append-only mode enforced at the file level (open with write-only append).

## AlertRule

Stored in YAML config file (e.g., `config/alerts.yml`).

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `name` | VARCHAR(100) | NOT NULL, UNIQUE | Rule identifier |
| `metric_name` | VARCHAR(100) | NOT NULL | Metric to evaluate |
| `condition` | ENUM(`gt`, `lt`, `gte`, `lte`, `eq`) | NOT NULL | Comparison operator |
| `threshold` | FLOAT | NOT NULL | Threshold value |
| `severity` | ENUM(`info`, `warning`, `critical`) | NOT NULL | Severity if triggered |
| `message_template` | TEXT | NULL | Template string for alert message |
| `enabled` | BOOLEAN | DEFAULT true | Whether the rule is active |
