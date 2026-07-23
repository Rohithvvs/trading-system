# Implementation Plan: Taxonomy Alignment & Historical Backfill

**Branch**: `013-situation-taxonomy-backfill` | **Date**: 2026-07-21 | **Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/013-situation-taxonomy-backfill/spec.md)
**Input**: Feature specification from `/specs/013-situation-taxonomy-backfill/spec.md`

## Summary

This feature aligns historical and future recommendations under a standardized market situation taxonomy. By adding a `situation_tags` array column to `analysis_history`, executing a safe, resumable batch backfill for historical records, and implementing ongoing auto-tagging in the live engine, we enable situation-aware validation.

The implementation consists of:
1. **Schema Migration**: Add a non-blocking `situation_tags` `TEXT[]` column with a default `{}` and a concurrently created GIN index on `analysis_history`. Create the `backfill_progress` table.
2. **Deterministic Classifier**: A pure Python function that parses recommendation signals, sentiment scores, news, and market regimes to assign tags (`GOOD_NEWS_CATALYST`, `BAD_NEWS_CATALYST`, `EARNINGS_PLAY`, `MARKET_REGIME`, `RANGE_BOUND`, `UNKNOWN`).
3. **Resumable Batch Backfill Engine**: A CLI-triggered async service utilizing keyset paging (cursor-based pagination on `id`) to update historical records in small, throttled batches to prevent table locks.
4. **Ongoing Auto-Tagging**: Integration into `OrchestratorAgent._persist_analysis` to instantly tag and save recommendations.
5. **Observability CLI**: Distribution reporting command (`taxonomy-report`) to output tag share percentages.

---

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, SQLAlchemy, Alembic, asyncio, requests  
**Storage**: PostgreSQL (tables: `analysis_history`, `backfill_progress`, `news_articles`, `watched_stocks`)  
**Testing**: pytest (unit and integration tests)  
**Target Platform**: Linux / Windows Server  
**Project Type**: web-service / cli  
**Performance Goals**: Backfill batch execution database load < 5% CPU; tag queries retrieve filtered lists under 2 seconds.  
**Constraints**: Keyset paging on `id` with throttled batch updates; GIN index created concurrently.  
**Scale/Scope**: ~100k to 1,000,000 recommendations backfilled in non-blocking batches.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Gate | Status | Description |
|:---|:---|:---|
| **I. Library-First** | Passed | Tagging logic is implemented in a standalone, pure classifier module. |
| **II. CLI Interface** | Passed | Backfill and report commands are integrated into the existing governance CLI (`app.governance.experiment_cli`). |
| **III. Test-First (TDD)** | Passed | Classifier unit tests will be written and run before building the backfill script. |
| **IV. Integration Testing** | Passed | Integration test verifies that a simulated scanner run persists the tagged recommendation correctly. |
| **V. Observability** | Passed | Real-time progress logging and status tracking in the `backfill_progress` database table. |

---

## Project Structure

### Documentation (this feature)

```text
specs/013-situation-taxonomy-backfill/
├── plan.md              # This file
├── research.md          # Technical research and choices
├── data-model.md        # Database schema modifications and new tables
└── quickstart.md        # Runnable verification and validation steps
```

### Source Code

```text
backend/
├── alembic/
│   └── versions/        # Migration file to add column and GIN index
├── app/
│   ├── agents/
│   │   └── orchestrator_agent.py   # Call tagging function inside _persist_analysis
│   ├── db/
│   │   └── base.py                 # Register BackfillProgress model
│   ├── governance/
│   │   └── experiment_cli.py       # Expose CLI commands for backfill and report
│   ├── models/
│   │   └── analysis.py             # Add situation_tags column and define BackfillProgress model
│   └── services/
│       ├── backfill_service.py     # Backfill batch runner class (keyset paging + throttling)
│       └── taxonomy_classifier.py  # Pure tagging rules function
└── tests/
    ├── integration/
    │   └── test_backfill_integration.py # Backfill safety and transaction tests
    └── unit/
        └── test_taxonomy_classifier.py  # Unit tests for tagging heuristics
```

**Structure Decision**: Standard single project backend layout. All new services are placed under `backend/app/services/` and database models under `backend/app/models/`.

---

## Detailed Technical Steps

### 1. Database Migrations
- Generate an Alembic migration script to:
  - Add `situation_tags` column to `analysis_history` (`postgresql.ARRAY(sa.Text())`, server default `"{}"`, nullable `False`).
  - Create table `backfill_progress`.
  - Disconnect transaction (using `op.execute("COMMIT")` or `transactional_ddl = False`) to run `CREATE INDEX CONCURRENTLY` for the GIN index on `situation_tags`.

### 2. Heuristic Classifier (`taxonomy_classifier.py`)
- Implement `determine_situation_tags(symbol, recommendation, sentiment_score, articles, market_regime) -> list[str]`.
- Keywords list for `EARNINGS_PLAY` scan: `["earnings", "q1", "q2", "q3", "q4", "quarter", "dividend", "results", "profit", "revenue"]`.
- Return `["UNKNOWN"]` if essential inputs are missing.

### 3. Backfill Service (`backfill_service.py`)
- Implement `BackfillService.run_backfill(batch_size, delay, resume)`.
- Keyset paging query structure:
  ```python
  stmt = (
      select(AnalysisHistory)
      .where(AnalysisHistory.id > last_processed_id)
      .order_by(AnalysisHistory.id.asc())
      .limit(batch_size)
  )
  ```
- Match news articles for `EARNINGS_PLAY` by executing a join or select from the `news_articles` table where symbol matches and publish date is within +/- 3 days of the recommendation `created_at`.
- Save progress in `BackfillProgress` table at the end of each batch using an atomic update.
- Yield database locks between batches using `await asyncio.sleep(delay)`.

### 4. CLI Routing
- Extend `app.governance.experiment_cli` with:
  - `backfill`: Trigger/pause/resume a backfill job.
  - `taxonomy-report`: Query `analysis_history` using SQL aggregations to display the percentage share of each situation tag.

---

## Complexity Tracking

*No violations to track. Design follows the simplest path using native Postgres features, avoiding heavy dependencies.*
