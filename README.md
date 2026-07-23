# Stock Analysis And Recommendation System

This repository contains the phase 1 backend base for a stock analysis and recommendation system designed for manual trading only. The system is advisory-only, stores analysis history in SQLite, and does not place live trades.

## Phase 1 scope

- project structure for a full-stack app
- FastAPI backend base
- SQLite models and DB wiring
- modular architecture with `config`, `db`, `models`, `schemas`, `routes`, `services`, `agents`, and `utils`
- endpoint contracts for technical analysis, news analysis, backtesting, final recommendation, full analysis, and rankings
- mock-safe fallbacks when FYERS, Marketaux, or LLM keys are missing

## Project structure

```text
backend/
  app/
    agents/
    config/
    db/
    models/
    routes/
    schemas/
    services/
    utils/
    main.py
  requirements.txt
frontend/
  README.md
.env.example
README.md
```

## API endpoints

- `GET /health`
- `POST /stocks/analyze`
- `POST /analysis/technical`
- `POST /analysis/news`
- `POST /analysis/backtest`
- `POST /analysis/final-recommendation`
- `POST /analysis/full`
- `POST /analysis/rankings`
- `POST /analysis/screener/full`

## Setup

```powershell
cd "f:\trading system"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r .\backend\requirements.txt
uvicorn backend.app.main:app --reload
```

### Frontend

```powershell
cd "f:\trading system\frontend"
npm install
npm run dev
```

Open:

- `http://127.0.0.1:8000/docs` for backend docs
- `http://127.0.0.1:5173` for the frontend dashboard

## Logs

Backend pipeline logs are written to:

```text
f:\trading system\logs\trading_system.log
```

The log file includes messages for:

- whether FYERS live data or mock fallback was used
- which symbols were scanned
- which symbols failed data quality
- which symbols passed broad trend eligibility
- how weighted screener scores were computed
- which symbols were shortlisted
- which shortlisted symbols became BUY, WATCH, or REJECT
- per-symbol analysis completion and final recommendation

## Notes

- Recommendations are advisory only.
- Live order execution is intentionally not included.
- The frontend dashboard now supports symbol entry, mode/timeframe selection, rankings, charts, and per-stock detail panels.
- FYERS is wired with a fallback path. News, technical indicators, backtests, and recommendations still use placeholder-safe service logic where full live/provider logic has not been implemented yet.
- The Nifty 500 screener now scans the configured universe, keeps matched stocks, then analyzes only the top shortlist before highlighting BUY candidates in the UI.
- The combined Nifty 500 swing scanner now follows this staged pipeline:
  1. Fetch real OHLCV
  2. Validate data quality
  3. Apply broad trend eligibility
  4. Compute weighted screener score
  5. Keep top 20-50
  6. Run full analysis only on the top set
  7. RecommendationAgent decides BUY / WATCH / REJECT
  8. Rank BUY and WATCH separately

## Shadow Mode Configuration (FEAT-011 Spec 1)

The shadow infrastructure foundation is configured via environment variables loading into global `Settings` (`backend/app/config/settings.py`):

- `SHADOW_MODE_ENABLED`: `bool` (default `False`) — Master toggle for the orchestrator shadow hook.
- `SHADOW_MODE_STAGE`: `str` (default `"SHADOW"`) — Lifecycle stage. Valid values: `OFF`, `SHADOW`, `ACTIVE` (validated case-insensitively). The hook runs only when enabled **and** stage is not `OFF`. `ACTIVE` is reserved for future execution activation; Spec 1 still isolates shadow work from production scoring/API responses.
- `SHADOW_MODE_RULESET`: `str` (default `"experimental_v1"`) — Name of the experimental ruleset identity used when a concrete executor is registered later.
- `SHADOW_MODE_PERSISTENCE_ENABLED`: `bool` (default `False`) — **Non-binding in Spec 1.** Reserved for future `IShadowStore` database writes; setting this to `True` logs a warning and does not persist shadow comparisons yet.

Shadow observability:

- Logger: `app.shadow_executor`
- Registered audit actions: `shadow.execution.start`, `shadow.execution.complete`, `shadow.discrepancy.detected` (see `backend/app/governance/audit.py`)


## Fyers Access Token Automation & Database Storage (Sprint 4)

Sprint 4 integrates the headless Fyers login token automation utility with database storage and monitoring observability:

- **Token Generation & Retries**: Headless login flow using pure API + TOTP (`generate_fyers_access_token()`) automatically retries up to 3 times on transient errors, using randomized backoff delays (5.0s to 10.0s).
- **Database Persistence**: The generated access token is symmetrically Fernet-encrypted and persisted to the system-wide singleton row (`id=1`) in the `fyers_tokens` table in **one atomic transaction** (token + monitoring fields + history).
- **Monitoring Observability**: Every run updates the monitoring columns on `FyersToken`:
  - `status` (unified): `"Success"` on any successful token save (UI, OAuth, broker mirror, or automation), `"Failed"` on automation failure, `"inactive"` when deactivated. Legacy DB rows with `"active"` are still treated as connected.
  - `last_error`: Exception message (`str(exc)`, truncated) on failure; cleared to `None` on success.
  - `access_token_saved_at`: Update timestamp (UTC).
  - History note for automation: `Automated headless token generation`.
- **Status API extras** (`GET /api/token/status`):
  - `connection_status`: normalized `Connected` / `Expiring Soon` / `Expired` / `Disconnected` (works for both `active` and `Success`/`Failed`).
  - `automation_metrics`: in-process counters (`success_total`, `failure_total`, last outcome/latency).
- **CLI Runner** (replaces the old hardcoded SQLite `fyers_auth` injector — that path is retired):
  ```bash
  python update_token.py
  ```
  Exit `0` on success (prints masked token preview only); exit `1` on failure after recording `Failed` when the DB is reachable.
  Requires `DATABASE_URL` and Fyers credentials via environment / settings (never hardcode tokens).
- **Optional timeouts** (env):
  - `FYERS_TOKEN_JOB_TIMEOUT_SEC` (default `180`) — max wall time for generation thread.
  - `FYERS_TOKEN_DB_WRITE_TIMEOUT_SEC` (default `30`) — max wall time for DB commit.
- **Test Suite**:
  ```bash
  pytest tests/test_token_persistence.py
  ```

## Validation & Minimal Promotion (Sprint 5)

Sprint 5 implements the validation report, promotion gate, and dynamic routing for candidates moving from shadow mode to production:

- **Challenger Validation Report**:
  Generates key performance and false-positive metrics over the last 14 days of shadow execution data for a rule:
  ```bash
  python -m app.governance.experiment_cli report --rule news_dedup
  ```
  Saves report results to `governance/reports/challenger_report_news_dedup.json` and `.md`.

- **Minimal Promotion Gate**:
  Promotes a rule from `shadow` to `production` execution after verifying human checklist completion:
  ```bash
  python -m app.governance.experiment_cli promote --rule news_dedup --checklist-approved --reason "14-day shadow window is complete and checklist is verified"
  ```
  *Note: Checklist verification references `docs/FEAT_010_REVIEW_CHECKLIST.md`.*

- **Emergency Kill Switch (Rollback)**:
  Instantly disables any active rule to revert recommendation pipelines back to baseline:
  ```bash
  python -m app.governance.experiment_cli kill --rule news_dedup --reason "Emergency rollback: sentiment anomalies detected"
  ```

- **Testing**:
  ```bash
  pytest backend/tests/unit/test_validation_report.py
  pytest backend/tests/unit/test_rule_manager.py
  pytest backend/tests/integration/test_promotion_flow.py
  ```






