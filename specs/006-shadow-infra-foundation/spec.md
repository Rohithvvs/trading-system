# Feature Specification: Shadow Infrastructure Foundation

**Feature Branch**: `006-shadow-infra-foundation`  
**Created**: 2026-07-20  
**Status**: Draft  
**Input**: User description: "FEAT-011 Shadow Infrastructure Specification 1 Shadow Infrastructure Foundation"

---

## 1 Feature Summary

The objective of Specification 1 is to establish the architectural foundation required for Shadow Mode. It prepares the platform for future specifications (including the Shadow Executor, Persistence, Telemetry, and Crash Isolation modules) by introducing only foundational infrastructure. This specification must NOT introduce any production behavior changes, API response mutations, scoring modifications, or trade execution changes. 

In this phase:
- We define configuration models and feature flags.
- We establish the base interfaces for shadow execution and persistence.
- We formulate the execution contexts and telemetry structures.
- We outline the safe, isolated insertion points within the existing async-first pipeline.

---

## 2 Previous Specification Review

- **Sprint 1 (Baseline & Diagnostics)**: Introduced the core governance database models (`Experiment`), lifecycle states (`active`, `paused`, `completed`, `failed`), and diagnostics log/metric persistence (`ExperimentLog`, `AuditTrailManager`). Shadow Mode will leverage the `ExperimentService` and `Experiment` models to coordinate active shadow rulesets and use `ExperimentLog` to capture comparative metrics.
- **Sprint 2 (Hardening)**: Hardened async execution boundaries and performance. Existing services must remain untouched.
- **FEAT-024A (Execution Costs Config)**: Introduced execution cost configuration parameters (slippage_bps, commission_fixed, etc.) in `Settings`. Future shadow execution will simulate these costs on experimental recommendations for realistic scoring comparison.
- **FEAT-024B (Portfolio Config)**: Introduced portfolio constraint parameters (starting_capital, max_concurrent_positions, etc.) in `Settings`. These will eventually govern the simulated capital allocation of the shadow portfolio.
- **Existing Recommendation Pipeline**: Consists of `OrchestratorAgent`, `RecommendationAgent`, and `RecommendationService`. They compute composite scores and apply Strict Buy Gate, FEAT-004 (Market Regime), and FEAT-007 (Sector Relative Strength) overlays. These must remain completely unaffected.
- **Existing AnalysisService (AnalyticsService)**: Tracks strategy performance and drift by comparing past recommendations against current prices. Shadow Mode will eventually reuse these tracking pathways.
- **Existing BacktestService**: Runs historical backtests.
- **Existing database models & async transactions**: Models (`WatchedStock`, `AnalysisHistory`, `BacktestHistory`) and async transaction handling (where each symbol is persisted in its own local async session `async with AsyncSessionLocal() as db:`) must not be disrupted or blocked.

---

## 3 Current Architecture Analysis

The existing recommendation pipeline flows as follows:
1. **Screener/Analysis API POST request** triggers `OrchestratorAgent.run_full`.
2. `OrchestratorAgent` fetches market data (candles), computes vectorized TA indicators.
3. For each symbol, `OrchestratorAgent._analyze_symbol_post_bulk` gathers backtest, sentiment, and fundamental analysis concurrently via `asyncio.gather` and `asyncio.to_thread`.
4. The production `RecommendationAgent.run` is called, delegating to `RecommendationService.build` to compute the composite score and label (`BUY`, `WATCH`, `REJECT`).
5. Overlays (Strict Buy Gate, FEAT-004, FEAT-007) adjust the score and label to produce the production `recommendation` and `challenger_recommendation`.
6. `OrchestratorAgent._persist_analysis` commits these to the database via `AsyncSessionLocal`.
7. `StockAnalysisResult` is returned to the API layer and client.

### insertion Point for Shadow Mode
Shadow Mode execution naturally belongs at the end of the per-symbol pipeline in `OrchestratorAgent._analyze_symbol_post_bulk`, immediately after the production recommendation and challenger recommendation have been successfully resolved, but **before** the final results are returned. 
To ensure zero impact on production:
- Shadow execution must run asynchronously, isolated in an exception-safe envelope.
- Shadow outputs must not modify the production `StockAnalysisResult` returned to the API client.
- Shadow database persistence must be decoupled from the production transaction boundary to prevent database lock contention or rollback contamination.

---

## 4 Files To Modify

| File | Reason | Change Type |
|---|---|---|
| `backend/app/config/settings.py` | Introduce new configuration parameters and feature flags for Shadow Mode. | Extension |
| `backend/app/schemas/analysis.py` | Add non-disruptive, optional schemas for shadow comparison logs and metadata. | Extension |
| `backend/app/agents/orchestrator_agent.py` | Add the execution hook for the shadow execution pathway inside `_analyze_symbol_post_bulk` inside an exception-safe try/except block. | Extension |

