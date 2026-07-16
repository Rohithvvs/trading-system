# Research: Sprint 1 – Baseline & Diagnostics (Phase 0)

## Technology Decisions

### Experiment/Tracking Storage
- **Decision**: File-based JSON log for Phase 0; PostgreSQL for experiment metadata via existing SQLAlchemy models
- **Rationale**: PostgreSQL is already the project's primary database; experiment metadata (name, status, timestamps) benefits from queryability. Metric observations use file-based JSON for simplicity in Phase 0 to avoid schema churn.
- **Alternatives considered**: Pure PostgreSQL (schema churn for variable metric schemas), pure JSON (harder to query experiment state)

### Log Aggregation
- **Decision**: File-based append-only JSON per day (e.g., `logs/2026-07-16.jsonl`)
- **Rationale**: Simple, testable, no database dependency. Each line is a JSON object with timestamp, level, source, message. Querying uses line-by-line streaming with index file for time-range lookups.
- **Alternatives considered**: SQLite (file locking concerns), PostgreSQL (schema overhead for Phase 0)

### Alert Rule Evaluation
- **Decision**: In-process metrics evaluation using APScheduler (already in project) with configurable thresholds in YAML/JSON config
- **Rationale**: APScheduler is already a dependency; no additional infrastructure needed. Rules are checked on each metric ingestion tick.
- **Alternatives considered**: Dedicated event stream processor (overkill for Phase 0 single-node)

### Resource Monitoring
- **Decision**: psutil for process-level CPU/memory/I/O tracking per experiment window
- **Rationale**: psutil 6.0.0 is already in requirements.txt. Cross-platform, no external deps. Provides per-process and system-wide metrics.
- **Alternatives considered**: containers/cgroups (deferred to Phase 1 distributed deployment)

### Dashboard
- **Decision**: React page in existing frontend fetching metrics via new FastAPI REST endpoints
- **Rationale**: The existing frontend already has React/Recharts for charting. Adding a diagnostics page there is more maintainable than serving a separate embedded UI.
- **Alternatives considered**: Embedded HTML via FastAPI template (breaks existing UI pattern)

### CLI for Experiment Management
- **Decision**: Python Click-based CLI module (`experiment start`, `experiment complete`, `experiment list`, etc.) callable from command line
- **Rationale**: Aligns with existing Python tooling; no new CLI framework needed. Rich for formatted table output.
- **Alternatives considered**: REST API only (less convenient for admin), agent-based commands (too heavy for Phase 0)

### Authentication
- **Decision**: Reuse existing JWT/API key auth from the project's core security module
- **Rationale**: The project already has PyJWT, passlib, Argon2, and a security module in `backend/app/core/`. No new auth infrastructure needed.
- **Alternatives considered**: New auth system (unnecessary duplication)

### Audit Trail
- **Decision**: Append-only JSON file with SHA-256 hash chaining for immutability
- **Rationale**: Simple, verifiable, no DB overhead. Each entry links to the previous entry's hash. Tampering is detectable by re-hashing.
- **Alternatives considered**: PostgreSQL audit trigger (deferred to Phase 1), blockchain-style (overkill)

### Testing
- **Decision**: pytest with pytest-asyncio for backend; tempfile-based test fixtures for file storage
- **Rationale**: Matches existing test patterns in the project. Tempfile fixtures avoid polluting real logs during tests.
