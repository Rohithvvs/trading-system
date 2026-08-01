# Phase 0 Research: Sprint 1 – Role Normalization + JWT + Default Admin

## Research Topic 1: Role Enforcement & Registration Privilege Escalation

### Decision
Enforce role assignment strictly at the backend service layer during registration by hardcoding `role = "trader"`. Strip or ignore any client-supplied `role` key in incoming request schemas.

### Rationale
Registration endpoints are public, unauthenticated attack vectors. If request deserializers bind request bodies directly to database models (Mass Assignment Vulnerability), clients can inject `"role": "admin"`. Server-side hardcoded assignment guarantees zero-trust boundaries where external clients cannot dictate authorization levels.

### Alternatives Considered
* **Schema Validation Rejection**: Returning HTTP 422 if `"role"` is in payload. *Rejected*: Stripping/ignoring the parameter prevents breaking clients that accidentally pass metadata while preserving strict security.
* **Role Whitelist Filtering**: Allowing clients to select roles from an allowed list. *Rejected*: Self-service registration must never allow administrative role selection.

---

## Research Topic 2: Stateless JWT Claims vs Database Lookups

### Decision
Embed `sub`, `role`, and `exp` claims inside standard signed JWT access tokens. Downstream request context and API authorization middleware decode and trust the signed `role` claim statelessly.

### Rationale
Querying the database on every authenticated API request for role verification introduces significant I/O latency and database load. Including `role` in the cryptographically signed JWT allows instant, stateless role verification across microservices and API gateways.

### Alternatives Considered
* **Database Role Lookups Per Request**: Fetching user role from database in auth middleware. *Rejected*: Unnecessary DB overhead when JWT signatures guarantee claim integrity.
* **Session Storage / Redis Lookup**: Checking token against a central session store. *Rejected*: Adds stateful infrastructure complexity to an otherwise stateless JWT architecture.

---

## Research Topic 3: Database Data Normalization & Schema Constraints

### Decision
Execute an idempotent Alembic/SQL migration that normalizes existing string variations (`Trader`, `TRADER`, `owner`, `manager` -> `'trader'`, `Admin`, `ADMIN` -> `'admin'`), alters the column default to `'trader'`, and applies a SQL `CHECK (role IN ('trader', 'admin'))` constraint.

### Rationale
Inconsistent string casing causes subtle bugs in conditional checks across services. Database-level `CHECK` constraints provide a defense-in-depth barrier ensuring invalid data can never be persisted regardless of application layer bugs.

### Alternatives Considered
* **Application-Only Validation**: Handling role normalization in Python/TypeScript application logic without DB constraints. *Rejected*: Leaves database vulnerable to raw SQL inserts or legacy script bugs.
* **Native Database ENUM**: Using `CREATE TYPE user_role AS ENUM ('trader', 'admin')`. *Rejected*: Modifying DB ENUM types in future migrations introduces database-specific DDL complexity compared to standard VARCHAR + CHECK constraints.

---

## Research Topic 4: Automated Default Admin Bootstrapping

### Decision
Execute an application startup hook that queries the user repository for any record with `role = "admin"`. If count is 0, initialize an admin account with `admin@example.com`, password `Admin@123`, and `role = "admin"`.

### Rationale
Automating admin setup on startup guarantees zero-touch deployments without manual SQL execution while ensuring idempotency across restarts.

### Alternatives Considered
* **Manual SQL Seed Scripts**: Running seed scripts during deployment pipelines. *Rejected*: Prone to operator error and deployment step omission.
* **Hardcoded Credentials in Environment**: Loading admin credentials strictly from ENV variables on every request. *Rejected*: Admin accounts must exist as persistent database records with standard password hashing.