---

## 5 Infrastructure Design

Specification 1 defines the following abstract contracts and data contexts to support Shadow Mode:

### Shadow Execution Configuration (Settings)
- `shadow_mode_enabled`: (bool, default `False`) Master toggle to enable shadow pathways.
- `shadow_mode_stage`: (str, default `"SHADOW"`) Lifecycle stage: `"OFF"`, `"SHADOW"` (compute and log, do not affect production), `"ACTIVE"` (reserved for future execution activation).
- `shadow_mode_ruleset`: (str, default `"experimental_v1"`) Identifies which experimental recommendation logic to run.
- `shadow_mode_persistence_enabled`: (bool, default `False`) Toggles whether shadow results are written to the database.

### Shadow Execution Context (`ShadowExecutionContext`)
A data transfer object (DTO) that groups the inputs of the current market snapshot to pass to the experimental logic:
- `symbol`: str
- `candles`: list[OHLCVPoint]
- `technical_results`: list[TechnicalAnalysisResult]
- `sentiment_score`: float
- `fundamental_result`: FundamentalAnalysisResult | None
- `backtests`: list[BacktestResult]
- `production_recommendation`: FinalRecommendation
- `production_challenger_recommendation`: FinalRecommendation
- `scan_date`: datetime

### Shadow Execution Interface (`IShadowExecutor`)
Defines the contract that any experimental ruleset must implement:
- `async def execute_shadow(context: ShadowExecutionContext) -> ShadowExecutionResult`

### Shadow Store Interface (`IShadowStore`)
Defines the contract for persisting comparative results:
- `async def save_comparison(comparison: ShadowComparisonLog) -> None`

### Telemetry Hooks
Introduces standard logging categories and event names:
- Logger: `app.shadow_executor`
- Audit actions: `shadow.execution.start`, `shadow.execution.complete`, `shadow.discrepancy.detected`
- Metric keys: `shadow_mismatch_rate`, `shadow_score_delta_mean`

---

## 6 Integration Analysis

- **AnalysisService**: Shadow Mode will supply comparative data to `AnalyticsService` to allow tracking strategy drift of the experimental logic over 5, 10, and 20 days.
- **Recommendation Pipeline**: Runs the production recommendation code first. If `shadow_mode_enabled` is `True`, it captures the inputs, constructs a `ShadowExecutionContext`, and passes it to the `IShadowExecutor`.
- **Backtest Pipeline**: Passes existing production backtest results into the shadow context, avoiding duplicate simulations.
- **Database**: No production tables are modified. Shadow data will be handled via the `IShadowStore` interface, executing in a separate async database session context.
- **Logging**: Comparative summaries (e.g., `[SHADOW COMPARE] RELIANCE-EQ | Prod: BUY (74.0) | Shadow: WATCH (70.5) | Match: False`) are directed to `app.shadow_executor`.
- **Telemetry**: Records deviations in labels (mismatch count) and scores (mean squared error) into the existing `ExperimentLog` for dashboard rendering.
- **Redis**: Future optimization can cache shadow state, but no Redis dependencies are introduced in Spec 1.
- **Scheduler**: Scheduled daily analysis runs will naturally execute the shadow flow alongside production runs.
- **SSE**: SSE data streaming is unaffected; shadow comparison results are omitted from the client response payloads.

---

## 7 Impact Analysis

- **API**: Zero public changes. Shadow comparison structures remain internal or optional in serialization schemas.
- **Database**: No table additions or migrations are run in this phase. Schema definitions are declarative and unmapped.
- **Models**: Production models are untouched.
- **Services**: Production scoring, strict buy gate, regime overlays, and sector overlays remain 100% identical.
- **Serialization**: Schema updates are additive and backward-compatible.
- **Redis**: No impact.
- **Scheduler**: No impact.
- **Observability**: Adds a new dedicated log stream `app.shadow_executor` and audit event routes.

---

## 8 Future Specification Readiness

This foundational specification prepares the system for subsequent phases:
- **Specification 2 (Shadow Executor)**: Will implement the concrete `IShadowExecutor` and route execution based on `shadow_mode_ruleset`.
- **Specification 3 (Persistence)**: Will define SQL tables for shadow logs and implement the concrete database `IShadowStore`.
- **Specification 4 (Telemetry)**: Will wire the comparative metrics into the real-time diagnostics dashboard and export utilities.
- **Specification 5 (Crash Isolation)**: Will wrap the executor in a non-blocking background task runner that guarantees shadow failures do not impact production pipeline execution times or cause API errors.
- **Specification 6 (Human Review Workflow)**: Will utilize comparative audit logs to generate review screeners for comparing live production and experimental outcomes.

---

## 9 Risks

