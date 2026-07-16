# Implementation Plan: Sprint 1 – Baseline & Diagnostics (Phase 0)

**Branch**: `002-sprint1-baseline` | **Date**: 2026-07-16 | **Spec**: `specs/002-sprint1-baseline/spec.md`
**Input**: Feature specification from `/specs/002-sprint1-baseline/spec.md`

## Summary

Establish a governance framework (experiment tracking, agent command routing, audit trail) and an observability stack (diagnostics dashboard, log aggregation, monitoring/alerting, resource tracking) for the recommendation engine. Phase 0 runs on the existing Python/FastAPI backend with React frontend, using file-based storage for logs and append-only JSON for the audit trail, deferring database-backed persistence and distributed deployment to Phase 1.

## Technical Context

**Language/Version**: Python 3.12 (+ TypeScript 5.8 for frontend)  
**Primary Dependencies**: FastAPI (existing), Pydantic, SQLAlchemy (existing), psutil (resource monitoring), APScheduler (existing — alert evaluation), rich (CLI output)  
**Storage**: File-based JSON logs/audit trail (Phase 0); PostgreSQL via SQLAlchemy for experiment metadata  
**Testing**: pytest with pytest-asyncio (backend), Vitest + Testing Library (frontend)  
**Target Platform**: Linux (Render deployment)  
**Project Type**: Full-stack web application  
**Performance Goals**: Dashboard load <500ms, log ingestion 1000 events/sec, alert evaluation <10s, experiment lifecycle <2s  
**Constraints**: Single-node for Phase 0; file-based log/audit storage; single admin role; API key auth  
**Scale/Scope**: Single concurrent experiment; single admin user; 90-day log retention

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution file (`.specify/memory/constitution.md`) is currently a template — no binding principles defined. No gate violations to report.

## Project Structure

### Documentation (this feature)

```text
specs/002-sprint1-baseline/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 — research & decisions
├── data-model.md        # Phase 1 — entities & schema
├── quickstart.md        # Phase 1 — validation guide
├── contracts/           # Phase 1 — API contracts
└── tasks.md             # Phase 2 — task breakdown (created by /speckit.tasks)
```

### Source Code (repository root)

```text
# Governance & Experiment Framework
backend/app/governance/
├── __init__.py
├── experiment.py          # Experiment model, lifecycle CRUD
├── experiment_cli.py      # CLI command handlers (start, complete, query)
├── experiment_log.py      # Experiment log persistence (JSON file)
├── audit.py               # Audit trail manager (append-only JSON)
└── router.py              # Agent command routing (activation workflow)

# Observability & Diagnostics
backend/app/observability/  # Extend existing directory
├── __init__.py
├── dashboard.py            # Dashboard data provider (metrics API)
├── log_aggregator.py       # Log ingestion & query engine
├── alert_engine.py         # Alert rule evaluation engine
├── resource_tracker.py     # Per-experiment resource monitoring (psutil)
└── schema.py               # Input validation schemas (metric, log, filter)

# Diagnostics Dashboard (Frontend)
frontend/src/pages/Diagnostics.tsx         # Dashboard page
frontend/src/components/Diagnostics/       # Dashboard sub-components
├── MetricsPanel.tsx
├── LogViewer.tsx
├── AlertsPanel.tsx
└── ResourceUsagePanel.tsx

# Tests
backend/app/tests/
├── governance/
│   ├── test_experiment.py
│   ├── test_audit.py
│   └── test_router.py
└── observability/
    ├── test_dashboard.py
    ├── test_log_aggregator.py
    ├── test_alert_engine.py
    └── test_resource_tracker.py

frontend/src/tests/
└── diagnostics/
    └── test_DiagnosticsPage.test.tsx
```

**Structure Decision**: New `governance/` module under `backend/app/` for experiment/audit logic; extend existing `observability/` module for diagnostics; add `Diagnostics` page and components to the existing React frontend.
