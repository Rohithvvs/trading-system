# Trading System V2 Engineering Constitution

**Version:** 1.0 [file:49]  
**Effective Date:** 27 June 2026 [file:49]  
**Status:** Supreme Governing Document [file:49]  
**Document Path:** `.specify/memory/constitution.md` [file:49]  
**Audience:** AI Coding Agents and Human Engineers [file:49]

> This Constitution is the highest authority for all development, refactoring, feature addition, and AI-assisted code generation on the Trading System V2 codebase. [file:49]
> Every AI agent must read this document in full before generating, modifying, reviewing, or deleting code in this repository. [file:49]
> Where this Constitution conflicts with another document, README, or prior implementation note, this Constitution wins. [file:49]
> This is a brownfield system, so rules must respect existing code and known debt unless an explicit migration is in scope. [file:49][file:31][file:32]

---

## PART I — Project Identity

### ID-001
Trading System V2 is a single-user, personal algorithmic trading and paper-trading platform for Indian equity markets, centered on the NIFTY500 universe. [file:49][file:33]

### ID-002
This system is not a multi-tenant SaaS platform, not a broker-side matching engine, and not a horizontally scaled public product. [file:49]

### ID-003
The current verified product scope includes market scanning, technical analysis, AI-assisted recommendations, paper trading, backtesting, market-data ingestion, and portfolio monitoring. [file:33][file:31]

### ID-004
Paper trading is a first-class production workflow today, while live trading remains non-primary and must not be assumed safe or enabled by default. [file:33][file:49]

---

## PART II — Engineering Philosophy

### PHIL-001
Correctness of financial state is the highest priority. All trading, risk, PnL, and capital calculations must be deterministic and reproducible. [file:49][file:31]

### PHIL-002
Reliability is mandatory. The market engine must degrade gracefully on bad ticks, token expiry, broker failure, or transient provider outage, and must not crash the main loop during market operation. [file:49][file:31]

### PHIL-003
Observability is mandatory. Order transitions, scheduler activity, WebSocket lifecycle changes, and major engine events must be traceable through structured logs and diagnostics. [file:49][file:31]

### PHIL-004
Idempotency is mandatory for all critical mutations. A retried request must not create duplicate financial effects. [file:49][file:31][file:33]

### PHIL-005
This is a brownfield codebase. AI agents must not refactor working code unless the refactor is explicitly requested, required for a feature, or required to satisfy a constitutional rule. [file:49]

### PHIL-006
AI agents must not introduce new dependencies without explicit user approval. Any approved dependency must be added to the appropriate dependency manifest and justified in the related change. [file:49]

### PHIL-007
AI agents must not generate mock, placeholder, or fake production-path implementations. If a task is too large, it must be split into complete, real slices. [file:49]

### PHIL-008
When an existing module violates this Constitution, agents must not propagate the violation to new code and must not silently “fix everything” outside task scope. Brownfield debt must be contained unless the user explicitly requests remediation. [file:49]

### PHIL-009
No change is complete until the agent has answered: “What happens if this code runs twice concurrently with the same idempotency key?” The acceptable answer is: “Exactly one effect occurs.” [file:49]

### PHIL-010
Every financial number that leaves the system through an API response, log line, report, or LLM prompt must be traceable to a deterministic computation. [file:49]

### PHIL-011
Definition of done means: the feature works, relevant tests pass, Constitution rules are respected, schema changes have Alembic migrations, request and response contracts are reflected in Pydantic models, and existing jobs or flows are not broken. [file:49]

---

## PART III — Architecture Principles

### ARCH-001
The system follows strict layered architecture: routes handle transport, services handle business logic, and models and schemas handle data representation. Cross-layer shortcuts are forbidden. [file:49][file:31][file:33]

### ARCH-002
FastAPI routes must stay thin. Routes may parse input, call services, and return typed responses, but must not contain business logic or direct provider logic. [file:49][file:31]

