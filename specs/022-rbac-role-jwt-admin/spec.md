# Feature Specification: Sprint 1 – Role Normalization + JWT + Default Admin

**Feature Directory**: `specs/022-rbac-role-jwt-admin`  
**Status**: Draft  
**Target Sprint**: Sprint 1 (RBAC Foundation)  

---

## 1. Overview

Sprint 1 establishes the foundational security, authentication, and Role-Based Access Control (RBAC) architecture for the application. It establishes strict, normalized role definitions (`trader`, `admin`), embeds verified role claims into JSON Web Tokens (JWT), updates authentication endpoints to return consistent user identity and role metadata, enforces client-side role awareness, and automates the deterministic bootstrapping of a default system administrator account.

By standardizing roles across database storage, API transport, token payloads, and frontend state, this specification guarantees consistent authorization capabilities and eliminates privilege escalation vulnerabilities during registration.

---

## 2. Business Objective

The primary objective of Sprint 1 is to build a robust, tamper-proof authentication foundation that unlocks multi-tenant governance, administrative security, and role-restricted capabilities in subsequent application sprints.

Specifically, this sprint resolves existing data inconsistencies and authorization gaps by:
1. **Eliminating Security Vulnerabilities**: Preventing unauthorized users from self-elevating privileges to administrative roles during self-service account registration.
2. **Enabling Stateless Authorization**: Embedding identity and role claims directly inside signed JWT access tokens, eliminating redundant database queries for role verification on every API request.
3. **Establishing Administrative Access**: Guaranteeing that every deployment automatically initializes a known, deterministic default administrator account without requiring manual database manipulation.
4. **Providing Frontend Role Context**: Equipping client interfaces with clear, persistent user role state to control UI layout, navigation, and feature visibility safely.
5. **Ensuring Seamless Continuity**: Normalizing existing database role entries and maintaining total backward compatibility for existing valid accounts.

---

## 3. Current Problems

Prior to Sprint 1, the system suffers from several critical architectural and security deficiencies:

* **Inconsistent Role Casing & Values**: Roles in the database exist as heterogeneous strings (e.g., `Trader`, `TRADER`, `Admin`, `ADMIN`, `manager`, `owner`). This causes fragile role comparisons, conditional logic failures, and potential security bypasses due to case-sensitivity mismatches.
* **Privilege Escalation Vulnerability**: Account registration payloads accept arbitrary role inputs from clients, allowing malicious users to supply parameters like `{"role": "admin"}` and gain administrative privileges upon registration.
* **Opaque JWT Tokens**: Access tokens contain basic identification claims (e.g., `sub`) but omit role metadata. Upstream services and downstream middleware cannot enforce role-based access control statelessly without querying the database on every HTTP request.
* **Incomplete Auth API Responses**: Existing endpoints (`/auth/login`, `/auth/me`) do not return a unified identity object containing role metadata, forcing frontends to infer user privileges or perform secondary lookups.
* **Lack of Automated Admin Bootstrapping**: Deployments lack an automated method to guarantee administrative presence, leading to manual DB scripting or unauthenticated administrative setup steps.
* **Unconstrained Database Schema**: The database schema allows arbitrary string inserts into the role column without strict value domain enforcement or explicit column defaults.

---

## 4. Proposed Solution

Sprint 1 implements a unified 2-tier role security architecture spanning backend, database, JWT, API, and frontend layers:

1. **Role Standardizing & Normalization**: Standardize all role representation across the entire ecosystem to exactly two lower-case string literals: `trader` and `admin`.
2. **Hardcoded Registration Role**: Force all new self-service registration requests to be assigned `role = "trader"` server-side, completely ignoring and discarding any client-provided role fields.
3. **Enhanced JWT Payload**: Update the JWT access token generation module to include `sub` (user identity), `role` (assigned role), and `exp` (expiration timestamp) claims.
4. **Unified API Contract**: Standardize `/auth/login` and `GET /auth/me` responses to return `id`, `email`, `full_name`, and `role`.
5. **Client-Side Role Awareness**: Store `user.role` in frontend authentication context and persist it in local or session storage alongside the JWT access token.
6. **Automated Idempotent Admin Bootstrapper**: Execute a startup routine that verifies if an administrator exists. If no account with `role = "admin"` exists, automatically create `admin@example.com` with password `Admin@123` and `role = "admin"`.
7. **Idempotent Data Migration & Constraints**: Apply a database migration to transform existing case-variant roles (`Trader`, `ADMIN`, `owner`, etc.) to valid normalized values, set column default to `'trader'`, and enforce a SQL `CHECK` constraint.

