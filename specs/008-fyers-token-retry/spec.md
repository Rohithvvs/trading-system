# Feature Specification: Sprint 3 – Retry Logic in Token Generation

**Feature Branch**: `008-fyers-token-retry`  
**Created**: 2026-07-20  
**Status**: Draft  
**Input**: User description: "Generate a detailed technical specification for Sprint 3 of the Fyers Access Token Automation project..."

---

## Overview

We are enhancing the Fyers automated login token generation utility to make it resilient against temporary failures (such as intermittent network connectivity issues, API timeouts, or temporary third-party API rate limits). This sprint adds automated retry logic with configurable delays to the existing token generation process. If any transient error occurs during the login steps, the process will retry up to a maximum of 3 attempts before raising a final exception.

---

## Clarifications

### Session 2026-07-20
- Q: What exact pattern should be used to determine the delay duration between attempts? → A: Randomized delay (uniform random between 5.0 and 10.0 seconds using jitter).
- Q: How should the system log and report intermediate failed attempts before a retry is triggered? → A: Log failures as WARNING and retry actions as INFO.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automated Retry on Temporary Failures (Priority: P1)

If the token generation encounters a transient failure (e.g. temporary network drop, rate limit, or server-side error), the system should automatically attempt to regenerate the token on a subsequent try.

**Why this priority**: Intermittent failures in API endpoints should not cause the daily token generation background job to fail immediately. Retrying automatically ensures that self-correcting errors do not block access to trading APIs.

**Independent Test**:
Can be fully tested by simulating transient network errors on the first two login API requests, and verifying that the final access token is still successfully returned on the third attempt.

**Acceptance Scenarios**:
1. **Given** the remote API server returns transient failures for the first two attempts, **When** token generation is invoked, **Then** it automatically performs a retry and successfully returns the access token on the third attempt.
2. **Given** all three attempts fail due to transient errors, **When** token generation is invoked, **Then** it raises a clear authentication exception after the third failure.
3. **Given** the first attempt succeeds, **When** token generation is invoked, **Then** it returns the access token immediately without triggering any retries.

---

### User Story 2 - Delay / Backoff Between Retries (Priority: P2)

When an attempt fails, the system must wait a short duration before trying again, giving the remote service or network connection time to recover.

**Why this priority**: Immediate retries on a failing remote service often fail again instantly or worsen rate-limiting conditions. A delay gives transient issues time to resolve.

**Independent Test**:
Measure the elapsed time between failed attempts during execution, asserting that it stays within the required range.

**Acceptance Scenarios**:
1. **Given** an attempt fails, **When** the next retry is scheduled, **Then** the system waits for a randomized delay between 5.0 and 10.0 seconds before starting the next attempt.

---

### Edge Cases

- **Permanent Failures**: What happens when a permanent error is encountered (e.g., invalid PIN, missing config, incorrect credentials)?
  - *Behavior*: The system MUST NOT retry. It should fail fast and raise the corresponding exception immediately. Only transient/temporary errors (such as connection timeouts or remote server-side errors) should trigger retries.
- **Timing and TOTP Windows**: How does the delay interact with the 30-second TOTP validity window?
  - *Behavior*: Since a retry waits between 5 to 10 seconds, the subsequent retry must compute a fresh TOTP code at the moment of the request rather than reusing the previous attempt's code.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST automatically retry the token generation process on transient failures.
- **FR-002**: The maximum number of attempts allowed is 3 (initial attempt + up to 2 retries).
- **FR-003**: The system MUST introduce a randomized delay (uniform random between 5.0 and 10.0 seconds) between failed attempts.
- **FR-004**: If any attempt succeeds, the system MUST immediately return the access token and skip any remaining retries.
- **FR-005**: If all 3 attempts fail, the system MUST raise a clear exception indicating that authentication failed after the maximum number of attempts.
- **FR-006**: The system MUST NOT retry on configuration errors (e.g., missing environment variables) or permanent authentication errors (e.g., invalid PIN, bad app credentials).
- **FR-007**: The system MUST generate a fresh 2FA code (TOTP) for each attempt.
- **FR-008**: The system MUST log failed attempts at the WARNING level (detailing the attempt number and failure reason) and log scheduled retry actions at the INFO level.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A transiently failing connection succeeds on retry without manual intervention in 100% of cases where the underlying problem clears within 20 seconds.
- **SC-002**: Delay between retries is verified to be random and strictly between 5.0 and 10.0 seconds.
- **SC-003**: In case of persistent failure, the process raises an exception and exits in less than 35 seconds (3 attempts with up to 10 seconds of delay each).
- **SC-004**: Running the utility with correct parameters and no network issues incurs zero retry delay.

---

## Assumptions

- Transient failures are defined as connection errors, request timeouts, and server-side errors (HTTP 5xx).
- The target API endpoints continue to support pure API/TOTP login.
- Credentials validation is handled correctly, allowing the identification of permanent credential failures.