### ARCH-003
Business logic lives in `/services`. Financial rules, state transitions, risk checks, provider orchestration, and domain decisions must not be implemented in routes or React components. [file:49][file:31][file:32][file:33]

### ARCH-004
React components must remain presentation-oriented. UI components may manage UI state and call backend APIs, but business logic must be moved into backend services, custom hooks, or pure utilities as appropriate. [file:49][file:32]

### ARCH-005
All FYERS access, including REST and WebSocket access, must go through the existing service abstraction layer. No unrelated route, component, scheduler, or service may directly import the broker SDK. [file:49][file:31]

### ARCH-006
All Groq or LLM-provider access must go through the LLM service abstraction. No unrelated route, scheduler, or service may directly import the provider SDK. [file:49][file:31]

### ARCH-007
FastAPI dependency injection via `Depends(...)` must be used for request-scoped dependencies such as `AsyncSession` and related services. [file:49][file:31]

### ARCH-008
`AsyncSession` lifetime is request-scoped in API paths and job-scoped in background workers. Sessions must never be stored as module-level singletons or shared across requests. [file:49][file:31]

### ARCH-009
Module responsibilities must remain clear: routes own HTTP transport, services own business rules, models own ORM structure, schemas own Pydantic contracts, scheduler code owns registration and triggers, and pure utilities must remain side-effect free. [file:49][file:31][file:33]

### ARCH-010
No module may import upward across architectural layers, and circular dependencies are forbidden. Agents must prefer extension of existing modules over unnecessary new abstractions. [file:49]

### ARCH-011
Use APScheduler for scheduled jobs, asyncio for async I/O workflows, and a bounded thread pool only when blocking SDK or pandas-heavy work cannot remain async. [file:49][file:31][file:33]

### ARCH-012
Any background task created outside the main request flow must surface failures through logging and must never fail silently. [file:49][file:31]

---

## PART IV — Trading Domain Rules

### TRADE-001
All order and position state transitions must go through `live_state_machine.py`, which is the single source of truth for allowed lifecycle transitions. [file:49][file:31]

### TRADE-002
The enforced paper-trading lifecycle is `PENDING → ENTRY_FILLED → OPEN → CLOSED`, and transitions must not skip required intermediate states. [file:49][file:31][file:33]

### TRADE-003
Invalid state transitions must be rejected explicitly through typed errors or equivalent explicit handling. Silent no-ops are forbidden for invalid financial state changes. [file:49]

### TRADE-004
Every mutating paper-trading operation, including create, modify, cancel, and fill paths, must honor idempotency. Duplicate requests must not create duplicate side effects. [file:49][file:31][file:33]

### TRADE-005
Execution-event deduplication must be preserved. `dedupe_key` or equivalent uniqueness controls on execution records must not be weakened. [file:49][file:31][file:33]

### TRADE-006
Capital, margin, and PnL calculations must be derived deterministically from durable financial records and execution history, not from drift-prone cached state alone. [file:49][file:31][file:33]

### TRADE-007
Risk controls configured in account, strategy, or service logic must never be bypassed. No new trade path may ignore max-risk-per-trade, capital checks, or other enforced paper-trading limits. [file:32][file:31]

### TRADE-008
Position sizing must be implemented as a deterministic and testable function. It must not be embedded ad hoc across UI components or route handlers. [file:49][file:32]

### TRADE-009
New paper entries must respect Indian market-hours logic in the service layer, while exit flows must remain available so positions can be closed safely. [file:49][file:31]

### TRADE-010
All financial calculations, including PnL, sizing, Sharpe ratio, drawdown, and win rate, must be deterministic for the same inputs. Calculation functions must not depend on ambient runtime time like `datetime.now()`. [file:49][file:31]

### TRADE-011
Execution-event history is an immutable audit trail. Financial event rows must be treated as append-only records rather than mutable history. [file:49][file:33]

### TRADE-012
Direct position reversal in a single transition is forbidden. A position must close before an opposite-direction position is opened. [file:49]

### TRADE-013
A `CLOSED` position is terminal unless a clearly documented correction flow appends an explicit correction event with reasoned auditability. [file:49]

