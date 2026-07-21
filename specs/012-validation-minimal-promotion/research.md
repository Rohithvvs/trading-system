# Research & Technical Decisions: Validation & Minimal Promotion

This document details the technical research and design decisions for implementing the Validation Report, Minimal Promotion Gate, and Controlled Promotion Path.

---

## 1. False-Positive Rate Calculation Heuristic

* **Decision**: Implement **automatic log correlation**. A generated shadow recommendation (`BUY` or `SELL`) is flagged as a false positive if no matching order (a `BUY` order for a `BUY` recommendation, or a `SELL` order for a `SELL` recommendation) is successfully filled (`FILLED` status) in the `live_orders` (or `paper_orders`) table within a 24-hour window from the recommendation's timestamp.
* **Rationale**: This heuristic leverages existing database execution records (`live_orders`/`paper_orders`) to measure recommendation actionability. It is fully automated and does not require manual operator overhead or complex feedback interfaces.
* **Alternatives Considered**:
  * *Manual Auditing*: Rejected due to high operator overhead.
  * *Static Heuristic Rule Check*: Rejected because it does not capture real-world recommendation actionability.

---

## 2. Administrative Control Interface

* **Decision**: Extend the **CLI command interface** in `app.governance.experiment_cli` to support two new subcommands:
  * `python -m app.governance.experiment_cli promote --rule <rule_id> --checklist-approved`
  * `python -m app.governance.experiment_cli kill --rule <rule_id> --reason "<reason>"`
* **Rationale**: This design directly leverages the existing governance framework and module routing defined in `AGENTS.md` (which maps `/specify` agent commands to in-process python CLI calls). It keeps administrative tasks clean and segregated from standard runtime API routes.
* **Alternatives Considered**:
  * *REST API endpoints*: Exposing `POST /api/v1/governance/promote` and `/kill`. While useful for a frontend dashboard, the CLI is the primary administrative tool for this system in Phase 0. We will implement the CLI commands first and wrap them in light, optional FastAPI routes if needed.

---

## 3. Review Checklist Enforcement

* **Decision**: Implement a **process-level check (assertive flag)**. The CLI `promote` command requires the `--checklist-approved` flag to be explicitly passed. If the flag is omitted, the promotion is rejected with a clear instruction message pointing to `docs/FEAT_010_REVIEW_CHECKLIST.md`.
* **Rationale**: It enforces double-verification (the human must explicitly assert that they completed the review checklist), which aligns with the safety guidelines. This approach is highly robust and avoids fragile SQL checks mapping md files.
* **Alternatives Considered**:
  * *Database-state check*: Querying the database to check if a signed checklist record exists. Rejected for Phase 0 as it adds excessive database complexity and schema overhead.
  * *Audit warning only*: Letting the promotion succeed without enforcement but logging a warning. Rejected because it does not provide a strict gate.

---

## 4. State Storage for Rule Lifecycle

* **Decision**: Store rule states in a simple local JSON file at `backend/app/config/rule_states.json`. The states are represented as a mapping:
  ```json
  {
    "news_dedup": "shadow"
  }
  ```
  The `RuleManager` will load this file into a thread-safe in-memory cache on startup. Read queries will hit the cache (ensuring < 0.5ms latency). State updates (promote/kill) will write synchronously back to the JSON file and invalidate the cache.
* **Rationale**: This is the simplest safe option. It avoids database migrations, prevents locking contention on database connections during live recommendations, and matches existing config architectures (like `sector_mappings.json`).
* **Alternatives Considered**:
  * *Database table*: Rejected because it introduces DB roundtrips on every live recommendation scan, which threatens the sub-2ms query budget, and requires a migration.
  * *Environment Variables*: Rejected because env vars cannot be mutated easily at runtime across multiple worker processes.
