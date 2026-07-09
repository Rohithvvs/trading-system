# Phase 0: Research & Architecture Decisions

## 1. Password Hashing Algorithm
- **Decision:** Argon2id
- **Rationale:** As clarified in the feature spec, Argon2id is the modern standard for password hashing, offering memory-hard protection against GPU brute force attacks.
- **Alternatives considered:** bcrypt (legacy standard, not memory-hard), PBKDF2.

## 2. JWT Session Revocation Strategy
- **Decision:** Redis Blocklist for Access Tokens
- **Rationale:** To meet the <1 second revocation requirement while maintaining stateless API validation (via JWT signature), we will maintain a fast, in-memory blocklist in Redis for revoked JWTs before their natural 24h expiry.
- **Alternatives considered:** Short-lived tokens (5 mins) requiring frequent refreshes (rejected for UX/trading performance constraints), Database-backed token validation (too slow).

## 3. Rate Limiting and Account Lockout
- **Decision:** Redis-backed rate limiting and temporary 15-minute lockout after 5 consecutive failed login attempts.
- **Rationale:** Provides strong protection against brute force and credential stuffing while remaining user-friendly with a reasonable timeout.
- **Alternatives considered:** Permanent lockout (high support burden), CAPTCHA (disrupts smooth trading UX).

## 4. Authentication Middleware
- **Decision:** FastAPI `Depends` with `HTTPBearer` for standard JWT extraction, backed by a custom `get_current_user` dependency that checks the Redis blocklist and extracts roles.
- **Rationale:** Standard FastAPI pattern that integrates perfectly with Swagger UI and clean architecture.

## 5. Security Packages
- **Decision:** Add `PyJWT` for token generation, `argon2-cffi` for hashing, and `passlib` for legacy hashing facade if needed.
- **Rationale:** Industry standard python packages for these specific security tasks.
