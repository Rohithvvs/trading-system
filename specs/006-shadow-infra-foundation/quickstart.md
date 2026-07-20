# Quickstart Validation Guide: Shadow Infrastructure Foundation

**Feature Branch**: `006-shadow-infra-foundation` | **Date**: 2026-07-20  
**Feature**: [spec.md](./spec.md)

---

## 1. Setup and Environment Configuration

To configure the shadow infrastructure foundation settings in the development environment:

1. Open the `.env` file in the project root.
2. Add the following shadow mode variables:
   ```env
   SHADOW_MODE_ENABLED=True
   SHADOW_MODE_STAGE=SHADOW
   SHADOW_MODE_RULESET=experimental_v1
   SHADOW_MODE_PERSISTENCE_ENABLED=False
   ```

---

## 2. Validation Scenario 1: Configuration Validation

Validate that the configurations load correctly at startup:

1. Start the FastAPI backend service:
   ```powershell
   ./start_backend.ps1
   ```
2. Verify that the project boots without any Pydantic settings schema errors.
3. Access the health check endpoint to verify base service health:
   ```powershell
   Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
   ```

---

## 3. Validation Scenario 2: Isolated Hook Validation

Since Spec 1 introduces the context and interface hooks without concrete rulesets or database tables, we validate that the orchestrator executes the isolated trigger block without regressions:

1. Trigger a full preset screener scan via the API:
   ```powershell
   Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/analysis/screener/full" -Body '{"preset":"nifty500","top_n":5}' -Headers @{"Content-Type"="application/json"}
   ```
2. Open the logs:
   ```powershell
   Get-Content -Path "./backend/logs/app.log" -Tail 100
   ```
3. Verify that the logs print successful execution:
   - Check that production recommendations run exactly as before (100% parity).
   - Verify that there are no shadow-mode-related exceptions or crashes.
   - Verify that the warning log appears indicating that the shadow executor/ruleset is not registered (proving that the hook runs inside `OrchestratorAgent._analyze_symbol_post_bulk` and degrades gracefully):
     ```text
     [WARNING] app.shadow_executor: Shadow executor is enabled but no ruleset executor is registered for ruleset 'experimental_v1'. Gracefully skipping.
     ```
