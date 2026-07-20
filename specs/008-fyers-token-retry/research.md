# Research Notes: Sprint 3 – Retry Logic in Token Generation

**Feature**: [spec.md](file:///D:/Work_Space/trading-system/specs/008-fyers-token-retry/spec.md)
**Created**: 2026-07-20

---

## 1. Technical Decisions

### Decision 1: Retry Control Flow Structure
- **Choice**: A simple `for` loop with `try-except` blocks.
- **Rationale**:
  - Requires no additional third-party dependencies (keeps `requirements.txt` lightweight).
  - Allows fine-grained control over which specific exceptions are retried (transient) versus which exceptions fail fast (permanent config/auth issues).
  - Keeps code highly legible and maintains the existing function signature without decorators.
- **Alternatives Considered**:
  - `tenacity` library: Decorator-based retrying. Rejected because importing a third-party framework for a simple 3-attempt loop is over-engineering.
  - Recursion: Re-calling the function on failure. Rejected to avoid stack depth expansion and keep state/attempt counters simple.

### Decision 2: Randomized Jitter Delay
- **Choice**: Python's standard `random.uniform(5.0, 10.0)` paired with `time.sleep()`.
- **Rationale**:
  - Uniform random distribution provides the exact required delay range (5 to 10 seconds).
  - Standard library module (`random`) is built-in.
- **Alternatives Considered**:
  - Fixed 5s or 10s sleep: Fails to distribute requests dynamically if multiple automation scripts trigger concurrently.

---

## 2. Classification of Errors

To satisfy **FR-006** (fail-fast on permanent errors), exception types are handled as:

| Exception Class / Condition | Error Category | Action on Failure |
|-----------------------------|----------------|-------------------|
| `FyersConfigError` | Permanent | Fail-fast (Raise immediately) |
| `FyersAuthError` (Bad Credentials/PIN/App ID) | Permanent | Fail-fast (Raise immediately) |
| `FyersConnectionError` (Timeout/Network) | Transient | Sleep and Retry |
| `FyersAuthError` (Remote 500/Gateway Timeout) | Transient | Sleep and Retry |