---

## 5. Scope

### In-Scope
* Database schema migration and data normalization for existing users.
* Enforcement of SQL check constraints for `role IN ('trader', 'admin')`.
* Registration logic updates to enforce `role = "trader"`.
* JWT issuance updates to embed `sub`, `role`, and `exp` claims.
* Auth API response updates for `POST /auth/register`, `POST /auth/login`, and `GET /auth/me`.
* Frontend authentication state and storage persistence updates for user role.
* Startup initialization routine for default administrator creation.

### Out-of-Scope (Explicitly Deferred)
* Admin Dashboard UI components.
* Admin-restricted API endpoints or administrative route handlers.
* Permission matrix or granular RBAC policy engines (e.g., fine-grained permission flags).
* `AdminRoute` or client-side route guard components.
* Developer Mode / Debug role switching utilities.
* Feature flags management system.
* User management APIs (listing, updating roles, deactivating users).
* Business logic changes to trading execution, scanner engines, or portfolio management.

---

## 6. Functional Requirements

### Role Normalization & Enforcement
* **FR-001**: The system MUST restrict valid user roles exclusively to the two lower-case string values: `"trader"` and `"admin"`.
* **FR-002**: The backend registration handler MUST unconditionally assign `role = "trader"` to every newly registered user account.
* **FR-003**: The backend registration handler MUST ignore, strip, and fail to process any client-submitted `role` field in the registration payload, preventing self-assignment of roles.
* **FR-004**: The database MUST enforce column default of `'trader'` for the `role` field on the user table.
* **FR-005**: The database MUST enforce a check constraint ensuring that any inserted or updated row has `role IN ('trader', 'admin')`.

### JWT Access Tokens
* **FR-006**: Upon successful authentication (`POST /auth/login` or `POST /auth/register`), the backend MUST generate a signed JWT access token containing the following claims:
  * `sub`: User unique identifier (string/integer representation).
  * `role`: User normalized role (`"trader"` or `"admin"`).
  * `exp`: Token expiration epoch timestamp (integer).
* **FR-007**: The backend token verification middleware MUST statelessly decode and expose the `role` claim from valid JWT tokens for downstream request context.

### Authentication API Endpoints
* **FR-008**: The `POST /auth/login` response payload MUST include the authenticated user's metadata: `id`, `email`, `full_name`, and `role`.
* **FR-009**: The `GET /auth/me` endpoint MUST validate the caller's JWT access token and return the user's profile metadata: `id`, `email`, `full_name`, and `role`.
* **FR-010**: Authentication responses MUST format the `role` string in normalized lower-case (`"trader"` or `"admin"`).

### Default Administrator Initialization
* **FR-011**: On backend application startup, the system MUST check the database for the existence of any user account with `role = "admin"`.
* **FR-012**: If zero administrative accounts exist, the system MUST automatically create a default administrator account with:
  * Email: `admin@example.com`
  * Password: `Admin@123` (hashed using system standard password hashing algorithm)
  * Role: `admin`
* **FR-013**: If one or more administrative accounts already exist, the default administrator creation routine MUST bypass execution without throwing errors or mutating existing records.
* **FR-014**: The startup administrator bootstrap routine MUST be idempotent and safe for execution in single-instance and multi-instance deployment environments.

### Frontend Role Context
* **FR-015**: The frontend authentication context MUST extract and hold the user's `role` property as part of the authenticated user state (`user.role`).
* **FR-016**: The frontend MUST persist `user.role` alongside authentication tokens in persistent client storage (local storage or session storage).
* **FR-017**: On application initialization/rehydration, the frontend MUST populate `user.role` from persistent storage or initial `/auth/me` fetch.

---

## 7. Non-Functional Requirements

### Performance
* **NFR-001**: Role validation during API authorization MUST execute statelessly using the JWT `role` claim, incurring 0 additional database read queries per request.
* **NFR-002**: The default admin startup check MUST add no more than 50 milliseconds to application startup time.

