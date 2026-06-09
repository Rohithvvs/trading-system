# Environment Variables Reference

This document provides a comprehensive reference of all environment variables used across the application, extracted from configuration files (`settings.py`, `docker-compose.yml`, `render.yaml`) and system documentation.

**Note:** Actual secret values must NEVER be committed to version control and should be securely injected via a secret manager (e.g., AWS Secrets Manager, GitHub Secrets) or a `.env` file in local environments.

## Core Backend & Infrastructure Variables

| Variable Name | Purpose | Used By | Required | Default Value | Security Impact |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `DATABASE_URL` | Primary PostgreSQL connection string. Must use `postgresql+asyncpg://` schema. | Backend DB config, Alembic migrations | Yes | `postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system` | **High** - Contains database credentials |
| `REDIS_URL` | Primary Redis connection string. | Backend caching, task queues | Yes | `redis://localhost:6379/0` | **Medium** - Connection details |
| `APP_NAME` | Name of the application. | Backend application initialization | No | `Trading System` | Low |
| `APP_ENV` | Deployment environment (e.g., development, production). | Backend configuration | No | `development` | Low |
| `QUARANTINE_MODE` | Toggles system quarantine mode (safety feature). | Backend trading logic | No | `False` | Medium - Alters operational state |
| `APP_HOST` | Host address for the application server. | Backend uvicorn startup | No | `127.0.0.1` | Low |
| `APP_PORT` / `PORT` | Port on which the application runs. | Backend uvicorn, Render deployment | No | `8000` (Render dynamically injects `$PORT`) | Low |
| `CORS_ORIGINS` | Comma-separated list of allowed UI domains for Cross-Origin Resource Sharing. | FastAPI middleware | Yes | `http://localhost:5173,...` | Medium - Prevents unauthorized origins |
| `PYTHON_VERSION` | Specifies the Python runtime version. | Render deployment | Yes (Render) | `3.12.0` | Low |
| `POSTGRES_USER` | Initial Postgres user. | docker-compose | Yes (Docker) | `trading_user` (local) | High in prod |
| `POSTGRES_PASSWORD` | Initial Postgres password. | docker-compose | Yes (Docker) | `trading_password` (local) | High in prod |
| `POSTGRES_DB` | Initial Postgres database name. | docker-compose | Yes (Docker) | `trading_db` (local) | Low |

## Third-Party Integrations & API Keys

| Variable Name | Purpose | Used By | Required | Default Value | Security Impact |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `FYERS_APP_ID` | Broker authentication app identifier. | Fyers Integration | Yes | `""` | Medium |
| `FYERS_SECRET_ID` | Securely sign OAuth tokens for broker authentication. | Fyers Integration | Yes | `""` | **High** - Must never be exposed |
| `FYERS_ACCESS_TOKEN` | Broker authentication token. | Fyers API calls | No (stored in DB) | `""` | **High** - Allows executing trades |
| `FYERS_PIN` | Broker account PIN. | Broker Login | No | `""` | **High** - Personal credential |
| `FYERS_REDIRECT_URI` | Broker OAuth callback URI. | OAuth Flow | If UI auth used | `""` | Low |
| `GROQ_API_KEY` | API token required for LLM OrchestratorAgent. | LLM / Orchestrator Agent | Yes | `""` | Medium - Quota theft risk |
| `LLM_PROVIDER` | Specifies the language model provider. | LLM Integration | No | `groq` | Low |
| `LLM_MODEL` | Specifies the exact LLM model to use. | LLM Integration | No | `LLAMA_3_70B` | Low |
| `NEWS_API_KEY` | API token for fetching latest catalyst news streams. | News Ingestion Service | Yes (if marketaux) | `""` | Medium - Quota theft risk |
| `NEWS_PROVIDER` | Specifies the news API provider. | News Ingestion Service | No | `marketaux` | Low |
| `NEWS_BASE_URL` | Base URL for the news API. | News Ingestion Service | No | `https://api.marketaux.com/v1/news/all` | Low |

## Domain & Symbol Configuration

| Variable Name | Purpose | Used By | Required | Default Value | Security Impact |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `NIFTY500_CSV_PATH` | Path to the Nifty 500 symbols CSV file. | Symbol Loading | No | `ind_nifty500list.csv` | Low |
| `NIFTY500_SYMBOLS` | Overrides dynamic universe pools. | Symbol Screener | No | `""` | Low |
| `NIFTY_NEXT_500_SYMBOLS` | Overrides dynamic universe pools. | Symbol Screener | No | `""` | Low |
| `NIFTY1000_SYMBOLS` | Overrides dynamic universe pools. | Symbol Screener | No | `""` | Low |
| `UNIVERSE_SYMBOLS` | Overrides dynamic universe pools. | Symbol Screener | No | `""` | Low |
| `BSE500_SYMBOLS` | Overrides dynamic universe pools. | Symbol Screener | No | `""` | Low |
| `BSE1000_SYMBOLS` | Overrides dynamic universe pools. | Symbol Screener | No | `""` | Low |
| `FYERS_SCREENER_SYMBOLS` | Hardcoded default symbols for screener. | Symbol Screener | No | List of 25+ top caps | Low |
| `ADVISORY_DISCLAIMER` | Legal disclaimer string presented to users. | UI/Frontend | No | `"Advisory only..."` | Low |

## Frontend Variables

| Variable Name | Purpose | Used By | Required | Default Value | Security Impact |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `VITE_API_URL` / `VITE_API_BASE_URL` | Explicit mapping to the backend domain. | Frontend | Yes | N/A | Low |
| `VITE_WS_URL` | Dedicated websocket endpoint configuration. | Frontend | No | N/A | Low |

## Deprecated / Unused Variables

| Variable Name | Purpose | Used By | Required | Default Value | Security Impact |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `MONGO_URL` | MongoDB connection string (deprecated in favor of Postgres). | Unused | No | `""` | Low |
| `MONGO_DB_NAME` | MongoDB database name (deprecated). | Unused | No | `""` | Low |

---
*Generated by AI documentation agent.*
