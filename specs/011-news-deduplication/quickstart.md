# Quickstart Validation Guide: News Deduplication & Governance Workflows

This guide provides step-by-step verification procedures to validate the News Deduplication (FEAT-014) and Prompt Templates (FEAT-009) features.

## 1. Prerequisites
- Python 3.11 virtual environment activated:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- PostgreSQL database running and migrations applied:
  ```bash
  cd backend
  alembic upgrade head
  ```
- Shadow remains **disabled by default** (`SHADOW_MODE_ENABLED=false`). Enable only for shadow validation.

---

## 2. Test Execution

All verification suites are written in `pytest`. Execute the following commands to prove correctness:

### A. Run Heuristic Unit Tests
Verify the pure deduplication logic, time window groupings, source prioritization, stop words filtering, and edge cases.
```bash
pytest backend/tests/unit/test_news_deduplication.py -v
```

### B. Run Shadow Isolation & Logging Tests
Ensure that database write failures do not propagate to the production recommendations flow and that duplicate logs are written properly.
```bash
pytest backend/tests/integration/test_news_dedup_shadow.py -v
```

### C. Run Prompt Template Checks
```bash
pytest backend/tests/unit/test_research_prompt_templates.py -v
```

### D. Related regression slice
```bash
pytest backend/tests/integration/test_orchestrator_integration.py \
  backend/tests/api/test_analysis_endpoints.py \
  backend/tests/unit/test_agents.py \
  backend/tests/unit/test_shadow_config.py \
  backend/tests/regression/test_shadow_infra_foundation_regression.py -v
```

### Recorded verification (2026-07-21)
| Suite | Result |
|-------|--------|
| Unit news deduplication | PASS |
| Unit research prompt templates | PASS |
| Integration news dedup shadow | PASS |
| Orchestrator integration | PASS |
| Analysis full + screener SSE | PASS |
| Shadow config / FEAT-011 regression | PASS |

---

## 3. Manual E2E Validation Flow

To run E2E verification via script:
1. Apply migrations (`alembic upgrade head`).
2. Set `SHADOW_MODE_ENABLED=true` and `SHADOW_MODE_STAGE=SHADOW` in the environment.
3. Trigger a recommendation / full analysis for a test stock (e.g., `RELIANCE-EQ`) that has multiple duplicate headlines in the news source.
4. Confirm the production API response returns the **unfiltered** sentiment path:
   - Response still includes the full article set used for production scoring.
   - Recommendation action is not altered by shadow dedup.
5. Inspect the PostgreSQL database to verify audit trail recording:
   - Run: `SELECT * FROM news_deduplication_audit WHERE symbol='RELIANCE-EQ' ORDER BY created_at DESC LIMIT 20;`
   - Check that removed duplicates are logged with `kept_id`, `deduplicated_id`, `similarity`, and `reason`.
6. Verify the `analysis_history` table's JSONB `shadow_outputs` field:
   - Run:  
     ```sql
     SELECT shadow_outputs
     FROM analysis_history ah
     JOIN watched_stocks ws ON ws.id = ah.stock_id
     WHERE ws.symbol = 'RELIANCE-EQ'
     ORDER BY ah.created_at DESC
     LIMIT 1;
     ```
   - Confirm nested `"news_dedup"` counts and flat `original_news_count` / `kept_news_count`.
7. Disable shadow again for normal operation (`SHADOW_MODE_ENABLED=false`).

### Manual E2E checklist status
| Step | Status |
|------|--------|
| Migrations applied | Required per environment before enable |
| Automated isolation + persistence tests | ✅ Verified in pytest |
| Live market E2E with production news feed | Operator-run after deploy |

---

## 4. Feature flags

| Variable | Default | Notes |
|----------|---------|-------|
| `SHADOW_MODE_ENABLED` | `false` | Master toggle |
| `SHADOW_MODE_STAGE` | `SHADOW` | Must not be `OFF` for hook to run |
| Combined gate | off | `settings.is_shadow_hook_enabled()` |