### Security
* **NFR-003**: The system MUST prevent privilege escalation attacks by enforcing backend ownership of role assignment during registration.
* **NFR-004**: JWT access tokens MUST be cryptographically signed using a strong secret key (HS256 or RS256) to prevent client-side tampering of the `role` claim.
* **NFR-005**: Password hashing for the default admin account MUST utilize the system's standard secure hashing algorithm with appropriate salt rounds.

### Maintainability & Scalability
* **NFR-006**: Role string definitions MUST be managed via centralized constants or enum declarations in backend and frontend codebases to prevent magic string duplication.
* **NFR-007**: Token format and auth payloads MUST follow standard RFC 7519 JSON Web Token specifications and REST conventions.

### Backward Compatibility
* **NFR-008**: Existing valid user credentials (email and password) MUST remain valid and fully functional post-migration.
* **NFR-009**: Existing client applications expecting standard auth tokens MUST continue operating without breaking, while acquiring access to the newly exposed `role` attributes.

### Auditability
* **NFR-010**: System startup logs MUST record the execution and result of the default admin initialization routine (e.g., "Default admin created" vs "Admin user exists, bootstrap skipped") without logging sensitive raw credentials.

---

## 8. Security Requirements

### Threat Model: Privilege Escalation via Self-Registration
In vulnerable authentication systems, registration endpoints accept generic JSON objects mapping directly to database models (Mass Assignment Vulnerability). If a client submits a registration payload containing:

```json
{
  "email": "attacker@example.com",
  "password": "SecurePassword123!",
  "full_name": "Malicious User",
  "role": "admin"
}
```

An unhardened backend might bind the `"role": "admin"` key directly to the newly created user record, granting full administrative privileges to an untrusted external user.

### Defense Mechanism & Backend Ownership
1. **Explicit Server-Side Overrides**: The registration handler MUST construct the user model by explicitly assigning `role = "trader"` in backend code. Any `role` key present in incoming request DTOs/schemas MUST either be rejected by strict schema validation or explicitly stripped prior to model binding.
2. **Backend Authorization Ownership**: Authorization levels and role assignments are strict system-owned properties. Clients are never authoritative source for their privilege level.
3. **Database Check & Default Guard**: As a defense-in-depth layer, the database column default (`DEFAULT 'trader'`) and column constraint (`CHECK (role IN ('trader', 'admin'))`) ensure invalid role values cannot be persisted even if backend application code experiences a validation bug.

### Security Rationale for JWT Role Claim
Embedding the `role` claim in the signed JWT payload ensures:
* **Stateless Verification**: API Gateways and microservices can inspect `payload.role` and enforce endpoint authorization without querying the primary user database, eliminating database bottleneck vulnerabilities under high load.
* **Tamper Resistance**: If an attacker attempts to modify the `role` value in the base64-encoded JWT payload from `"trader"` to `"admin"`, the cryptographic signature validation on the server will fail, immediately rejecting the request with HTTP 401 Unauthorized.

---

## 9. Authentication Flow

### Registration Flow
```
[Client App] ---> (POST /auth/register payload: email, password, full_name, [role ignored])
                      |
                      v
             [Backend Server]
                      |
            1. Validate Email & Password format
            2. Strip/Ignore any client-submitted 'role' property
            3. Explicitly set user.role = "trader"
            4. Hash password & persist user record to Database
            5. Generate JWT with claims: sub, role="trader", exp
                      |
                      v
[Client App] <--- (HTTP 200/201 Response: id, email, full_name, role="trader", access_token)
```

### Login Flow
```
[Client App] ---> (POST /auth/login payload: email, password)
                      |
                      v
             [Backend Server]
                      |
            1. Query User record by email from Database
            2. Verify password hash
            3. Extract user.role from record (normalized to "trader" or "admin")
            4. Generate JWT with claims: sub, role, exp
                      |
                      v
[Client App] <--- (HTTP 200 Response: id, email, full_name, role, access_token)
```

### Profile Retrieval / Verification Flow (`GET /auth/me`)
```
[Client App] ---> (GET /auth/me Header: Authorization: Bearer <access_token>)
                      |
                      v
             [Backend Server]
                      |
            1. Validate & decode JWT access token
            2. Extract user ID (sub) and role from token or verify user record
            3. Construct user profile response
                      |
                      v
[Client App] <--- (HTTP 200 Response: id, email, full_name, role)
```

---

## 10. JWT Flow

### Token Claims Structure
Every access token generated upon login or registration MUST adhere to the following payload schema:

