# Implementation Plan: Validation & Minimal Promotion

**Branch**: `012-validation-minimal-promotion` | **Date**: 2026-07-21 | **Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/012-validation-minimal-promotion/spec.md)
**Input**: Feature specification from `/specs/012-validation-minimal-promotion/spec.md`

## Summary

This plan outlines the technical design to build the Challenger Validation Report, the Rule Manager (Promotion Gate), and the Production Wiring for the first candidate feature (`news_dedup`). The state will be managed locally using a fast JSON file to ensure sub-millisecond query latency.

---

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, SQLAlchemy, Pandas, asyncio  
**Storage**: PostgreSQL (for analysis history and live orders), local JSON (for rule lifecycle states)  
**Testing**: pytest  
**Target Platform**: Linux / Windows Server  
**Project Type**: web-service / CLI  
**Performance Goals**: Active rule query latency < 1ms  
**Constraints**: Zero production impact unless promoted; instant rollback on kill; no new external dependencies  
**Scale/Scope**: Focuses on `news_dedup` rule lifecycle state and validation audit tracking

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Library-First**: The core validation calculator and state manager logic will be implemented as self-contained services inside `backend/app/services/`.
- **II. CLI Interface**: Administrative tasks are exposed via `app.governance.experiment_cli`.
- **III. Test-First**: pytest unit and integration tests will be developed alongside code implementation.
- **IV. Integration Testing**: Focused integration tests will prove the end-to-end promotion and kill path.
- **V. Observability**: All rule state transitions will write to `logs/audit.jsonl` via `AuditTrailManager`.

---

## Project Structure

### Documentation (this feature)

```text
specs/012-validation-minimal-promotion/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 interface contracts
│   ├── cli.md           # CLI contract for promote and kill
│   └── report.md        # CLI contract for report generation
└── tasks.md             # Phase 2 output (generated separately)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── agents/
│   │   └── news_analysis_agent.py   # Wires production deduplication route
│   ├── config/
│   │   ├── rule_states.json         # State store mapping
│   │   └── settings.py              # Loads path configurations
│   ├── governance/
│   │   ├── experiment_cli.py        # Exposes promote, kill, and report CLI commands
│   │   ├── router.py                # Registers command routes
│   │   └── rule_manager.py          # Rule lifecycle state coordinator
│   └── services/
│       └── validation_report.py     # Report generator logic
└── tests/
    ├── unit/
    │   └── test_rule_manager.py     # Verifies state loading and validation
    └── integration/
        └── test_promotion_flow.py   # Verifies production wiring and kill switches
```

**Structure Decision**: Monolith layout. Source files are placed under `backend/app/` and test files under `backend/tests/`.

---

## Complexity Tracking

*No constitution check violations exist.*

---

## Detailed Implementation Steps

### 1. Challenger Validation Report Calculator
* Create `backend/app/services/validation_report.py`.
* Implement query strategy against `AnalysisHistory`:
  * Load all `AnalysisHistory` records in the last 14 days containing `"news_dedup"` in `shadow_outputs`.
  * Safe extraction: `original_news_count = shadow_outputs.get("original_news_count")` (or from `"news_dedup"` sub-key).
  * Calculate total processed, total deduplicated, deduplication rate, average sentiment.
* Implement False-Positive correlation:
  * For each `AnalysisHistory` where recommendation is `"BUY"` or `"SELL"`, query `LiveOrder` (and `PaperOrder`) for the same `symbol` created within 24 hours of `created_at` where `status == "FILLED"`. If none is found, record as false positive.
  * `false_positive_rate = false_positive_count / total_signals`.
* Output: Save JSON report to `governance/reports/challenger_report_news_dedup.json` and Markdown report to `governance/reports/challenger_report_news_dedup.md`.
* Graceful handling: If zero records exist, warn operator and output 0 counts with `"FAIL"` status.

### 2. Rule Manager (`RuleManager`)
* Create `backend/app/governance/rule_manager.py`.
* Handle file loading/caching:
  * Cache values in an in-memory dictionary.
  * Load from `backend/app/config/rule_states.json` synchronously.
  * If the file is missing or has parsing errors, return `"shadow"` as the default state for `news_dedup` to guarantee safety.
* Implement transitions:
  * `promote_rule(rule_id, checklist_approved)`: Requires `checklist_approved` to be True. Writes state `"production"` to file and logs to `AuditTrailManager`.
  * `kill_rule(rule_id, reason)`: Writes state `"disabled"` to file and logs to `AuditTrailManager`.

### 3. Production Wiring
* Modify `backend/app/agents/news_analysis_agent.py`:
  * Query `RuleManager.is_active_in_production("news_dedup")`.
  * If True:
    * In-line deduplicate the article list before sentiment scoring: `articles = deduplicate_articles(articles)`.
    * Do not trigger the background shadow executor task.
  * If False (state is `"shadow"` or `"disabled"`):
    * Scoring runs on the original list.
    * If state is `"shadow"`, submit task to `ShadowThreadPool` as before. If state is `"disabled"`, do not submit shadow task.
