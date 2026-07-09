# Quickstart Validation Guide

This guide details how to validate the core flows of the Authentication System once implemented.

## Prerequisites
- Redis server running on `localhost:6379`.
- PostgreSQL database running and migrations applied.
- Backend FastAPI server running on `http://localhost:8000`.
- Frontend Vite server running on `http://localhost:5173`.

## 1. Validating User Registration and PIN Setup

1. Open the UI at `http://localhost:5173/signup`.
2. Enter an email and a strong password (e.g., `Test!1234abcd`).
3. Click **Sign Up**.
4. Check the backend logs for the OTP email payload.
5. Enter the OTP in the `/verify-email` UI page.
6. Enter a secure 4-digit PIN (e.g., `8251`).
7. **Expected Outcome**: Account is created, email verified, PIN is saved, and you are logged in.

## 2. Validating Account Lockout (Brute Force Protection)

1. Open `http://localhost:5173/login`.
2. Enter a valid email but incorrect password 5 times in a row.
3. On the 6th attempt, enter the *correct* password.
4. **Expected Outcome**: The 6th attempt should return a `423 Locked` error indicating the account is temporarily locked for 15 minutes.

## 3. Validating Immediate Session Revocation

1. Login successfully using your credentials on Browser A. Save the Access Token.
2. Login successfully using your credentials on Browser B.
3. In Browser B, navigate to the Active Sessions page (`/settings/sessions`).
4. Click "Revoke" on the session corresponding to Browser A.
5. In Browser A, attempt to access a protected route (e.g., `/api/v1/trading/portfolio`).
6. **Expected Outcome**: The request from Browser A fails immediately with a `401 Unauthorized` response due to the Redis blocklist, even though the token hasn't technically expired yet.
