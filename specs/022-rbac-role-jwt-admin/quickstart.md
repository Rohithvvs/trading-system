# Quickstart Validation Guide: Sprint 1 – Role Normalization + JWT + Default Admin

This document defines the validation commands and verification scenarios used to verify Sprint 1 implementation.

## Prerequisites
* Database service running and accessible.
* Backend server process initialized.
* Command line HTTP client (e.g. `curl`) or test suite runner available.

---

## Validation Scenario 1: Verification of Automated Default Admin Creation

### Action
1. Ensure database has 0 user records or execute application startup on clean environment.
2. Boot backend server process.

### Verification
Execute login attempt with default admin credentials:
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "Admin@123"}'
```

### Expected Outcome
* HTTP Status: `200 OK`
* Response JSON contains `"role": "admin"`.

---

## Validation Scenario 2: Privilege Escalation Prevention on Registration

### Action
Submit registration request attempting to self-assign administrative role:
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "attacker@example.com", "password": "Password123!", "full_name": "Attacker", "role": "admin"}'
```

### Verification
Check returned registration payload and perform `/auth/me` call with returned token.

### Expected Outcome
* HTTP Status: `200 OK` or `201 Created`
* Response JSON contains `"role": "trader"` (client-supplied `"role": "admin"` was stripped/ignored).

---

## Validation Scenario 3: JWT Role Claim Verification

### Action
Decode base64 payload of issued access token from login or registration.

```bash
# Extract payload from JWT (second segment)
echo "<access_token>" | cut -d'.' -f2 | base64 --decode
```

### Expected Outcome
* Decoded JSON payload contains `"sub"`, `"exp"`, and `"role"`.
* Value of `"role"` is `"trader"` or `"admin"`.

---

## Validation Scenario 4: Database Check Constraint Enforcement

### Action
Attempt raw database insert with invalid role value (e.g. `'superuser'`).

### Expected Outcome
* Database rejects transaction with SQL Check Constraint violation error (`CHECK constraint failed: role IN ('trader', 'admin')`).
