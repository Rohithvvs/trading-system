# AUDIT TASK

Audit the implementation deeply like a senior production engineer.

---

# VERIFY

## Architecture
- consistency
- clean layering
- dependency correctness
- duplicate abstractions

## Backend
- async correctness
- race conditions
- transaction safety
- retry safety
- timeout handling
- memory leaks

## Trading Safety
- duplicate order risk
- stale state risk
- websocket duplication
- partial execution risk

## Frontend
- stale UI state
- re-render issues
- cleanup handling
- async cancellation

## Database
- missing indexes
- query inefficiencies
- locking issues
- migration risks

## Observability
- missing logs
- missing metrics
- missing tracing
- missing correlation IDs

## Testing
- missing edge-case tests
- missing failure-path tests
- missing concurrency tests

---

# OUTPUT FORMAT

1. Critical Issues
2. High Risk Issues
3. Medium Risk Issues
4. Performance Risks
5. Security Risks
6. Missing Tests
7. Recommended Fixes
8. Production Readiness Score