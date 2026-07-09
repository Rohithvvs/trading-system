# Architecture Review & Design

## Current Architecture Analysis
The current application uses a separated React+Vite frontend and a FastAPI backend.
- **Backend Strengths**: High-performance asynchronous framework (FastAPI) backed by PostgreSQL and SQLAlchemy, with robust background tasks (APScheduler) and an existing logging structure.
- **Frontend Strengths**: Modern build tooling (Vite, Tailwind), clean component structure.
- **Weaknesses**: Lack of any authentication layer currently. All endpoints are implicitly open.

## New Authentication Architecture

### What can be reused:
- Database connection logic (`db/session.py`), SQLAlchemy declarative bases.
- FastAPI dependency injection system (can be seamlessly extended for `get_current_user`).
- Existing Tailwind CSS configuration in the frontend.

### What should NOT be modified:
- Core trading logic (Order execution, scanning algorithms).
- Background scheduler structures.

### Potential Breaking Changes:
- **Major**: Adding `Depends(get_current_user)` to existing routers will instantly break any frontend or external script that does not provide a Bearer token.
- **Solution**: The frontend must be updated simultaneously to wrap API calls with the AuthContext interceptor.

## Overall System Flow
1. **Client** (Browser/Mobile) interacts with the **Frontend** React app.
2. The React app sends credentials to the **FastAPI Backend**.
3. FastAPI validates against **PostgreSQL** (Argon2id hash comparison).
4. FastAPI issues a stateless **JWT**.
5. Client attaches JWT to the `Authorization: Bearer` header on subsequent requests.
6. FastAPI Dependency (`get_current_active_user`) extracts the JWT, verifies the signature using a secret key, checks **Redis** to ensure the token is not on the blocklist, checks PostgreSQL if role validation is needed, and injects the `User` object into the path operation.
