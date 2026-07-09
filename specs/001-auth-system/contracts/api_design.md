# API Design Contracts

All endpoints are prefixed with `/api/v1/auth`.

## 1. POST `/signup`
- **Auth Required**: No
- **Request Body**: `email`, `password`, `full_name`
- **Response (201)**: `{"message": "Verification email sent", "user_id": "uuid"}`
- **Errors**: `400 Bad Request` (Validation), `409 Conflict` (Email exists).

## 2. POST `/verify-email`
- **Auth Required**: No
- **Request Body**: `email`, `otp`
- **Response (200)**: `{"message": "Email verified successfully"}`
- **Errors**: `400 Bad Request` (Invalid or expired OTP).

## 3. POST `/pin/setup`
- **Auth Required**: Yes (Access Token required after signup/login)
- **Request Body**: `pin`
- **Response (201)**: `{"message": "PIN setup successfully"}`
- **Errors**: `400 Bad Request` (Invalid PIN rules).

## 4. POST `/login`
- **Auth Required**: No
- **Request Body**: `email`, `password`, `device_info`
- **Response (200)**: `{"message": "Login successful", "requires_mfa": false}` with `Set-Cookie: access_token=jwt; HttpOnly; SameSite=Strict; Secure` and `Set-Cookie: refresh_token=token; HttpOnly; SameSite=Strict; Secure` or `{"requires_mfa": true, "session_id": "temp_id"}`
- **Errors**: `401 Unauthorized` (Invalid credentials), `423 Locked` (Account temporarily locked).

## 5. POST `/login/mfa`
- **Auth Required**: No
- **Request Body**: `session_id`, `otp`
- **Response (200)**: `{"message": "Login successful"}` with `Set-Cookie: access_token=jwt; HttpOnly` and `Set-Cookie: refresh_token=token; HttpOnly`

## 6. POST `/biometric/register`
- **Auth Required**: Yes
- **Request Body**: `device_name`, `webauthn_attestation`
- **Response (201)**: `{"message": "Biometric device registered"}`

## 7. POST `/login/biometric`
- **Auth Required**: No
- **Request Body**: `device_fingerprint`, `webauthn_assertion`
- **Response (200)**: `{"message": "Login successful"}` with `Set-Cookie: access_token=jwt; HttpOnly` and `Set-Cookie: refresh_token=token; HttpOnly`

## 8. POST `/refresh`
- **Auth Required**: No (Requires valid refresh token in HttpOnly Cookie)
- **Request Body**: None (Uses Cookie)
- **Response (200)**: `{"message": "Tokens refreshed"}` with new `Set-Cookie` headers

## 9. POST `/logout`
- **Auth Required**: Yes
- **Response (200)**: `{"message": "Logged out successfully"}` with cleared `Set-Cookie` headers
- **Action**: Adds access_token to Redis blocklist, invalidates refresh token.

## 9. GET `/sessions`
- **Auth Required**: Yes
- **Response (200)**: `[{"session_id": "uuid", "device": "iPhone", "ip": "...", "current": true}]`

## 10. DELETE `/sessions/{session_id}`
- **Auth Required**: Yes
- **Response (200)**: `{"message": "Session revoked"}`
- **Action**: Pushes associated access token to Redis blocklist.

## 11. POST `/forgot-password`
- **Auth Required**: No
- **Request Body**: `email`
- **Response (200)**: `{"message": "OTP sent if email exists"}`

## 12. POST `/reset-password`
- **Auth Required**: No
- **Request Body**: `email`, `otp`, `new_password`
- **Response (200)**: `{"message": "Password reset successfully"}`
