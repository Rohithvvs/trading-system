# Security Design

## Core Strategy
- **Password Hashing**: Argon2id is the primary standard. It resists GPU brute-forcing via memory-hardness.
- **PIN Hashing**: Argon2id (with lower memory parameters if needed for speed, given the limited entropy of a 4-digit PIN, but paired with aggressive rate limiting).
- **JWT Strategy**: Stateless JWT Access Tokens with a 24-hour expiration. Short enough to mitigate extreme exposure, long enough to avoid constant interruptions.
- **Session Revocation**: A Redis blocklist will track revoked JWTs. Every protected request checks Redis (O(1) fast lookup) to see if the token is revoked before its 24h natural expiration.

## Attack Mitigation
- **Brute Force & Credential Stuffing**: 
  - Redis-backed rate limiter on `/login`, `/verify-email`, `/pin/setup`.
  - Temporary 15-minute account lockout after 5 consecutive failed login attempts.
- **Cross-Site Request Forgery (CSRF) & XSS**: 
  - JWT Access Tokens handled securely. If using cookies, they MUST be `HttpOnly`, `Secure`, and `SameSite=Strict`.
- **User Enumeration**:
  - Generic error messages: E.g., `/login` returns "Invalid credentials", never "User not found".
  - `/forgot-password` returns "If an account exists, an email has been sent."
- **Token Replay**: JWTs are cryptographically signed.

## Audit Logging
- Every critical security action (Login, Logout, PIN Change, Password Change, Failed Login) writes an immutable record to the `audit_logs` table.

## Device Binding
- On login, a `device_fingerprint` is tied to the `user_sessions`. A stolen JWT used from a different IP/User-Agent may trigger a suspicious activity flag or require step-up MFA.