```json
{
  "sub": "12345",
  "role": "trader",
  "exp": 1785168000,
  "iat": 1785081600
}
```

* `sub` (Subject): The unique identifier of the authenticated user.
* `role` (Role Claim): Lower-case string literal, strictly constrained to `"trader"` or `"admin"`.
* `exp` (Expiration): Standard Unix epoch timestamp indicating token expiration time.

### Token Verification Lifecycle
1. **Request Reception**: Incoming HTTP requests include `Authorization: Bearer <token>` in headers.
2. **Signature Verification**: Server verifies token signature using the server's secret signing key.
3. **Expiration Verification**: Server confirms `exp` timestamp is in the future.
4. **Context Injection**: Server decodes claims and attaches `user_id` and `user_role` to the request execution context.
5. **Authorization Enforcement**: Route handlers or middleware verify `user_role` against required endpoint permissions statelessly.

---

## 11. Database Requirements

### Schema Definition
The user table must define the `role` column with the following constraints:
* **Column Name**: `role`
* **Data Type**: String / Character Varying (VARCHAR) or ENUM.
* **Nullable**: False (`NOT NULL`).
* **Default Value**: `'trader'`
* **CHECK Constraint**: `CHECK (role IN ('trader', 'admin'))`

### Normalization Logic
During database migration execution:
* Case-insensitive matching maps `trader`, `Trader`, `TRADER` to `'trader'`.
* Case-insensitive matching maps `admin`, `Admin`, `ADMIN` to `'admin'`.
* Legacy roles such as `owner`, `manager`, `user`, `member`, or NULL values map safely to `'trader'`.

---

## 12. API Requirements

### 1. `POST /auth/register`

#### Request Payload
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "full_name": "Jane Doe"
}
```
*(Note: If `"role": "admin"` is included in the request body, the backend MUST ignore it and proceed with registration assigning `role = "trader"`).*

#### Success Response (HTTP 201 Created or 200 OK)
```json
{
  "id": "usr_98765",
  "email": "user@example.com",
  "full_name": "Jane Doe",
  "role": "trader",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

### 2. `POST /auth/login`

#### Request Payload
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

#### Success Response (HTTP 200 OK)
```json
{
  "id": "usr_98765",
  "email": "user@example.com",
  "full_name": "Jane Doe",
  "role": "trader",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

### 3. `GET /auth/me`

#### Request Headers
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### Success Response (HTTP 200 OK)
```json
{
  "id": "usr_98765",
  "email": "user@example.com",
  "full_name": "Jane Doe",
  "role": "trader"
}
```

---

### Error Responses

#### Invalid Credentials (HTTP 401 Unauthorized)
```json
{
  "error": "Unauthorized",
  "message": "Invalid email or password"
}
```

#### Missing/Malformed Bearer Token (HTTP 401 Unauthorized)
```json
{
  "error": "Unauthorized",
  "message": "Missing or invalid authentication token"
}
```

---

## 13. Frontend Requirements

### Auth Context & State Model
The client application's central authentication store must manage an identity object adhering to:

```typescript
interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: 'trader' | 'admin';
}
```

### Storage Persistence
* Upon successful login or registration, the frontend MUST persist both the `access_token` and `user.role` (or the complete `user` object) in client storage (local storage or session storage).
* Upon logout or session invalidation, the frontend MUST purge `access_token` and stored user state.

### Rehydration & Session Restoring
* On initial web page load or app boot:
  1. Retrieve persisted token and user role from storage.
  2. If token exists, invoke `GET /auth/me` to verify session validity and update client auth context with server-returned `role`.
  3. If `GET /auth/me` returns 401 Unauthorized, clear storage and transition auth state to unauthenticated.

---

## 14. Migration Strategy

### Step 1: Pre-Migration Data Audit
Before applying schema changes, execute a data audit query to inspect distinct values currently stored in the `role` column.

### Step 2: Data Normalization Transformation
Execute an idempotent data update script:
1. Update values matching `'admin'`, `'Admin'`, `'ADMIN'` to `'admin'`.
2. Update values matching `'trader'`, `'Trader'`, `'TRADER'` to `'trader'`.
3. Update all other values (e.g., `'owner'`, `'manager'`, `NULL`) to `'trader'`.

### Step 3: Schema & Constraint Application
1. Alter column `role` to set default value `'trader'`.
2. Alter column `role` to set `NOT NULL`.
3. Add table `CHECK` constraint: `CHECK (role IN ('trader', 'admin'))`.

### Step 4: Verification & Rollback Plan
* **Verification**: Query distinct role values post-migration to confirm only `'trader'` and `'admin'` exist.
* **Rollback Plan**: If migration fails during constraint application, drop check constraint, restore default value settings, and log error details without corrupting user identity data.

---

## 15. Default Admin Strategy

### Bootstrapping Lifecycle
The backend service MUST execute an automated initialization hook during application startup (e.g., server boot event):

```
                       [Application Boot]
                               |
                               v
               [Query DB: WHERE role = 'admin']
                               |
                   +-----------+-----------+
                   |                       |
            (Count > 0)               (Count == 0)
                   |                       |
                   v                       v
          [Bypass Initialization]   [Execute Creation Routine]
          Log: "Admin user exists"         |
                                           |-- Email: admin@example.com
                                           |-- Password: Admin@123 (hashed)
                                           |-- Role: admin
                                           |-- Full Name: Default Admin
                                           v
                                    [Persist Admin Record]
                                    Log: "Default admin initialized"
