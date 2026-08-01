# Quickstart Validation Guide: Sprint 3 – Retry Logic in Token Generation

**Feature**: [spec.md](file:///D:/Work_Space/trading-system/specs/008-fyers-token-retry/spec.md)
**Created**: 2026-07-20

This guide documents the validation scenarios to verify the automated retry logic and delay backoff.

---

## Validation Scenario 1: Verify Retries on Transient Connection Failures

### Execution Steps
Run the test suite specifically targeting retry success scenarios:

```bash
pytest tests/test_fyers_token.py -k "test_generate_fyers_access_token_retry"
```

### Expected Outcome
- The logs output `WARNING` entries detailing attempt failures.
- The logs output `INFO` entries indicating scheduled retries with sleep times between 5.0 and 10.0 seconds.
- The test returns success when a retry attempt succeeds.

---

## Validation Scenario 2: Verify Fail-Fast on Permanent Config Errors

### Execution Steps
Unset the `FYERS_PIN` environment variable and run the CLI script:

```powershell
$env:FYERS_PIN=""
python fyers_token.py
```

### Expected Outcome
- The command exits immediately with code `1`.
- The execution time is near-instant (< 100ms) with zero retry delay.
- The output in `stderr` reports a `FyersConfigError`.

---

## Consumer notes (merge-ready)

### Correct imports
```python
# Token generator (this feature)
from fyers_token import generate_fyers_access_token, FyersConnectionError, FyersAuthError

# ORM model (different module — persistence)
from backend.app.models.fyers_token import FyersToken
```

### Handling exhausted retries
```python
try:
    token = generate_fyers_access_token()
except FyersConnectionError as e:
    # Prefer type catches; original step error is e.__cause__
    # Message format: "<original> [after N attempts; maximum retries exhausted]"
    attempts = getattr(e, "attempts", None)
    raise
```

### Out of scope for Sprint 3
Persisting the token to `fyers_tokens` and scheduling daily runs are **downstream** steps. Example manual flow:

```python
token = generate_fyers_access_token()
# then: POST /api/token/save-access-token  or  token_service.save_access_token(...)
```

---

## Full suite

```bash
pytest tests/test_fyers_token.py -v
```
