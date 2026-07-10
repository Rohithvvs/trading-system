# Testing Strategy

## Target: >90% Authentication Coverage

### 1. Unit Tests (Backend)
- **Security Utilities**: Mock hashing algorithms to ensure Argon2id parameters are correctly applied. Test JWT generation and signature verification.
- **Service Layer**: Test `auth_service.py` functions isolated from the database using mocks to ensure logic (e.g., checking password rules, generating OTPs) is sound.
- **Redis Blocklist**: Test that tokens added to the blocklist correctly return `True` for `is_revoked()`.

### 2. Integration Tests (Backend API)
- Use FastAPI `TestClient`.
- **Signup Flow**: Send valid payload -> verify DB insertion -> verify OTP generated.
- **Login Flow**: Send valid credentials -> receive JWT. Send invalid credentials -> receive 401.
- **Rate Limiting**: Hit the login endpoint 6 times with bad credentials -> verify 423 Locked on the 6th attempt.
- **Protected Routes**: Attempt to access a trading API without a token (401), with an expired token (401), and with a revoked token (401).

### 3. UI Tests (Frontend)
- **Component Tests**: Use React Testing Library to render `AuthInput` and `PasswordInput`. Verify toggle visibility works.
- **Form Validation**: Type invalid passwords and verify real-time UI updates (e.g., "Must contain an uppercase letter" turns red).

### 4. End-to-End Tests (Playwright)
- **Full Journey**: Open `/signup`, fill form, intercept network to mock OTP email, submit OTP, set PIN, and land on Dashboard.
- **Logout Flow**: Click logout, verify redirect to `/login`, press "Back" in browser, and verify Dashboard is inaccessible.

### 5. Security Tests
- **Brute Force**: Script to attempt 100 logins a second; ensure rate limiter kicks in.
- **Token Tampering**: Alter the JWT payload on the client and submit; verify the signature check fails.
