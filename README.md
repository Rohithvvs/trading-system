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



