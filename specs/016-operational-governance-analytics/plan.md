# Implementation Plan: Operational Governance & Analytics Layer

**Branch**: `016-operational-governance-analytics` | **Date**: 2026-07-22 | **Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/016-operational-governance-analytics/spec.md)  
**Input**: Feature specification from `/specs/016-operational-governance-analytics/spec.md`

## Summary

Build the long-term operational layer for the Recommendation Engine, shifting it from a single project delivery model into a living, self-monitoring system. This feature implements:
1. **Production Rule Governance (FEAT-026)**: Automated weekly 30-day rolling false-positive evaluation comparing promoted rules against `baseline_v1.0.json` with sample-size protection and discrete health status assignment (`GREEN`, `YELLOW`, `RED`, `INSUFFICIENT_DATA`).
2. **Sector Strength Watch-Only Feature (FEAT-020)**: Passive calculation of sector performance relative to broader market benchmarks executed strictly in shadow mode via `ShadowThreadPool` and persisted into `shadow_outputs["sector_strength"]` without altering live 100-point scores.
3. **Lightweight Analytics Dashboard (FEAT-028)**: Three FastAPI endpoints (`GET /api/v1/analytics/engine-health`, `GET /api/v1/analytics/shadow-status`, `GET /api/v1/analytics/rule-governance`) providing visibility without direct database SQL access.

---

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, SQLAlchemy (PostgreSQL / SQLite), Pandas, asyncio, Pydantic  
**Storage**: PostgreSQL (`AnalysisHistory.shadow_outputs` JSONB, `AnalysisHistory` records)  
**Testing**: pytest, pytest-asyncio  
**Target Platform**: Windows / Linux server (backend Web API + CLI governance runner)  
**Project Type**: Web service + CLI operational governance tools  
**Performance Goals**: Dashboard endpoints response latency < 2s; shadow task queue overhead < 5ms  
**Constraints**: Zero impact on live 100-point scoring matrix; row-level SAVEPOINT/FOR UPDATE lock on shadow writes; non-destructive brownfield changes only; no heavy ML dependencies.  
**Scale/Scope**: 7-day and 30-day rolling aggregation windows across scanned stocks.  

---

## Constitution Check

*GATE: Passed before Phase 0 research and verified post-Phase 1 design.*

- [x] **Brownfield Architecture Integrity**: No modifications to core scoring matrix or recommendation pipelines. All shadow operations run asynchronously via `ShadowThreadPool`.
- [x] **Watch-Only Safety**: Sector Strength runs purely in shadow mode; outputs are recorded in `shadow_outputs` JSONB and never read by live recommendation or scoring services.
- [x] **Database Lock & Isolation**: Shadow writes use PostgreSQL server-side JSONB `||` merge and row-level locking (`_shadow_outputs_write_lock` + `_merge_shadow_outputs_locked`).
- [x] **Simplicity & Auditability**: Uses simple, deterministic statistical formulas and standardized JSON schema outputs.

---

## Project Structure

### Documentation (this feature)

```text
specs/016-operational-governance-analytics/
├── plan.md              # This implementation plan
├── research.md          # Phase 0 research findings and decisions
├── data-model.md        # Phase 1 entity definitions and schemas
├── quickstart.md        # Phase 1 verification scenarios and run guide
├── contracts/
│   └── analytics-api.json  # OpenAPI schema contract for analytics endpoints
└── checklists/
    └── requirements.md  # Specification quality checklist
```

### Source Code Layout

```text
backend/app/
├── governance/
│   ├── rule_manager.py           # Existing rule state management
│   ├── rule_governance.py        # NEW: FEAT-026 governance evaluation service & baseline comparator
│   └── experiment_cli.py         # UPDATED: Exposes governance-report CLI command
├── services/
│   ├── sector_strength.py        # NEW: FEAT-020 pure relative strength calculation logic
│   └── shadow_executor.py        # UPDATED: Includes execute_shadow_sector_strength task wrapper
├── routes/
│   ├── analytics.py              # NEW: FEAT-028 FastAPI router with 3 dashboard endpoints
│   └── __init__.py               # UPDATED: Includes analytics_router in api_router
└── tests/
    ├── test_rule_governance.py   # NEW: FEAT-026 governance evaluation unit & integration tests
    ├── test_sector_strength.py   # NEW: FEAT-020 pure function and shadow isolation tests
    └── test_analytics_dashboard.py # NEW: FEAT-028 API endpoint tests
```

---

## Technical Implementation Breakdown

### Module 1: Production Rule Governance (FEAT-026)
- **File**: `backend/app/governance/rule_governance.py`
- **Logic**:
  - Load baselines from `baseline_v1.0.json` (defaults to `0.15` if missing).
  - Query `AnalysisHistory` records in the 30-day window for promoted rules (`news_dedup`, `sentiment_decay`, `market_breadth`).
  - Calculate 30-day false-positive rate:
    $$\text{FP Rate} = \frac{\text{BUY recommendations with negative/zero outcome}}{\text{Total BUY recommendations in 30d}}$$
  - Sample-size protection: If sample count $< 15$, status = `INSUFFICIENT_DATA`.
  - Status rules:
    - `GREEN` (`healthy`): Rate $\le$ Baseline + 0.05
    - `YELLOW` (`caution`): Baseline + 0.05 < Rate $\le$ Baseline + 0.15
    - `RED` (`degraded`): Rate > Baseline + 0.15
- **CLI Integration**: Expose CLI command `governance-report` in `experiment_cli.py` and map route in `AGENTS.md`.

### Module 2: Sector Strength – Watch-Only Feature (FEAT-020)
- **File**: `backend/app/services/sector_strength.py`
- **Logic**:
  - Pure calculation comparing sector average price returns against market benchmark index (e.g. NIFTY50).
  - Classify sector relative strength into `Outperforming` ($> +1\%$), `Neutral` ($\pm 1\%$), or `Underperforming` ($< -1\%$).
  - Low-confidence handling: If constituent count $< 3$ or benchmark missing, set `confidence = "low"`, `relative_strength = null`.
- **Shadow Integration**:
  - Add `execute_shadow_sector_strength` in `shadow_executor.py`.
  - Submit via `ShadowThreadPool` during market scans.
  - Write telemetry under `shadow_outputs["sector_strength"]` using atomic JSONB merge.
  - Zero live matrix impact guarantee.

### Module 3: Analytics Dashboard Endpoints (FEAT-028)
- **File**: `backend/app/routes/analytics.py`
- **Endpoints**:
  - `GET /api/v1/analytics/engine-health`: 7-day rolling scan totals, recommendation counts (BUY/SELL/HOLD), win-rate, confidence average.
  - `GET /api/v1/analytics/shadow-status`: Telemetry and execution counts for all active shadow rules (`news_dedup`, `sentiment_decay`, `market_breadth`, `sector_strength`).
  - `GET /api/v1/analytics/rule-governance`: Invokes `rule_governance.py` and returns JSON report of rule health statuses.
- **Registration**: Include router in `backend/app/routes/__init__.py`.
- **Fault Handling**: Graceful return of HTTP 200 with default zeroed schema on empty database.

### Module 4: Operational Verification & Testing
- Unit & integration tests covering:
  1. `test_rule_governance.py`: Status assignment rules, sample-size protection, baseline comparison.
  2. `test_sector_strength.py`: Pure calculation accuracy, low-confidence handling, shadow task submission, 0% score mutation.
  3. `test_analytics_dashboard.py`: Endpoint payload schemas, HTTP status codes, empty-database resilience.

---

## Complexity Tracking

> No constitution violations. All additions are modular, isolated, and strictly follow brownfield patterns.
