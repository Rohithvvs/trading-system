# Implementation Plan: Sprint 1 – Role Normalization + JWT + Default Admin

**Branch**: `022-rbac-role-jwt-admin`  
**Spec Document**: [spec.md](file:///D:/Work_Space/trading-system/specs/022-rbac-role-jwt-admin/spec.md)  
**Status**: Approved Architecture Plan  

---

## 1. Sprint Goal

The objective of Sprint 1 is to establish a secure, standardized, role-based access control (RBAC) foundation across the application. 

This sprint delivers:
1. **Strict Role Normalization**: Standardizing all role representations across backend, database, JWT claims, API contracts, and frontend state strictly to `"trader"` and `"admin"`.
2. **Zero-Trust Privilege Escalation Prevention**: Hardcoding self-service registration to assign `role = "trader"`, explicitly stripping and ignoring client-supplied role payloads.
3. **Stateless JWT Claims**: Embedding `sub`, `role`, and `exp` claims into signed access tokens, allowing downstream services and client applications to evaluate permissions statelessly without database lookup overhead.
4. **Automated Admin Bootstrapping**: Guaranteeing the automated initialization of a single default administrator account (`admin@example.com` / `Admin@123` / `admin`) on application startup if zero admins exist.
5. **Database Integrity & Backward Compatibility**: Applying idempotent data migrations, setting column defaults, and enforcing SQL check constraints while preserving existing active user sessions.

---

## 2. Architecture Impact

Sprint 1 impacts seven key architectural layers across the application:

* **Database Layer**: Data migration normalizes legacy role strings (`Trader`, `TRADER`, `owner`, `manager` -> `'trader'`, `Admin`, `ADMIN` -> `'admin'`), sets column default to `'trader'`, and enforces a SQL `CHECK (role IN ('trader', 'admin'))` constraint.
* **Backend Data Models**: User model updated to enforce normalized role attributes and string constraints.
* **Request/Response Schemas**: Registration request DTOs updated to ignore/strip role input fields; Auth response DTOs updated to include `role` attribute alongside `id`, `email`, `full_name`, and `access_token`.
* **Authentication Service**: Registration business logic updated to hardcode `role = "trader"`. Login and profile retrieval services updated to load and format normalized user role metadata.
* **JWT Service**: Token generation engine updated to embed `role` claim alongside `sub` and `exp` claims in token payloads.
* **Startup Initialization Layer**: Application lifecycle bootstrapper updated to include an idempotent default administrator seed routine.
* **Frontend Authentication State**: Auth context, state store, and persistent storage wrappers updated to extract, store, and rehydrate `user.role` persistently.

---

## 3. Implementation Phases

```
+-----------------------------------------------------------------------------------+
|                            Phase Execution Lifecycle                              |
+-----------------------------------------------------------------------------------+
| Phase 1: Database Migration & Schema Constraints                                  |
|   -> Phase 2: Core Backend Domain & JWT Security                                  |
|     -> Phase 3: Auth API Contracts & Serialization                                |
|       -> Phase 4: Startup Bootstrapper & Default Admin Seed                       |
|         -> Phase 5: Client Authentication State & Storage Persistence           |
|           -> Phase 6: End-to-End Validation & Security Auditing                   |
+-----------------------------------------------------------------------------------+
```

### Phase 1: Database Migration & Schema Constraints
* **Purpose**: Normalize existing user data and establish database-level schema constraints.
* **Expected Outcome**: All existing database rows hold normalized role strings (`'trader'` or `'admin'`). Schema enforces column default `'trader'` and `CHECK` constraint.
* **Dependencies**: None (Foundation step).
* **Risks**: Data corruption or unintended role demotion during mass string transformation.
* **Validation**: Query distinct role values post-migration to confirm 100% compliance with allowed domain values.

### Phase 2: Core Backend Domain & JWT Security
* **Purpose**: Enforce role normalization rules in data models and embed role claims in JWT access tokens.
* **Expected Outcome**: Data access layer enforces role enum/constant types; JWT engine embeds `sub`, `role`, and `exp` claims upon token generation.
* **Dependencies**: Phase 1 (Database migration).
* **Risks**: Missing or malformed claims breaking token signature verification.
* **Validation**: Unit tests verifying token decoding contains `role` claim matching user domain model.

### Phase 3: Auth API Contracts & Serialization
* **Purpose**: Update registration, login, and profile API handlers to process normalized roles and prevent privilege escalation.
* **Expected Outcome**: Registration endpoint hardcodes `role = "trader"`, ignoring client-submitted roles. Login and `/auth/me` endpoints return `role` in response payloads.
* **Dependencies**: Phase 2 (Core domain & JWT service).
* **Risks**: Incompatible client serialization breaking existing frontend consumers.
* **Validation**: Integration tests sending `"role": "admin"` during registration verifying created record is `"trader"`.

### Phase 4: Startup Bootstrapper & Default Admin Seed
* **Purpose**: Implement automated startup routine to guarantee existence of default admin account.
* **Expected Outcome**: Application startup checks for admin existence and seeds `admin@example.com` (`Admin@123` / `admin`) if 0 admins exist.
* **Dependencies**: Phase 3 (Auth services & API layer).
* **Risks**: Race conditions in multi-instance cluster deployments creating duplicate seeds or throwing unhandled errors.
* **Validation**: Boot application on clean DB; verify admin creation; restart application; verify idempotent bypass.

### Phase 5: Client Authentication State & Storage Persistence
* **Purpose**: Integrate user role awareness into frontend authentication context and client storage.
* **Expected Outcome**: Frontend state store holds `user.role`; local/session storage persists role; initial app boot rehydrates role.
* **Dependencies**: Phase 3 (API contracts).
* **Risks**: Stale storage state causing auth context mismatch post-deployment.
* **Validation**: Automated frontend unit/integration tests verifying storage read/write and state rehydration.

### Phase 6: End-to-End Validation & Security Auditing
* **Purpose**: Execute regression testing, security penetration testing (privilege escalation attempts), and migration verification.
* **Expected Outcome**: 100% passing acceptance criteria across all 8 sprint domains.
* **Dependencies**: Phases 1–5.
* **Risks**: Uncovered edge cases breaking active sessions.
* **Validation**: Full suite execution of unit, integration, contract, and quickstart scenarios.

---

## 4. Component Breakdown

```
+-----------------------------------------------------------------------------------+
|                             System Component Architecture                         |
+-----------------------------------------------------------------------------------+
|  [Frontend Auth Store & Storage]  <--->  [Auth REST API Layer]                    |
|                                                  |                                |
|                                                  v                                |
|  [JWT Token Generation Engine]    <--->  [Authentication Service]                 |
|                                                  |                                |
|                                                  v                                |
|  [Startup Seed Bootstrapper]      <--->  [Database Access Layer & Constraints]    |
+-----------------------------------------------------------------------------------+
```

* **Database Layer**: Relational schema hosting `users` table with `role` column (`DEFAULT 'trader'`, `CHECK (role IN ('trader', 'admin'))`).
* **Backend Data Models**: Domain model defining user entity with strict role type definitions.
* **Request/Response Schemas**: Serialization DTOs defining strict incoming payloads (omitting/ignoring role) and outgoing structures (including `id`, `email`, `full_name`, `role`).
* **Authentication Service**: Core application service executing credentials verification, user persistence, password hashing, and role assignment.
* **JWT Service**: Cryptographic signing and decoding service managing access token lifecycle and claim injection (`sub`, `role`, `exp`).
* **API Route Layer**: HTTP controllers exposing `/auth/register`, `/auth/login`, and `/auth/me` endpoints.
* **Startup Initialization Module**: Event listener executing database query on app startup to seed default admin if necessary.
* **Frontend Auth Context & Storage**: Client state manager maintaining `user.role` in memory and persisting state to local/session storage.

---

## 5. Dependency Order

Work must proceed sequentially according to technical dependency relationships:

```
    [1. Database Migration & Schema Constraints]
                        │
                        ▼
       [2. Backend Data Models & Domain]
                        │
                        ▼
      [3. Serialization Schemas & DTOs]
                        │
                        ▼
           [4. JWT Generation Engine]
                        │
                        ▼
         [5. Authentication Service]
                        │
                        ▼
            [6. API Controllers & Routes]
                        │
                        ▼
      [7. Application Startup Bootstrapper]
                        │
                        ▼
   [8. Frontend State & Storage Integration]
                        │
                        ▼
      [9. End-to-End Security & Integration Testing]
```

---

## 6. Data Flow

### Registration Flow
1. **Client Submission**: Client sends `POST /auth/register` with `email`, `password`, `full_name` (and optional malicious `role`).
2. **Schema Sanitization**: API deserializer strips/ignores client-submitted `role`.
3. **Service Logic**: Auth service explicitly sets `role = "trader"`, hashes password, and persists user record.
4. **Database Guard**: Database default `'trader'` and check constraint validate record integrity during insert.
5. **Token Generation**: JWT engine generates access token embedding `sub`, `role="trader"`, and `exp`.
6. **API Response**: Response returned with `id`, `email`, `full_name`, `role: "trader"`, and `access_token`.
7. **Client Persistence**: Frontend auth context updates state and persists `access_token` and `user.role` in storage.

### Login Flow
1. **Client Submission**: Client sends `POST /auth/login` with credentials.
2. **Authentication**: Auth service verifies password hash against database record.
3. **Role Fetch**: User record role (`"trader"` or `"admin"`) retrieved from database.
4. **Token Generation**: JWT engine generates token with `sub`, `role`, and `exp`.
5. **API Response**: Response returned with user metadata and token.
6. **Client Hydration**: Client updates in-memory auth context (`user.role`) and stores token.

---

## 7. Security Plan

* **Privilege Escalation Prevention**: Public registration APIs must NEVER trust incoming role attributes. Role assignment is exclusively owned by server-side logic (`role = "trader"`).
* **Role Ownership**: Authorization roles are system-controlled security policies. Only administrative provisioning processes (e.g. system bootstrapper or internal DB admin scripts) can assign `role = "admin"`.
* **JWT Integrity & Trust**: JWT tokens are cryptographically signed using a strong secret key. Decoded token claims (`role`) are trusted statelessly by backend middleware because signature verification guarantees payload immutability.
* **Stateless Validation**: Middleware verifies `role` from verified JWT claims, eliminating DB lookup vectors while guarding protected routes.
* **Default Admin Security**: The default admin account (`admin@example.com`) is seeded with password `Admin@123` hashed using system standard password hashing algorithms. Application startup logs emit security reminders urging immediate password update post-deployment.

---

## 8. Migration Plan

* **Pre-Migration Data Cleanup**: Execute a data audit query identifying distinct non-standard role values in the database.
* **Idempotent String Normalization**: Run migration script converting:
  * Case variants (`Trader`, `TRADER`) -> `'trader'`
  * Case variants (`Admin`, `ADMIN`) -> `'admin'`
  * Unrecognized legacy roles (`owner`, `manager`, `user`, NULL) -> `'trader'`
* **Schema Updates**:
  1. Alter column `role` to `NOT NULL`.
  2. Set column `DEFAULT 'trader'`.
  3. Apply SQL `CHECK (role IN ('trader', 'admin'))`.
* **Rollback Plan**: In the event of migration failure, drop the check constraint, restore column defaults, and log failure details without altering primary user identity records.

---

## 9. Testing Strategy

* **Unit Testing**:
  * Verify DTO sanitization strips `role` from registration inputs.
  * Verify JWT generation embeds correct `sub`, `role`, and `exp` claims.
  * Verify default admin bootstrapper checks admin count correctly.
* **Integration Testing**:
  * Execute registration with `"role": "admin"` payload; verify database row created with `role = "trader"`.
  * Execute login for trader and admin accounts; verify API response structure contains correct `role`.
  * Call `GET /auth/me` with valid Bearer token; verify response profile metadata.
* **Migration Testing**:
  * Seed test database with legacy strings (`Trader`, `ADMIN`, `manager`); execute migration; verify all rows normalized correctly.
  * Test raw SQL insert with invalid role (`'superuser'`); verify database throws check constraint error.
* **Frontend Testing**:
  * Verify frontend auth state correctly stores `user.role`.
  * Verify client storage persistence and rehydration on app restart.
* **Security & Penetration Testing**:
  * Attempt privilege escalation via registration mass-assignment payloads.
  * Attempt token tampering (modifying JWT role claim in base64 without valid signature); verify backend returns HTTP 401.

---

## 10. Risks & Mitigation Strategies

| Risk ID | Risk Description | Impact | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **R-01** | Legacy users with non-standard role titles demoted to `trader` during migration. | High | Pre-migration data audit; review and manually flag high-privilege accounts prior to executing mass update script. |
| **R-02** | Default admin account credentials (`admin@example.com` / `Admin@123`) un-updated in production. | Critical | Application startup emits prominent security alerts; document mandatory password reset procedure in deployment guide. |
| **R-03** | Startup race conditions in multi-instance clusters attempting duplicate default admin creation. | Medium | Enforce database transaction isolation and catch unique key constraint violations on admin email gracefully. |
| **R-04** | Active client sessions holding legacy JWT tokens (missing `role` claim) experience auth failures. | Medium | Gracefully handle missing token role claims by triggering automatic token refresh or re-authentication. |

---

## 11. Validation Checklist

- [ ] Data migration converts all legacy role strings to lower-case `'trader'` or `'admin'`.
- [ ] Database schema enforces `NOT NULL`, `DEFAULT 'trader'`, and `CHECK (role IN ('trader', 'admin'))`.
- [ ] Registration API ignores client-supplied `role` input and forces `role = "trader"`.
- [ ] Login API returns `id`, `email`, `full_name`, `role`, and `access_token`.
- [ ] JWT access token contains valid `sub`, `role`, and `exp` claims.
- [ ] `GET /auth/me` validates token and returns user profile including `role`.
- [ ] Application startup automatically seeds `admin@example.com` (`Admin@123` / `admin`) if 0 admins exist.
- [ ] Startup admin seed routine is idempotent on subsequent application restarts.
- [ ] Frontend auth context stores `user.role` and persists state to client storage.
- [ ] Frontend rehydrates `user.role` correctly upon application reload.

---

## 12. Deployment Plan

* **Pre-Deployment**: Run pre-migration database audit to verify current role string distribution.
* **Database Migration**: Execute migration script during deployment pipeline prior to application process restart.
* **Application Startup**: Launch application processes; startup bootstrapper executes admin count check and seeds default admin if required.
* **Verification**: Execute quickstart validation suite (`POST /auth/login` for default admin and `POST /auth/register` for new trader).
* **Rollback Plan**: If critical errors occur, revert application binary version and execute database rollback migration.

---

## 13. Success Criteria

Sprint 1 will be considered 100% complete when:

1. **Role Standardizing**: 100% of user roles in the database are strictly `'trader'` or `'admin'`.
2. **Registration Security**: Registration payloads attempting self-assignment of `role = "admin"` yield `role = "trader"` accounts without exception.
3. **Stateless Authorization**: All generated JWT access tokens contain valid `sub`, `role`, and `exp` claims.
4. **Unified API Contracts**: `/auth/login` and `/auth/me` responses include normalized `role` attributes across all test scenarios.
5. **Admin Bootstrapping**: Default administrator account (`admin@example.com`) is verified working on clean deployment.
6. **Frontend State**: Frontend authentication state store accurately reflects and persists `user.role`.
7. **Test Coverage**: All unit, integration, security, and migration test suites pass with zero regressions.