### TRADE-014
No code path may place a real broker order unless live trading is explicitly enabled by the user and supported by a dedicated, tested service path. Service-boundary checks are mandatory. [file:49]

---

## PART V — Market Data and Engine Rules

### MKT-001
The Market Engine owns the live FYERS WebSocket lifecycle. No other module may open an independent broker WebSocket outside the approved market-data path. [file:49][file:31]

### MKT-002
Token expiry, disconnects, provider errors, and degraded broker states must pause or degrade safely without crashing the engine. Known degraded states such as `TOKEN_EXPIRED_PAUSED` must be treated as controlled operating modes, not fatal failures. [file:49][file:31][file:32]

### MKT-003
Real-time candle cache data belongs in `candle_cache.db` or equivalent cache storage, while persistent trading records and durable history belong in PostgreSQL. Cache loss must not compromise correctness of core financial state. [file:49][file:31][file:33]

### MKT-004
Ticks must be aggregated deterministically into candle structures before downstream analysis, and any higher timeframe derivation must remain deterministic. [file:49][file:31]

### MKT-005
The system must continue to use reconciliation logic to detect and repair data gaps during engine operation. Gap-repair flows must prefer explicit repair over silently continuing on bad or missing data. [file:49][file:31]

### MKT-006
If the WebSocket feed is unavailable or degraded, the system may fall back safely to polling or equivalent degraded data retrieval, but that degradation must be explicit and observable. [file:49][file:31]

### MKT-007
Historical OHLCV data used for technical analysis, scanner logic, or backtesting must pass integrity validation before use. Invalid candles or structurally broken series must not flow silently into financial logic. [file:49][file:31]

### MKT-008
The orphaned `nightly_candle_sync` job is known debt. Agents must not build new features that assume it already runs unless they also explicitly attach or replace that scheduler path. [file:49][file:31]

### MKT-009
The Market Engine must remain resilient around reconnection, polling fallback, gap replay, and order evaluation, because these behaviors are core to the verified backend design. [file:31][file:33]

---

## PART VI — API Design Rules

### API-001
Existing route families and established backend API patterns must be respected unless a migration spec explicitly changes them. Agents must extend the current API shape rather than silently redesign it. [file:31][file:33]

### API-002
Every request body and response body must use strongly typed Pydantic models. Raw, untyped route contracts are forbidden. [file:49][file:31]

### API-003
Routes must return semantically correct HTTP status codes, including explicit conflict handling for idempotency collisions and business-rule violations. [file:49][file:31]

### API-004
User-facing API errors must never expose raw stack traces, internal table names, raw SQL, or unsafe internal implementation details. [file:49][file:31]

### API-005
The scanner’s streaming pattern must remain SSE-based where currently used, with explicit progress and failure signaling rather than opaque long-running synchronous blocking. [file:49][file:31][file:32]

### API-006
Frontend live tick delivery must remain WebSocket-oriented where currently used, rather than being replaced with aggressive polling. [file:32][file:31]

### API-007
Mutating routes must preserve idempotency semantics. Read routes must not be burdened with write-path idempotency requirements. [file:49][file:31]

### API-008
Long-running workflows such as scans or similar heavy operations must use streaming, background execution, or equivalent non-blocking patterns instead of freezing request threads. [file:49][file:31]

### API-009
Typed schemas and validation are part of the contract. If an API changes, its Pydantic schemas must change with it in the same unit of work. [file:49][file:31]

---

## PART VII — Frontend Rules

### FE-001
The frontend uses manual state-based routing through `mainView`. Agents must not introduce `react-router-dom` or another router library into this codebase. [file:32]

### FE-002
Global client state must remain based on React Context and local component state patterns already used in the app. Agents must not introduce Redux, Zustand, MobX, or similar external state managers. [file:32][file:49]

### FE-003
All external HTTP calls from the frontend must go through the existing `fetchWithDiagnostics` wrapper. Direct `fetch()` calls inside components are forbidden. [file:32][file:49]

