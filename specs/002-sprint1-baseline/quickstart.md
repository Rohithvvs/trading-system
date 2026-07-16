# Quickstart: Sprint 1 – Baseline & Diagnostics (Phase 0)

## Prerequisites

- Python 3.12+ with dependencies installed (`pip install -r backend/requirements.txt`)
- PostgreSQL running (via `docker-compose up` or existing instance)
- Node.js 18+ for frontend (`cd frontend && npm install`)
- Backend server running (`cd backend && uvicorn app.main:app --reload`)

## Validation Scenarios

### 1. Experiment Lifecycle

```bash
# Start a new experiment
python -m app.governance.experiment_cli start --name "phase0-baseline"

# Verify it's active
python -m app.governance.experiment_cli list --status active
# Expected: shows 1 active experiment

# Add a metric observation
python -m app.governance.experiment_cli metric --name cpu_usage --value 45.2

# Complete the experiment
python -m app.governance.experiment_cli complete

# Verify it's completed
python -m app.governance.experiment_cli list --status completed
# Expected: experiment status changed to completed, duration shown
```

### 2. Single Active Experiment Constraint

```bash
python -m app.governance.experiment_cli start --name "exp-1"
python -m app.governance.experiment_cli start --name "exp-2"
# Expected: Error — cannot start while another is active

python -m app.governance.experiment_cli complete
python -m app.governance.experiment_cli start --name "exp-2"
# Expected: Success — previous was completed first
```

### 3. Terminal State

```bash
python -m app.governance.experiment_cli start --name "terminal-test"
# Capture the experiment UUID from the start output, then:
python -m app.governance.experiment_cli complete
python -m app.governance.experiment_cli pause --id <uuid>
# Expected: Error — experiment is in terminal state (completed) and cannot be modified
```

### 4. Diagnostics Dashboard

```bash
# Start backend
cd backend && uvicorn app.main:app --reload

# Open browser
# http://localhost:8000/diagnostics
# Expected: Dashboard shows system metrics (CPU, memory, request rate, error rate)

# Ingest a test log event
curl -X POST http://localhost:8000/api/v1/dashboard/logs/ingest \
  -H "Content-Type: application/json" \
  -d '{"level":"info","source":"validation","message":"Quickstart test log"}'

# Verify in dashboard
# Expected: Log entry appears in LogViewer panel
```

### 5. Alerts

```bash
# Configure a test alert rule
# In config/alerts.yml:
# - name: high-cpu-test
#   metric_name: cpu_percent
#   condition: gt
#   threshold: 5.0
#   severity: warning
#   enabled: true

# Trigger the alert (ensure CPU > 5% — almost always true)
# Expected: Warning alert appears in AlertsPanel on dashboard
```

### 6. Audit Trail

```bash
# Perform some governance actions (start, complete experiments)

# Export audit trail
python -m app.governance.experiment_cli audit export --format json --since 2026-07-01
# Expected: JSON array of audit events with hash chain

# Verify chain integrity (separate script or method)
```

### 7. Test Suite

```bash
# Backend tests
cd backend
pytest app/tests/governance/ -v
pytest app/tests/observability/ -v

# Expected: All tests pass
```

## Expected Outcomes

- Experiment lifecycle fully functional with terminal states and single-active constraint
- Dashboard shows real-time system metrics and active experiment resource usage
- Log aggregation ingests and queries events from multiple sources
- Alerts trigger when thresholds are breached and appear in dashboard
- Audit trail exported as valid JSON/CSV with verifiable hash chain
- All governance actions produce audit events
- Test suite passes with >80% code coverage
