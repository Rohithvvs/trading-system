# Database Design

## 1. `users`
**Purpose**: Stores core identity.
- `id`: UUID (Primary Key)
- `email`: VARCHAR(255) (Unique, Indexed)
- `full_name`: VARCHAR(255)
- `password_hash`: VARCHAR(255) (Argon2id)
- `pin_hash`: VARCHAR(255) (Nullable, Argon2id)
- `is_active`: BOOLEAN (Default: True)
- `is_email_verified`: BOOLEAN (Default: False)
- `role`: VARCHAR(50) (Default: 'Trader')
- `created_at`: TIMESTAMP WITH TIME ZONE
- `updated_at`: TIMESTAMP WITH TIME ZONE
- `deleted_at`: TIMESTAMP WITH TIME ZONE (Nullable, Soft delete)

## 2. `user_sessions`
**Purpose**: Tracks active login sessions and refresh tokens.
- `id`: UUID (Primary Key)
- `user_id`: UUID (Foreign Key to `users.id`, Indexed)
- `device_id`: UUID (Foreign Key to `devices.id`, Nullable)
- `refresh_token_hash`: VARCHAR(255) (Hashed for security)
- `ip_address`: VARCHAR(45)
- `user_agent`: TEXT
- `is_active`: BOOLEAN (Default: True)
- `expires_at`: TIMESTAMP WITH TIME ZONE
- `created_at`: TIMESTAMP WITH TIME ZONE
- `last_active_at`: TIMESTAMP WITH TIME ZONE

## 3. `devices`
**Purpose**: Fingerprints physical devices/browsers for Biometric binding and trusted devices.
- `id`: UUID (Primary Key)
- `user_id`: UUID (Foreign Key to `users.id`, Indexed)
- `device_fingerprint`: VARCHAR(255) (Unique per user)
- `device_name`: VARCHAR(255) (e.g., 'iPhone 13', 'Chrome on Windows')
- `biometric_public_key`: TEXT (Nullable, WebAuthn)
- `is_trusted`: BOOLEAN
- `created_at`: TIMESTAMP WITH TIME ZONE
- `last_used_at`: TIMESTAMP WITH TIME ZONE

## 4. `audit_logs`
**Purpose**: Immutable log of security events.
- `id`: UUID (Primary Key)
- `user_id`: UUID (Foreign Key to `users.id`, Nullable, Indexed)
- `event_type`: VARCHAR(100) (e.g., 'LOGIN_SUCCESS', 'LOGIN_FAILED', 'PIN_CHANGED', 'SESSION_REVOKED')
- `ip_address`: VARCHAR(45)
- `user_agent`: TEXT
- `metadata`: JSONB (Stores specific details like changed fields or failures)
- `created_at`: TIMESTAMP WITH TIME ZONE (Indexed)

## 5. `otps`
**Purpose**: Temporarily stores OTPs for Email Verification, MFA, and Password Resets.
- `id`: UUID (Primary Key)
- `user_id`: UUID (Foreign Key to `users.id`, Indexed)
- `otp_hash`: VARCHAR(255)
- `purpose`: VARCHAR(50) (e.g., 'EMAIL_VERIFICATION', 'FORGOT_PASSWORD', 'LOGIN_MFA')
- `expires_at`: TIMESTAMP WITH TIME ZONE
- `is_used`: BOOLEAN (Default: False)
- `created_at`: TIMESTAMP WITH TIME ZONE

## Relationships
- `users` (1) to (N) `user_sessions`
- `users` (1) to (N) `devices`
- `users` (1) to (N) `audit_logs`
- `users` (1) to (N) `otps`

## Indexes
- `idx_users_email`
- `idx_sessions_user_id`
- `idx_devices_user_id`
- `idx_audit_logs_created_at`
- `idx_otps_user_purpose`
