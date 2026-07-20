# Implementation Plan: Shadow Infrastructure Foundation

**Branch**: `006-shadow-infra-foundation` | **Date**: 2026-07-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-shadow-infra-foundation/spec.md`

---

## Executive Summary

The objective of FEAT-011 Specification 1 is to establish the architectural and configuration foundation for the Shadow Infrastructure. This setup enables executing experimental recommendation logic on the same NSE/BSE Swing Trading market snapshots without impacting production behaviors. Spec 1 focuses on introducing settings configurations, execution context DTOs, executor/store interface contracts, and non-disruptive orchestrator hooks.

---

## Architecture Assessment

The backend is an async-first FastAPI service connecting to PostgreSQL via Async SQLAlchemy. Running dual recommendation flows (production and shadow) could introduce blocking operations or database lock contentions if not isolated. 
To preserve the async-first architecture:
- Shadow execution will be hooked after production results are resolved.
- It will be isolated using standard try/except blocks to guarantee crashes do not propagate.
- Spec 1 will only construct contexts and interfaces, preparing the system for non-blocking execution in Spec 2.

---

## Existing Components to Reuse

- **Configuration mapping**: Pydantic settings pattern in `backend/app/config/settings.py` (similar to FEAT-004 and FEAT-007).
- **Core Orchestrator**: `OrchestratorAgent._analyze_symbol_post_bulk` in `backend/app/agents/orchestrator_agent.py` to trigger the shadow run context.
- **Loggers**: Python standard logger configuration in `backend/app/utils/logger.py`.
- **Database Base Class**: SQLAlchemy `Base` from `backend/app/db/base.py`.
- **Telemetry & Auditing**: `AuditTrailManager` from `backend/app/governance/audit.py`.

---

## Files to Modify

| File | Reason | Type of Change |
|---|---|---|
| `backend/app/config/settings.py` | Add shadow mode config properties (`shadow_mode_enabled`, `shadow_mode_stage`, etc.) and Pydantic validation. | Extension |
| `backend/app/schemas/analysis.py` | Define `ShadowExecutionContext`, `ShadowExecutionResult`, and `ShadowComparisonLog` schemas. | Extension |
| `backend/app/agents/orchestrator_agent.py` | Insert the shadow execution context setup and run hooks in `_analyze_symbol_post_bulk` inside an isolated try-except block. | Extension |

---

## New Components (if absolutely necessary)

We introduce purely abstract interfaces to define the shadow mode engine contracts:
- **`backend/app/services/shadow_executor_interface.py`**: Defines `IShadowExecutor` for executing experimental rulesets.
- **`backend/app/services/shadow_store_interface.py`**: Defines `IShadowStore` for saving comparison results.

---

## Dependency Graph

```text
  [settings.py]
        │
        ▼
  [schemas/analysis.py]
        │
        ├────────────────────────────┐
        ▼                            ▼
  [shadow_executor_interface.py]  [shadow_store_interface.py]
        │                            │
        ▼                            ▼
  [orchestrator_agent.py (hook / context setup)]
```

---

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, Async SQLAlchemy, Pydantic, PostgreSQL  
**Storage**: PostgreSQL (declarative base)  
**Testing**: pytest  
**Target Platform**: Linux server (Render/Vercel)  
**Project Type**: web-service  
**Performance Goals**: Context initialization < 1ms overhead per symbol.  
**Constraints**: Zero database read/write impact, zero client API mutations, zero network requests.  
**Scale/Scope**: Up to 25 symbols concurrent per screener scan.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I: Library-First** — PASSED. Context schemas and settings are housed in core schemas, and interfaces in services.
- **Principle III: Test-First** — PASSED. Core config models will be fully covered by unit tests.
- **Principle V: Observability** — PASSED. New logger `app.shadow_executor` and audit trails.

---

## Project Structure

```text
specs/006-shadow-infra-foundation/
├── spec.md              # Feature specification
├── plan.md              # This implementation plan
├── research.md          # Phase 0: Research findings
├── data-model.md        # Phase 1: Data schemas definition
└── quickstart.md        # Phase 1: Verification guide

backend/app/
├── config/
│   └── settings.py
├── schemas/
│   └── analysis.py
├── services/
│   ├── shadow_executor_interface.py
│   └── shadow_store_interface.py
└── agents/
    └── orchestrator_agent.py
