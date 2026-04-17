# Plan — Implementation Roadmap (based on current repo)

This roadmap is prioritized for moving the existing repository from a phase-1 advisory prototype to a production-ready system. Items are ordered by recommended sequence and include what exists, gaps, and refactor suggestions.

**What is already built (code references)**
- FastAPI backend with middleware and route wiring ([backend/app/main.py](backend/app/main.py)).
- Full analysis pipeline orchestrator and agents ([backend/app/agents/orchestrator_agent.py](backend/app/agents/orchestrator_agent.py), [backend/app/agents/*](backend/app/agents)).
- Domain services: technical analysis, backtest, recommendation, ranking, LLM wrapper, FYERS client, sentiment and news service ([backend/app/services]).
- Paper trading simulator and REST endpoints ([backend/app/services/paper_trading_service.py](backend/app/services/paper_trading_service.py) and [backend/app/routes/paper_trading.py](backend/app/routes/paper_trading.py)).
- React frontend with scanner, candidate table, detail panel, and paper trading UI (`frontend/src`).

**Missing / needs improvement (high priority)**
1. **Authentication & authorization** — no auth present. Add token/OIDC plus RBAC for trade simulation endpoints.
2. **Background processing for heavy work** — move `full` analysis and screener to background worker (Celery/Redis, RQ, or Azure Functions) instead of running synchronously in the HTTP worker.
3. **Circuit breakers & retries** — add robust error handling around FYERS, LLM, and news providers.
4. **DB migrations & production datastore** — add Alembic migrations and migrate from SQLite to managed DB (Azure SQL if desired).
5. **LLM governance & monitoring** — centralize LLM request logging, schema validation, and rate-limits; redact secrets from logs.

**Refactoring opportunities (medium priority)**
- Extract external clients (FyersService, LLMService, NewsService) behind clear interfaces and provide dependency injection for easier testing and replacement.
- Replace synchronous `requests` with `httpx` (async) or isolate blocking calls into worker threads.
- Move heavy numerical logic out of request path (wrap calls in job queue) and return a status resource + webhook/polling for completion.
- Replace inline DB commits with a repository / unit-of-work pattern to improve transactional clarity.

**Scalability improvements (longer-term)**
- Cache OHLCV and LLM results (Redis) to avoid repeated external calls for the same inputs.
- Use a message broker (Redis/RabbitMQ) and worker pool for analysis/backtests, enabling horizontal scaling of CPU-bound tasks.
- Add autoscaling and containerization (Docker + Kubernetes or Azure App Service + Azure Container Instances) and CI/CD pipelines.

**Concrete phased roadmap**

Phase A — Stabilize (0–2 weeks)
- Add authentication middleware and secure CORS. (Acceptance: endpoints reject unauthenticated requests.)
- Add structured logging and redact secrets. (Acceptance: no API keys in logs.)
- Add request timeouts and limiters for `/analysis/*` endpoints. (Acceptance: long requests rejected with 503 and queued.)

Phase B — Background jobs & reliability (2–6 weeks)
- Introduce a job queue and worker for `screener/full` and `full` analysis flows. Replace synchronous calls with a fire-and-forget pattern and a status API. (Acceptance: background job completes and updates DB; HTTP latency predictable.)
- Implement circuit breaker + retries for FYERS and LLM client. (Acceptance: external failures return graceful fallback and are rate-limited.)
- Add Alembic and migrate DB from SQLite to a networked RDBMS for multi-worker setups. (Acceptance: migrations run and tests pass.)

Phase C — Observability & governance (4–8 weeks)
- Instrument metrics (Prometheus) and traces (OpenTelemetry). (Acceptance: dashboards for request latency, job queue length, LLM call failures.)
- Harden LLM governance: schema validation, request sampling, logging of prompts/responses (redacted). (Acceptance: validated LLM outputs stored; anomalies alert.)

Phase D — Production readiness & scaling (ongoing)
- Containerize services and deploy to staging/cloud. (Acceptance: zero-downtime deploy pipeline.)
- Add automated end-to-end tests, load tests on analysis paths, and security audit.
- Enable caching layer and autoscaling policies for workers.

**Quick wins (1–3 days)**
- Add input size limits and request validation on endpoints (already partially present — extend to all inputs).
- Centralize error handling and convert some `ValueError` flows to typed error responses.
- Add simple job status endpoint and move one heavy route (e.g., `/analysis/full`) to return 202 + job id.

**Acceptance criteria for going to production**
- Auth + RBAC in place; secrets managed, TLS enforced.
- Background worker processing of heavy analysis tasks; system does not block web workers for CPU-bound tasks.
- LLM calls monitored and governed; external provider failures degrade to mock or cached results.
- DB migrations and a managed DB in place with backups.

**Risks & mitigations**
- Risk: LLM hallucination or schema mismatch. Mitigation: strict JSON schema validation + deterministic fallback.
- Risk: long API latencies from synchronous external calls. Mitigation: background workers + timeouts + caching.

**Next mechanical steps for me (if you want me to continue)**
1. Implement minimal auth + RBAC scaffold.
2. Add a background job example for `analysis/full` (Celery or built-in background task) and surface an API to poll status.
3. Add Alembic migrations skeleton and CI test run.
