# Phase 1 Data Model: Sprint 1 – Role Normalization + JWT + Default Admin

## Entity Definitions

### 1. User Entity (`users` table)

#### Attributes
* `id` (String / Integer, Primary Key, Non-Null): Unique identifier for the user account.
* `email` (String, Unique, Non-Null): User's primary email address used for authentication.
* `password_hash` (String, Non-Null): One-way cryptographic hash of user's password.
* `full_name` (String, Non-Null): User's display name.
* `role` (String, Non-Null, Default: `'trader'`): User's administrative privilege level. Must satisfy `CHECK (role IN ('trader', 'admin'))`.
* `created_at` (Timestamp, Non-Null, Default: CURRENT_TIMESTAMP): Account creation timestamp.
* `updated_at` (Timestamp, Non-Null, Default: CURRENT_TIMESTAMP): Account modification timestamp.

#### Constraints
* **Primary Key**: `PRIMARY KEY (id)`
* **Unique Index**: `UNIQUE (email)`
* **Default Constraint**: `DEFAULT 'trader' FOR role`
* **Check Constraint**: `CHECK (role IN ('trader', 'admin'))`

---

## State & Value Domain Transitions

```
+-------------------------------------------------------------------+
|                         Role Domain Map                           |
+-------------------------------------------------------------------+
| Input Casing / Legacy Value          | Normalized Database Value  |
+--------------------------------------+----------------------------+
| 'trader', 'Trader', 'TRADER'         | 'trader'                   |
| 'admin', 'Admin', 'ADMIN'            | 'admin'                    |
| 'owner', 'manager', 'user', NULL     | 'trader' (Fallback)        |
+--------------------------------------+----------------------------+
```

### Self-Service Registration Lifecycle
```
[Client Payload] --(Stripped 'role')--> [Service Layer: Force role='trader'] --> [DB Insert: 'trader']
```

### Default Admin Bootstrap Lifecycle
```
[App Startup] --> [Count users WHERE role='admin']
                      |
                      +-- (Count == 0) --> [Insert: admin@example.com / Admin@123 / role='admin']
                      |
                      +-- (Count > 0)  --> [Bypass Creation]
```

---

## Token Data Structure (JWT Access Token)

### Header
```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

### Payload Schema
```json
{
  "sub": "string",
  "role": "trader | admin",
  "exp": 1785168000,
  "iat": 1785081600
}
```
