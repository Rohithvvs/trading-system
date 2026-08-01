# Quickstart & Integration Validation Guide: Authoritative Candle Store (Sprint 4)

**Feature Branch**: `020-authoritative-candle-store`  
**Date**: 2026-07-27  
**Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/020-authoritative-candle-store/spec.md)  

---

## 1. Environment & Feature Flag Configuration

Set the environment variable in `.env` or system environment:

```env
# Disable Authoritative Candle Store (Legacy Fallback Mode)
AUTHORITATIVE_CANDLE_STORE_ENABLED=false

# Enable Authoritative Candle Store (Phase 1 Dual-Write / Phase 3 Preferred)
AUTHORITATIVE_CANDLE_STORE_ENABLED=true
CANDLE_STORE_DUAL_WRITE=true
CANDLE_STORE_ALLOW_FALLBACK=true
```

### Staged production enablement (recommended)

Default is **OFF** after merge. Enable only in this order:

1. **Staging dual-write** — `AUTHORITATIVE_CANDLE_STORE_ENABLED=true` + `CANDLE_STORE_DUAL_WRITE=true`; watch `candle_store_*` metrics and logs.
2. **Parity audit** — confirm reconciliation `authoritative_consistency_audit_completed` shows low mismatch/repair rates.
3. **Canary reads** — small traffic share with flag ON; compare latency and provider error rates.
4. **Full enable** — promote flag ON; keep `CANDLE_STORE_ALLOW_FALLBACK=true` during soak.
5. **Instant rollback** — set `AUTHORITATIVE_CANDLE_STORE_ENABLED=false` (env) without restart.

Canonical automated suite:

```bash
pytest backend/tests/test_authoritative_candle_store.py \
       backend/tests/test_l1_candle_cache.py \
       backend/tests/test_candle_gap_filler.py \
       backend/tests/test_candle_store_feature_flag.py \
       backend/tests/test_candle_store_*.py \
       backend/tests/integration/test_candle_store_*.py -q
```

---

## 2. Validation Scenarios

### Scenario 1: Legacy Routing Verification (`AUTHORITATIVE_CANDLE_STORE_ENABLED=false`)

1. Set `AUTHORITATIVE_CANDLE_STORE_ENABLED=false`.
2. Trigger full analysis endpoint:
   ```bash
   curl -X POST "http://localhost:8000/analysis/full" \
        -H "Content-Type: application/json" \
        -d '{"symbols": ["NSE:RELIANCE-EQ"], "mode": "swing"}'
   ```
3. Verify that response status is HTTP 200 and legacy fetch logging appears in logs.

---

### Scenario 2: Authoritative Candle Store Query (`AUTHORITATIVE_CANDLE_STORE_ENABLED=true`)

1. Set `AUTHORITATIVE_CANDLE_STORE_ENABLED=true`.
2. Run the **canonical** candle-store suite under `backend/tests/`:
   ```bash
   pytest backend/tests/test_authoritative_candle_store.py \
          backend/tests/integration/test_candle_store_unified.py -v
   ```
3. Confirm that L1 cache hits and PostgreSQL queries route through `AuthoritativeCandleStore` service.

---

### Scenario 3: Instant Rollback Validation

1. Start application with `AUTHORITATIVE_CANDLE_STORE_ENABLED=true`.
2. Execute a universe scan request via API or background task.
3. Dynamically set `AUTHORITATIVE_CANDLE_STORE_ENABLED=false`.
4. Submit immediate follow-up query and verify that system seamlessly reverts to legacy fetch path within $< 100\text{ms}$ with zero 500 errors.
