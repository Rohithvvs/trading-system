# Quickstart Validation Guide: Taxonomy Alignment & Backfill

This guide describes runnable validation scenarios and the **production deploy / backfill runbook** for Situation Taxonomy & Historical Backfill.

---

## Prerequisites

- PostgreSQL running with connection configured in `.env`.
- **Migrations applied before deploying application code** that writes `situation_tags` (see [Production deploy order](#production-deploy-order-required)).

---

## Production deploy order (required)

Deploy in this order to avoid insert failures on `analysis_history`:

1. **Database first** (staging, then production):
   ```bash
   cd backend
   alembic upgrade head
   ```
   Confirm revision `6ee2afcfc7b5` (or later) is applied:
   ```bash
   alembic current
   ```
2. **Application second** — ship the build that includes orchestrator tagging and backfill CLI.
3. **Smoke live tagging** (one symbol scan) before bulk backfill.
4. **Backfill only after smoke** — prefer low-traffic windows (SC-003).

If `API_KEY` or `GOVERNANCE_ADMIN_TOKEN` is set, pass admin credentials on taxonomy commands:

```bash
export GOVERNANCE_CLI_TOKEN="$API_KEY"   # or pass --admin-token
```

---

## Production backfill runbook (SC-003)

Goal: complete historical tagging without starving the live engine.

### Recommended first production run

```bash
cd backend
# Dry / controlled batch size + throttle
python -m app.governance.experiment_cli backfill \
  --job-id prod-taxonomy-backfill-1 \
  --batch-size 100 \
  --delay 0.5

# If load spikes, pause (runner exits cleanly between batches)
python -m app.governance.experiment_cli backfill-pause --job-id prod-taxonomy-backfill-1

# Resume later
python -m app.governance.experiment_cli backfill \
  --job-id prod-taxonomy-backfill-1 \
  --resume \
  --batch-size 100 \
  --delay 0.5
```

### Monitoring during backfill

```sql
SELECT job_id, status, last_processed_id, processed_count, total_count, updated_at
FROM backfill_progress
ORDER BY updated_at DESC
LIMIT 5;
```

- Status should progress `RUNNING` → `COMPLETED` (or `PAUSED` / `FAILED` after interrupt).
- Watch DB CPU/connection pool; increase `--delay` or reduce `--batch-size` if needed.
- Only **one** backfill job should run at a time (enforced by advisory lock + RUNNING check).

### Interrupt behavior

| Action | Expected status |
|--------|-----------------|
| Ctrl+C / SIGTERM | `FAILED` (cursor preserved; use `--resume`) |
| `backfill-pause` | `PAUSED` |
| Normal completion | `COMPLETED` |

---

## Historical earnings fidelity (ops note)

Backfill loads news context from, in order:

1. `news_articles` (if present), or  
2. `news_deduplication_audit` (titles as proxy),  

within **±3 days** of each recommendation’s `created_at`.

If neither table has rows for a symbol/window, live-style `EARNINGS_PLAY` may be under-represented historically. Live tagging still uses in-memory articles at scan time.

---

## Scenario 1: Schema Migration Verification

Validate that the `situation_tags` column and GIN index exist on `analysis_history` and that `backfill_progress` is created.

### Verification Steps

1. Run database migrations:
   ```bash
   alembic upgrade head
   ```
2. Verify table schema in PostgreSQL:
   ```sql
   SELECT column_name, data_type, column_default, is_nullable
   FROM information_schema.columns
   WHERE table_name = 'analysis_history' AND column_name = 'situation_tags';
   -- Expected: data_type ARRAY (or USER-DEFINED/ARRAY), is_nullable='NO'

   SELECT indexname, indexdef
   FROM pg_indexes
   WHERE tablename = 'analysis_history' AND indexname = 'ix_analysis_history_situation_tags';
   -- Expected: USING gin (situation_tags)

   SELECT table_name
   FROM information_schema.tables
   WHERE table_name = 'backfill_progress';
   ```

---

## Scenario 2: Deterministic Classification Unit Tests

```bash
cd backend
pytest tests/unit/test_taxonomy_classifier.py -q
```

Expected: all classifier unit tests pass (GOOD/BAD/EARNINGS/REGIME/RANGE_BOUND/UNKNOWN rules).

---

## Scenario 3: Controlled Backfill Command & Resumption

1. Start (requires `--job-id`):
   ```bash
   python -m app.governance.experiment_cli backfill \
     --job-id qs-backfill-1 --batch-size 100 --delay 0.5
   ```
2. Interrupt with Ctrl+C or:
   ```bash
   python -m app.governance.experiment_cli backfill-pause --job-id qs-backfill-1
   ```
3. Inspect progress:
   ```sql
   SELECT last_processed_id, status, processed_count, total_count
   FROM backfill_progress WHERE job_id = 'qs-backfill-1';
   ```
4. Resume:
   ```bash
   python -m app.governance.experiment_cli backfill --job-id qs-backfill-1 --resume
   ```
5. Expect `status='COMPLETED'` and `processed_count` covering the dataset.

---

## Scenario 4: Ongoing Auto-Tagging

1. Trigger a recommendation scan (example):
   ```bash
   python -m app.cli.run_scanner --symbol RELIANCE-EQ --mode swing
   ```
2. Query latest row:
   ```sql
   SELECT recommendation, sentiment_score, situation_tags
   FROM analysis_history
   ORDER BY id DESC LIMIT 1;
   ```
   Expected: `situation_tags` is non-null and contains at least one valid taxonomy label.

---

## Scenario 5: Tag Distribution Report & SC-004 Health

```bash
python -m app.governance.experiment_cli taxonomy-report
# optional: --output-dir /path/to/reports
```

Expected:

- Stdout table of counts/percentages.
- Files:
  - `governance/reports/taxonomy_distribution_YYYYMMDDTHHMMSS.md`
  - `governance/reports/taxonomy_distribution_report.md` (latest pointer)
- Report includes **SC-004 Health Status**:
  - `HEALTHY` if UNKNOWN &lt; 15% and no non-UNKNOWN tag &gt; 60% of records
  - `NEEDS_ATTENTION` if either threshold is breached
  - `N/A` if zero rows

### Analytical query (FR-007)

```bash
python -m app.governance.experiment_cli taxonomy-query \
  --tags GOOD_NEWS_CATALYST \
  --recommendation BUY \
  --start 2024-01-01T00:00:00 \
  --end 2024-12-31T23:59:59 \
  --limit 50
```

---

## Post-merge checklist (completion review observations)

| Observation | Action |
|-------------|--------|
| Deploy order | Migration → app → smoke → backfill (this document) |
| SC-003 non-disruption | Low-traffic window + throttle; pause if needed |
| SC-004 distribution health | Run `taxonomy-report` after first full backfill; act on `NEEDS_ATTENTION` |
| Historical earnings | Ensure news tables populated if EARNINGS_PLAY share is critical |
| PR packaging | Commit feature branch; call out migration in PR description |