### FE-004
React components must stay light on business logic. Financial rules, trade validation, and core domain decisions belong in backend services, not components. [file:32][file:49]

### FE-005
Vanilla CSS with CSS variables is the standard styling system for the codebase. Tailwind is existing debt limited to `CentralCommand.tsx` and must not spread into new files. [file:32][file:49]

### FE-006
`window.alert()`, `window.confirm()`, and `window.prompt()` are legacy debt and must not be introduced into new UI paths. Use inline errors, banners, or toast-style feedback instead. [file:32][file:49]

### FE-007
`App.tsx` and `Dashboard.tsx` are known duplicate-shell debt. Agents must not add the same new shell feature to both unless explicitly instructed. [file:32][file:49]

### FE-008
The current Paper Trading UI contains aggressive polling debt, including 1-second quote polling and 10-second status polling. Agents must not add new sub-5-second polling loops and should prefer WebSocket migration when touching those flows. [file:32]

### FE-009
The frontend must degrade safely on WebSocket disconnects, token-expired states, and provider/API failures without crashing the whole application. [file:32][file:31]

### FE-010
TypeScript quality must remain strict. New code must avoid `any` where practical and keep response types aligned with backend schemas. [file:49]

---

## PART VIII — Database and Concurrency Rules

### DB-001
All PostgreSQL schema changes must go through Alembic migrations. Manual schema changes outside migrations are forbidden. [file:49][file:31][file:33]

### DB-002
Database transactions for mutating service operations must be explicit and safe, with correct rollback behavior on failure. [file:49][file:31]

### DB-003
All database access in application code must remain async-first through SQLAlchemy `AsyncSession`. Synchronous database patterns are prohibited in normal request flows. [file:49][file:31]

### DB-004
Singleton background tasks must use the existing distributed lock approach rather than ad hoc concurrency control. [file:49][file:31]

### DB-005
Market-engine position processing and similar concurrent financial workflows must preserve row-level locking protections such as `FOR UPDATE SKIP LOCKED` where currently required. [file:49][file:31]

### DB-006
Critical write paths must preserve deduplication guarantees at the database level through unique keys or equivalent constraints. [file:49][file:31]

### DB-007
Trading records, orders, and positions are audit-heavy data. They must not be hard-deleted in normal flows when soft-delete or preserved history is the established pattern. [file:49]

### DB-008
Frequently queried foreign keys and hot-path temporal columns must remain indexed when schema work affects them. [file:49]

### DB-009
SQLite is cache storage, not the source of truth for durable financial state. No agent may move durable trading truth into SQLite. [file:49][file:33]

---

## PART IX — Background Jobs and Scheduling

### JOB-001
APScheduler is the standard scheduler for timed background jobs in this system and must remain the central registration point for scheduled work. [file:49][file:31]

### JOB-002
Every scheduler job must have a traceable identity, explicit trigger registration, and observable start, completion, and failure behavior. [file:49][file:31]

### JOB-003
Market-engine lifecycle scheduling around pre-market startup, market-hours operation, and close-down is core system behavior and must be preserved when scheduler logic is touched. [file:31][file:49]

### JOB-004
Reconciliation loops and data-health checks are core safety mechanisms and must not be removed or bypassed for convenience. [file:31][file:49]

### JOB-005
A failed background job must log clearly, exit cleanly, and avoid crashing the scheduler event loop. [file:49][file:31]

### JOB-006
Blocking calls in background jobs must not stall the event loop. If a job must run blocking SDK or heavy CPU work, it must use the appropriate bounded async boundary. [file:49][file:31][file:33]

---

## PART X — AI and LLM Rules

### AI-001
LLM access must remain isolated behind the LLM service layer, not scattered across routes, schedulers, or UI logic. [file:49][file:31]

### AI-002
LLM calls must be non-blocking relative to core backend responsiveness and must not hold up the market engine or critical request paths. [file:49][file:31]