```

### Concurrency & Idempotency Safeguards
In multi-instance containerized deployments (e.g., multiple web workers starting simultaneously), duplicate execution is mitigated by:
* Catching unique key violation errors on `email = 'admin@example.com'` gracefully without crashing server startup.
* Executing the check and creation within an isolated database transaction block.

---

## 16. Risks

| Risk ID | Risk Description | Severity | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **R-001** | Legacy users with custom role strings (e.g. `owner`) lose administrative access when normalized to `trader`. | High | Perform pre-migration user audit. Manually verify high-privilege account emails prior to executing mass update script. |
| **R-002** | Default admin account credentials (`admin@example.com` / `Admin@123`) remain unchanged in production environments. | Critical | Log explicit security warnings on startup if default admin password remains default; document mandatory password update protocol in operational runbooks. |
| **R-003** | Active client sessions holding legacy JWT tokens (without `role` claim) fail token verification post-deployment. | Medium | Gracefully handle missing `role` claims by triggering automatic token refresh or requiring single re-login post-deployment. |

---

## 17. Assumptions

* **A-001**: The system uses a standard relational database supporting SQL `CHECK` constraints (e.g., PostgreSQL, SQLite, MySQL 8.0+).
* **A-002**: Password hashing utilizes a secure, one-way cryptographic hashing function (e.g., Argon2, bcrypt, or PBKDF2) already integrated into the backend core.
* **A-003**: The client application communicates with the backend over secure HTTPS channels to protect bearer tokens and auth payloads in transit.
* **A-004**: Users are uniquely identified by a primary key (`id`) and a unique `email` address.

---

## 18. Out of Scope

The following capabilities are explicitly EXCLUDED from Sprint 1 deliverables:
1. **Admin Dashboard Interface**: No UI screens for administrative analytics, system controls, or management dashboards.
2. **Admin-Restricted API Endpoints**: No business logic endpoints configured with admin authorization guards (e.g., `/api/v1/admin/*`).
3. **Granular Permission Engine**: No fine-grained permissions (e.g., `READ_PORTFOLIO`, `EXECUTE_TRADE`) or policy evaluation matrices.
4. **Client-Side Route Guards**: No higher-order React components or router guards (`<AdminRoute />`).
5. **Developer Mode / Debug Overrides**: No UI widgets or header overrides allowing developers to swap roles dynamically.
6. **Feature Flags System**: No conditional feature toggles tied to user roles.
7. **User Management APIs**: No CRUD endpoints for listing all users, editing user roles, or deleting accounts.
8. **Business Logic Changes**: No modifications to core trading, portfolio, or scanning business logic.

---

## 19. Acceptance Criteria

### 1. Registration
* [ ] **AC-REG-01**: Given a registration payload with valid `email`, `password`, and `full_name`, when `POST /auth/register` is called, then the user is created with `role = "trader"` and returned in the response.
* [ ] **AC-REG-02**: Given a registration payload containing `"role": "admin"`, when `POST /auth/register` is called, then the request succeeds but the created user role MUST be `"trader"`.
* [ ] **AC-REG-03**: Given a registration payload containing `"role": "SUPERUSER"`, when `POST /auth/register` is called, then the created user role MUST be `"trader"`.

### 2. Login
* [ ] **AC-LOG-01**: Given valid credentials for a trader account, when `POST /auth/login` is called, then the response HTTP status is 200 OK and payload contains `id`, `email`, `full_name`, `role: "trader"`, and `access_token`.
* [ ] **AC-LOG-02**: Given valid credentials for an admin account, when `POST /auth/login` is called, then the response HTTP status is 200 OK and payload contains `id`, `email`, `full_name`, `role: "admin"`, and `access_token`.
* [ ] **AC-LOG-03**: Given invalid credentials, when `POST /auth/login` is called, then HTTP 401 Unauthorized is returned.

### 3. JWT Access Token
* [ ] **AC-JWT-01**: Given a freshly issued `access_token`, when decoded, the payload MUST contain valid `sub`, `role`, and `exp` claims.
* [ ] **AC-JWT-02**: Given an `access_token` issued for a trader user, the decoded `role` claim MUST strictly equal `"trader"`.
* [ ] **AC-JWT-03**: Given an `access_token` issued for an admin user, the decoded `role` claim MUST strictly equal `"admin"`.

### 4. Auth APIs (`GET /auth/me`)
* [ ] **AC-ME-01**: Given a valid Bearer token for a trader, when `GET /auth/me` is called, then the response returns HTTP 200 OK with `id`, `email`, `full_name`, and `role: "trader"`.
* [ ] **AC-ME-02**: Given a valid Bearer token for an admin, when `GET /auth/me` is called, then the response returns HTTP 200 OK with `id`, `email`, `full_name`, and `role: "admin"`.
* [ ] **AC-ME-03**: Given a missing or invalid Bearer token, when `GET /auth/me` is called, then HTTP 401 Unauthorized is returned.

### 5. Frontend Integration
* [ ] **AC-FE-01**: Given a successful login response, the frontend auth state MUST store `user.role` matching the server response.
* [ ] **AC-FE-02**: Given a successful login response, the frontend MUST persist `user.role` (or user object) in client storage.
* [ ] **AC-FE-03**: Given an application page refresh, the frontend auth context MUST rehydrate `user.role` correctly from storage or `/auth/me`.

### 6. Default Admin Initialization
* [ ] **AC-ADM-01**: Given an empty database with 0 users, when the application starts up, then a user account with email `admin@example.com`, role `"admin"`, and password `Admin@123` is automatically created.
* [ ] **AC-ADM-02**: Given a database where an account with `role = "admin"` already exists, when the application starts up, then the bootstrapper completes cleanly without creating duplicate accounts or altering existing users.
* [ ] **AC-ADM-03**: Given the default admin account created on startup, when logging in with `admin@example.com` and `Admin@123`, then authentication succeeds and returns `role: "admin"`.

### 7. Database Migration
* [ ] **AC-DB-01**: Given existing database rows with roles `Trader`, `TRADER`, `Admin`, `ADMIN`, when migration executes, then all role values are updated to lower-case `'trader'` or `'admin'`.
* [ ] **AC-DB-02**: Given any existing database rows with unrecognized roles (e.g. `owner`), when migration executes, then the role value is updated to `'trader'`.
* [ ] **AC-DB-03**: Given a post-migration database, attempting to insert a row with `role = 'invalid_role'` MUST fail due to SQL check constraint violation.
* [ ] **AC-DB-04**: Given a post-migration database, inserting a user without specifying a role MUST default column value to `'trader'`.

### 8. Backward Compatibility
* [ ] **AC-BC-01**: Existing valid users in the database prior to migration MUST be able to log in with their existing passwords post-migration without error.

---

## 20. Sprint Summary

| Component | Responsibility / Mandate in Sprint 1 |
| :--- | :--- |
| **Role Values** | Strictly normalized to `"trader"` and `"admin"`. |
| **Registration Security** | Hardcoded `role = "trader"`. Client payload role input is ignored. |
| **JWT Claims** | Includes `sub`, `role`, and `exp` claims statelessly. |
| **Auth Responses** | `/auth/login` and `/auth/me` return `id`, `email`, `full_name`, and `role`. |
| **Frontend Context** | Stores and persists `user.role` in auth state and local/session storage. |
| **Default Admin** | Bootstrapped on startup (`admin@example.com` / `Admin@123` / `admin`) if 0 admins exist. |
| **Database Guard** | Migration normalizes legacy values, sets default `'trader'`, enforces `CHECK` constraint. |

---
