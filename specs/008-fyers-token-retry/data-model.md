# Data Model: Sprint 3 – Retry Logic in Token Generation

**Feature**: [spec.md](file:///D:/Work_Space/trading-system/specs/008-fyers-token-retry/spec.md)
**Created**: 2026-07-20

---

## Transient Execution State: RetryState

Holds the local context tracking execution attempts and delay scheduling inside the `generate_fyers_access_token()` function.

| Field Name | Type | Description | State Transitions |
|------------|------|-------------|-------------------|
| `attempt` | `int` | Current execution attempt number (1-based). | Initialized to `1`. Increments by `1` upon catch of a transient error. Max value `3`. |
| `delay` | `float` | Uniform random delay value computed in seconds. | Computed before sleep: `random.uniform(5.0, 10.0)`. |
| `last_error` | `Exception` | Stores the most recent caught exception. | Updated on each failed attempt. Raised if `attempt` reaches `3`. |