### AI-003
All prompts to the LLM must request structured output, and all raw LLM output must be parsed and validated before use. [file:49][file:31]

### AI-004
If the LLM fails, times out, returns malformed output, or violates schema expectations, the system must fall back to deterministic rule-based logic instead of failing the user flow. [file:49][file:31]

### AI-005
LLM output is advisory only. It must not directly trigger autonomous order execution in this codebase. [file:49]

### AI-006
AI coding agents must preserve existing module boundaries, avoid circular imports, keep imports correct, and avoid introducing new architectural patterns without explicit approval. [file:49]

### AI-007
AI coding agents must not rename files, public functions, database columns, or major contracts without user approval and a safe migration path. [file:49]

### AI-008
AI coding agents must not commit secrets, `.env` files, local cache databases, or generated runtime artifacts into version control. [file:49]

---

## PART XI — Testing and Quality Rules

### TEST-001
All financial calculations must have deterministic unit tests. This includes PnL, position sizing, fees, drawdown, Sharpe ratio, win rate, and similar numerical logic. [file:49][file:31]

### TEST-002
The order lifecycle and `live_state_machine.py` transitions must have integration coverage for valid paths and rejection coverage for invalid paths. [file:49][file:31]

### TEST-003
Idempotency behavior must be tested. Submitting the same mutation twice with the same idempotency identity must prove that only one effect occurs. [file:49][file:31]

### TEST-004
No feature is complete until new tests pass, existing tests still pass, and any new migration runs successfully against a fresh test database when relevant. [file:49]

### TEST-005
Every bug fix should include a regression test that would have caught the bug before the fix. [file:49]

### TEST-006
Tests must not depend on live market data or live FYERS or Groq calls. External providers must be mocked or replaced with deterministic fixtures. [file:49]

### TEST-007
Deterministic fixtures must use fixed timestamps, fixed prices, fixed quantities, and explicit input data rather than runtime-dependent values. [file:49]

---

## PART XII — Security Rules

### SEC-001
The system currently lacks general API authentication, and that is known debt. Until auth is added, the app must be treated as a local or controlled single-user system rather than a public network service. [file:49][file:31]

### SEC-002
When authentication is added, it must be centralized through FastAPI dependency-driven enforcement rather than ad hoc checks spread across routes. [file:49]

### SEC-003
Broker tokens must be stored durably and safely, must not live only in volatile memory, and must never be logged. [file:49][file:31][file:33]

### SEC-004
Secrets must be sourced from environment-backed configuration and must never be committed to the repository. `.env` files remain excluded from version control. [file:49]

### SEC-005
All API inputs must be validated through typed schemas, and raw SQL string concatenation is forbidden. Database access must use ORM or parameterized patterns only. [file:49]

### SEC-006
Agents must not widen exposure of the app to public network usage without corresponding security controls. [file:49]

---

## PART XIII — Observability Rules

### OBS-001
The Python logging system must be used for backend logging rather than raw `print()` statements in normal paths. [file:49][file:31]

### OBS-002
Logs must include enough context to reconstruct what happened in order flows, scheduler runs, WebSocket transitions, provider failures, and reconciliation events. [file:49][file:31]

### OBS-003
Sensitive data such as API keys, broker tokens, and secrets must never appear in logs. [file:49]

### OBS-004
Order and position state transitions must be logged with before/after context and entity identifiers so financial-state changes are auditable. [file:49][file:31]

### OBS-005
Scheduler job starts, finishes, and failures must be logged explicitly so background health is visible. [file:49][file:31]

### OBS-006
Expected degradations such as token expiry, disconnects, or provider rate limits must be logged distinctly from unexpected crashes or programming errors. [file:49][file:31]

### OBS-007
Diagnostics and metrics should follow the established project patterns already present around scanner and system diagnostics rather than inventing a second observability style. [file:31]

---

## PART XIV — Amendment Rule

### AMD-001
This Constitution may be changed only by explicit user instruction. AI agents must not silently weaken, delete, or reinterpret rules to make an implementation easier. [file:49]