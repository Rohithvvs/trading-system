# Implementation Plan: Sprint 3 – Retry Logic in Token Generation

**Branch**: `008-fyers-token-retry` | **Date**: 2026-07-20 | **Spec**: [spec.md](file:///D:/Work_Space/trading-system/specs/008-fyers-token-retry/spec.md)
**Input**: Feature specification from `/specs/008-fyers-token-retry/spec.md`

---

## ## Summary / Overview

This plan defines the update to the existing `generate_fyers_access_token()` function in `fyers_token.py` to support automatic retries. When a transient connection or server failure occurs during any phase of login, the function will log a warning, calculate a randomized delay between 5.0 and 10.0 seconds, wait, and retry the sequence up to a maximum of 3 attempts. Permanent failures (config/missing keys/bad PIN) will fail fast immediately without any delay or retry.

---

## ## Technical Context

- **Language/Version**: Python 3.11  
- **Primary Dependencies**: `requests` (v2.31.0+), `pyotp` (v2.9.0+), `fyers-apiv3` (v3.1.12+)  
- **Storage**: N/A  
- **Testing**: `pytest`  
- **Target Platform**: Windows / Linux server  
- **Project Type**: Library / CLI  
- **Performance Goals**: Immediate exit on success (< 5s), backoff sleep of 5-10s between retries, total persistent failure exit within 35 seconds.
- **Constraints**: No change to function signature; maximum of 3 attempts; delay randomized between 5.0 and 10.0 seconds; no browser automation.

---

## ## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status | Verification Method / Notes |
|-----------|-------|--------|-----------------------------|
| **I. Library-First** | Standalone module? | **PASS** | Modifies existing standalone module `fyers_token.py`. |
| **II. CLI Interface** | Direct execution supported? | **PASS** | Keeps existing `__main__` CLI block intact. |
| **III. Test-First** | Unit & integration tests defined? | **PASS** | Retry test cases are written in `tests/test_fyers_token.py` before modifying logic. |
| **IV. Integration Testing** | End-to-end integration scenario? | **PASS** | `quickstart.md` details how to run the E2E verification scenario. |
| **V. Observability** | Proper logging and error levels? | **PASS** | Logs failures as WARNING and retries as INFO, matching Q2 choice. |

---

## ## Project Structure

### Documentation
```text
specs/008-fyers-token-retry/
├── spec.md              # Feature Specification (with clarified requirements)
├── plan.md              # This Implementation Plan
├── research.md          # Phase 0 Research Notes (technique comparison)
├── data-model.md        # Phase 1 Data Model (retry state schema)
├── quickstart.md        # Phase 1 Quickstart Validation Guide
└── contracts/
    └── api_contracts.md # Interface Contracts (function and CLI contract)
```

### Source Code
Modifies existing files in place:
```text
D:/Work_Space/trading-system/
├── fyers_token.py       # Update generate_fyers_access_token() with retry loop
└── tests/
    └── test_fyers_token.py # Add retry tests
```

**Structure Decision**: Preserves Single project (root level) structure.

---

## ## Current State & Changes Required

### 1. Current State (Sprint 2)
The function currently executes sequentially:
1. `load_fyers_config()` -> throws `FyersConfigError` if variables are missing.
2. Step 1 (OTP Request) -> calls `send_login_otp_v2`. Throws `FyersConnectionError`/`FyersAuthError` on failure.
3. Step 2 (OTP Verification) -> calls `verify_otp` with single timing window retry.
4. Step 3 (PIN Verification) -> calls `verify_pin_v2`.
5. Step 4 (Auth Code Extraction) -> calls `/generate-authcode`.
6. Step 5 (Exchange) -> exchanges auth code via SDK SessionModel.

### 2. Changes Required
We will wrap the entire token generation sequence (Steps 1 to 5) inside a loop:
```python
for attempt in range(1, 4):
    try:
        # Load config and run login steps 1-5...
        return final_access_token
    except (FyersConnectionError, FyersAuthError) as e:
        # If this is a transient exception and attempt < 3:
        #   Log warning, calculate delay, sleep, and loop again.
        # Otherwise raise the exception.
```

---

## ## Detailed Design & Retry Strategy

### 1. Recommended Retry Approach (Simple Loop)
We will use a standard `for` loop:
- **Clean and readable**: No decorator libraries required.
- **Fail-fast alignment**: We can catch specific exceptions (`FyersConnectionError`, transient `FyersAuthError` from server statuses) while letting configuration issues (`FyersConfigError`) flow out immediately.
- **Randomized Jitter**: Uses `random.uniform(5.0, 10.0)` for delays.

### 2. Updated Function Logic Flow
```text
1. Load config (fail-fast on FyersConfigError).
2. For attempt = 1 to 3:
   a. Start try-except block.
   b. Generate TOTP code.
   c. Call OTP request, OTP verify, PIN verify, Auth code, SDK exchange.
   d. If successful: Return token immediately.
   e. If caught FyersConnectionError or transient FyersAuthError:
      - If attempt == 3: raise the last error.
      - Else:
        - Log WARNING: "Attempt [attempt]/3 failed: [error]."
        - Compute delay = random.uniform(5.0, 10.0)
        - Log INFO: "Retrying in [delay] seconds..."
        - sleep(delay)
```

### 3. Error Handling Strategy
- Catch `requests.RequestException` inside loop -> raise `FyersConnectionError`.
- Catch API statuses (e.g. `s != 'ok'`) inside loop -> raise `FyersAuthError`.
- If an exception occurs, check if it's transient:
  - Any `FyersConnectionError` is transient.
  - `FyersAuthError` is transient only if it's a remote API server-side issue (e.g. status code 500, gateway timeout) or rate limit. If it's a permanent credential issue (like invalid PIN), raise immediately without retrying.

---

## ## Step-by-Step Implementation Plan

### Task 1: Add Retry Tests (TDD)
- Open `tests/test_fyers_token.py`.
- Add tests mock-simulating failed attempts 1 and 2, succeeding on 3. Verify logging warning/info messages.
- Add tests mock-simulating failures on all 3 attempts. Verify exception is raised and sleep times are respected.

### Task 2: Refactor `generate_fyers_access_token` in `fyers_token.py`
- Import `random`.
- Move environment validation `load_fyers_config()` *outside* the retry loop (fail-fast).
- Wrap Steps 1 to 5 in a `for attempt in range(1, 4):` loop.
- Track attempt index.
- On exception, log warning, sleep for `random.uniform(5.0, 10.0)` seconds, and continue. Raise on the 3rd attempt.

### Task 3: Verify & Validate
- Run `pytest tests/test_fyers_token.py`.
- Test CLI directly.

---

## ## Testing Strategy

### 1. Mocked Unit Tests
Mock requests to return:
- Successive failures (Connection Error/503 Service Unavailable) then success.
- 3 successive failures.
Assert:
- Loop executes exactly the expected number of times.
- `time.sleep` called with random float within 5.0 to 10.0 range.
- Correct exception raised on 3rd failure.

---

## ## Definition of Done

- [ ] `generate_fyers_access_token()` retries up to 3 times on transient errors.
- [ ] Random delay between 5.0 and 10.0 seconds is introduced between retries.
- [ ] Permanent errors (config errors / bad PIN) fail fast immediately.
- [ ] Logging conforms to WARNING (on failure) and INFO (on retry delay).
- [ ] Unit tests pass successfully.
