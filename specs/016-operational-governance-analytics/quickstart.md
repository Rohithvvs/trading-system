# Quickstart & Verification Guide: Operational Governance & Analytics Layer

**Feature**: `016-operational-governance-analytics`  
**Date**: 2026-07-22  

This guide provides end-to-end verification scenarios to validate the implementation of Production Rule Governance (FEAT-026), Sector Strength Watch-Only Feature (FEAT-020), and Analytics Dashboard Endpoints (FEAT-028).

---

## 1. Prerequisites & Setup

Ensure the virtual environment is active and pytest dependencies are available:
```bash
# Activate virtual environment
source venv/Scripts/activate  # Windows PowerShell: .\venv\Scripts\Activate.ps1

# Ensure database is accessible
python check_db.py
```

---

## 2. Verification Scenarios

### Scenario A: Weekly Rule Governance Evaluation (FEAT-026)
Run the governance evaluation CLI command to generate a 30-day health report for all promoted rules:
```bash
python -m app.governance.experiment_cli governance-report
```
**Expected Outcome**:
- Output displays a table/JSON showing `news_dedup`, `sentiment_decay`, and `market_breadth`.
- Each rule shows `30d_fp_rate`, `baseline_fp_rate`, `sample_count`, and `health_status` (`GREEN`, `YELLOW`, `RED`, or `INSUFFICIENT_DATA`).
- Exit code is `0`.

### Scenario B: Passive Sector Strength Shadow Collection (FEAT-020)
Run a test market scan with Sector Strength enabled in shadow mode:
```bash
pytest backend/app/tests/test_sector_strength.py -v
```
**Expected Outcome**:
- `calculate_sector_strength` pure function computes relative sector return vs benchmark.
- Telemetry is successfully written to `shadow_outputs` under key `"sector_strength"`.
- Live 100-point scoring matrix and recommendation decisions remain 100% identical before and after sector strength calculation.

### Scenario C: Analytics Dashboard API Endpoints (FEAT-028)
Query the three analytics endpoints via HTTP or test client:
```bash
pytest backend/app/tests/test_analytics_dashboard.py -v
```
**Expected Outcome**:
1. `GET /api/v1/analytics/engine-health` returns 200 OK with rolling 7-day scan & recommendation metrics.
2. `GET /api/v1/analytics/shadow-status` returns 200 OK with active shadow rule execution telemetry.
3. `GET /api/v1/analytics/rule-governance` returns 200 OK matching the weekly governance report output.
4. On an empty database, all endpoints return 200 OK with clean default zeroed schemas (no 500 server errors).

---

## 3. Master Test Verification
Run all system unit and integration tests:
```bash
pytest backend/app/tests/ -v
```