```

**Structure Decision**: Reuses the standard single-project structure matching `backend/app/`.

---

## Implementation Phases

### Phase 0: Outline & Research
- **Objective**: Design clean Python contracts for the shadow executor and persistence stores that prevent blocking execution.
- **Scope**: Investigate async abstract base class (ABC) structures in Python and decoupling strategies.
- **Files**: `specs/006-shadow-infra-foundation/research.md` (to be generated).
- **Dependencies**: Approved specification.
- **Risks**: Overcomplicating interfaces. *Mitigation:* Focus only on a single `execute_shadow` async method.
- **Validation**: All unknowns resolved and stored in `research.md`.

### Phase 1: Design & Configuration
- **Objective**: Implement settings and schemas for shadow mode and verify startup configuration validation.
- **Scope**: Extend settings and define Pydantic DTO models.
- **Files**: 
  - `backend/app/config/settings.py`
  - `backend/app/schemas/analysis.py`
  - `specs/006-shadow-infra-foundation/data-model.md`
  - `specs/006-shadow-infra-foundation/quickstart.md`
- **Dependencies**: Phase 0.
- **Risks**: Pydantic boot failure. *Mitigation:* Ensure default value is `False` for settings.
- **Validation**: Project starts successfully; settings correctly load from `.env`.

### Phase 2: Interface Contracts & Hook Wiring
- **Objective**: Create `IShadowExecutor`/`IShadowStore` interfaces and wire the exception-isolated shadow execution hook into the orchestrator.
- **Scope**: Implement interface files and modify `orchestrator_agent.py`.
- **Files**:
  - `backend/app/services/shadow_executor_interface.py`
  - `backend/app/services/shadow_store_interface.py`
  - `backend/app/agents/orchestrator_agent.py`
- **Dependencies**: Phase 1.
- **Risks**: Shadow execution exceptions crashing production screener scans. *Mitigation:* Wrap orchestrator hook in a try/except block with robust error logging, preserving all production variables.
- **Validation**: Verification script executes and logs that shadow hook was evaluated without regressions.

---

## Database Impact

No SQL tables or migrations are introduced in Specification 1. The database interfaces are declarative and will be mapped in later specifications.

---

## API Impact

No public APIs are affected. All shadow variables and context logs remain internal to the server and are excluded from client response payloads.

---

## Configuration Impact

Exposes the following settings via `backend/app/config/settings.py` and `.env`:
- `shadow_mode_enabled`: (bool, default `False`)
- `shadow_mode_stage`: (str, default `"SHADOW"`)
- `shadow_mode_ruleset`: (str, default `"experimental_v1"`)
- `shadow_mode_persistence_enabled`: (bool, default `False`)

---

## Observability Impact

- Logger: `app.shadow_executor`
- Audit actions: `shadow.execution.start`, `shadow.execution.complete`, `shadow.discrepancy.detected`
- Telemetry metrics: `shadow_mismatch_rate`, `shadow_score_delta_mean`

---

## Testing Strategy

- **Unit Tests**:
  - Verify shadow mode configuration defaults and validation constraints.
  - Verify instantiation of `ShadowExecutionContext` and deep copy behavior.
- **Integration Tests**:
  - Verify that `OrchestratorAgent._analyze_symbol_post_bulk` invokes the shadow hook and runs to completion when shadow mode is enabled.
  - Verify exception-safety (e.g. if the shadow hook throws an error, the orchestrator continues successfully).

---

## Performance Considerations

- Context instantiation must not block the event loop or allocate significant memory.
- Copy only mutable DTO lists (like candles and technical indicator lists) rather than deep cloning large database model trees.

---

## Concurrency Considerations

- Shadow execution runs inside the same event loop context. Any future execution of experimental rulesets must be async-safe to prevent thread blocks.

---

## Failure Recovery Strategy

- **Crash Isolation**: The shadow execution hook is wrapped in a high-level try/except block. In case of failures (e.g., config error, schema parsing fail, interface missing), the exception is logged to `app.shadow_executor` and the execution continues normal production routing.

---

## Rollback Strategy

- Disable shadow execution instantly by setting `SHADOW_MODE_ENABLED=False` in the environment.
- Git checkout/reset of the branch.

---

## Risks

- **State Mutation Leak**: Mutable candle data passed to shadow execution could be altered. *Mitigation:* The context creates read-only views or deep copies of incoming data frames.
- **LLM Overhead**: Running additional LLM queries in shadow mode. *Mitigation:* Re-use pre-computed LLM findings from the production context.

---

## Complexity Tracking

No complexity tracking triggers needed (Constitution gates passed).

---

## Acceptance Criteria

- [ ] Startup settings load configuration flags correctly.
- [ ] `ShadowExecutionContext` correctly duplicates symbol snapshots.
- [ ] An exception inside shadow execution is caught and does not affect the production output.
- [ ] No API responses are modified.
- [ ] All existing test suites pass successfully.