- **Async & Thread Blocking**: Running CPU-bound experimental logic could block the FastAPI request cycle. *Mitigation:* The specification enforces that the future executor must wrap CPU-heavy logic in `asyncio.to_thread` or separate background tasks.
- **Database Lock Contention**: Writing shadow metrics in the same transaction block as production histories could cause deadlocks or write bottlenecks. *Mitigation:* Spec 1 mandates decoupling shadow store writes from production transaction boundaries.
- **Concurrency & Resource Exhaustion**: Running dual recommendation pipelines doubles API/LLM calls. *Mitigation:* Under Spec 1, the shadow executor has access only to pre-computed LLM inputs and does not trigger separate LLM prompts unless explicitly configured.
- **State Mutation Leakage**: Pass-by-reference sharing of candles or indicator objects could lead to the shadow pipeline mutating production recommendation inputs. *Mitigation:* The `ShadowExecutionContext` will enforce deep copying or read-only properties for its shared context elements.

---

## 10 Acceptance Criteria

### User Scenarios & Testing

#### User Story 1 - Configure Shadow Mode (Priority: P1)
As a systems operator, I want to be able to enable and configure Shadow Mode via settings so that the environment parameters are loaded correctly.
- **Why this priority**: Fundamental config needed before any shadow routing can be wired.
- **Independent Test**: boot the application and verify that settings load with correct defaults (`shadow_mode_enabled`=False, `shadow_mode_stage`="SHADOW").
- **Acceptance Scenarios**:
  1. **Given** no explicit configuration is defined in `.env`, **When** settings are initialized, **Then** shadow mode settings default to disabled with safe parameters.
  2. **Given** shadow mode settings are defined, **When** settings are loaded, **Then** validations pass successfully.

#### User Story 2 - Shadow Context Verification (Priority: P2)
As a developer, I want the system to prepare a read-only `ShadowExecutionContext` containing a snapshot of all inputs so that experimental logic can run deterministically on the same data.
- **Why this priority**: Ensures input parity and prevents data mutations.
- **Independent Test**: Instantiate `ShadowExecutionContext` and verify it contains deep copies of candles and technical results.
- **Acceptance Scenarios**:
  1. **Given** production recommendation has completed, **When** `ShadowExecutionContext` is built, **Then** all inputs match the production data snapshot exactly and cannot be mutated by downstream logic.

#### User Story 3 - Telemetry Verification (Priority: P3)
As a lead architect, I want to define comparison event types so that observability tools can detect discrepancies.
- **Why this priority**: Prepares comparison telemetry hooks.
- **Independent Test**: Verify audit action routes resolve correctly.
- **Acceptance Scenarios**:
  1. **Given** audit events list is queried, **When** checked, **Then** `shadow.*` events are registered.

---

### Requirements

#### Functional Requirements
- **FR-001**: System MUST support global `shadow_mode_enabled` configuration as a boolean with default `False`.
- **FR-002**: System MUST support `shadow_mode_stage` configuration as a string with default `"SHADOW"`.
- **FR-003**: System MUST support `shadow_mode_ruleset` configuration as a string with default `"experimental_v1"`.
- **FR-004**: System MUST support `shadow_mode_persistence_enabled` configuration as a boolean with default `False`.
- **FR-005**: System MUST NOT implement experimental rules, shadow scoring logic, DB table writes, or API response changes.
- **FR-006**: Existing recommendation scoring, transaction boundaries, and client-facing API endpoints MUST remain unaffected.
- **FR-007**: The `ShadowExecutionContext` MUST enforce read-only properties or deep copies of incoming data frames to prevent indicator mutation.

#### Key Entities
- **Shadow Execution Configuration**: The global parameters loaded from the environment to control shadow mode execution rules and stages.
- **Shadow Execution Context**: The DTO holding the immutable snapshot of symbol details, OHLCV candles, technical indicators, backtest results, and production recommendations.
- **Shadow Execution Result**: Schema representing the output of the shadow run (score, action, ruleset used, timing, details).
- **Shadow Comparison Log**: Schema representing the delta between production recommendations and shadow recommendations for auditing.

---

### Success Criteria

#### Measurable Outcomes
- **SC-001**: Shadow Mode settings validate successfully at startup under Pydantic.
- **SC-002**: 100% of existing unit and regression tests pass without modification.
- **SC-003**: Zero database tables or API schemas are altered, ensuring absolute backward compatibility.
- **SC-004**: Memory overhead of instantiating the execution context is negligible (< 1ms per symbol).
- **SC-005**: All registered shadow audit events (`shadow.*`) map to valid routes.

---

### Assumptions
- **A-001**: Shadow Mode runs within the context of daily swing trading scans and does not support real-time intraday trading ticks in Spec 1.
- **A-002**: LLM reasoning is not re-run for shadow mode; the shadow executor evaluates the pre-computed LLM analysis from the production flow.
- **A-003**: The database and Redis backends remain as configured in Sprint 1/2.
