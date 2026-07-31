"""Automated tests for 026-remove-multi-user (single-user application simplification).

Coverage maps to:
  - FR-010-01 / FR-010-02  — auth pages & JWT session stack removed
  - FR-011-01 / FR-011-02  — user tables removed; static SYSTEM_OWNER context
  - FR-012-01              — admin role gates removed from owner deps
  - FR-013-01 / FR-013-02  — trading engines + FYERS OAuth preserved
  - US1 / US2 / US3 acceptance scenarios
  - Edge cases: no cookies, deprecated auth paths, same owner every call
  - SC-001 / SC-002        — no user-auth surfaces; no auth required for trading APIs
"""
from __future__ import annotations

import importlib
import uuid
import warnings
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.deps import (
    SYSTEM_OWNER,
    SYSTEM_OWNER_ID,
    ApplicationOwnerContext,
    get_application_owner_context,
    get_application_owner_id,
    get_current_active_user,
    get_current_user,
    get_current_user_id_sync,
    get_current_user_sync,
)
from app.main import app
from app.models.broker_token import BrokerToken
from app.models.paper_trading import PaperTradingAccount
from app.services.audit_service import AuditService


EXPECTED_OWNER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Spec FR-010-01 / contracts: user authentication API surface removed
REMOVED_AUTH_PATHS = [
    "/api/v1/auth/signup",
    "/api/v1/auth/login",
    "/api/v1/auth/google",
    "/api/v1/auth/logout",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/me",
    "/api/v1/auth/profile",
    "/api/v1/auth/sessions",
    "/auth/signup",
    "/auth/login",
    "/auth/logout",
    "/auth/me",
    "/auth/profile",
]

# Modules deleted as part of multi-user removal
REMOVED_MODULES = [
    "app.models.auth",
    "app.models.user_profile",
    "app.routes.auth",
    "app.services.auth_service",
    "app.services.user_profile_service",
    "app.services.email_service",
    "app.schemas.auth",
    "app.schemas.user_profile",
]


# ---------------------------------------------------------------------------
# Unit: Application owner context (FR-011-02, US2)
# ---------------------------------------------------------------------------


class TestApplicationOwnerContextUnit:
    def test_system_owner_id_is_static_spec_uuid(self):
        """FR-011-02: SYSTEM_OWNER_ID matches specification UUID."""
        assert SYSTEM_OWNER_ID == EXPECTED_OWNER_UUID
        assert str(SYSTEM_OWNER_ID) == "00000000-0000-0000-0000-000000000001"

    def test_application_owner_context_fields(self):
        """Key entity ApplicationOwnerContext exposes owner id and Owner role."""
        ctx = get_application_owner_context()
        assert isinstance(ctx, ApplicationOwnerContext)
        assert ctx.id == EXPECTED_OWNER_UUID
        assert ctx.role == "Owner"
        assert ctx.is_active is True
        assert ctx.email

    def test_preferred_owner_helpers_require_no_request(self):
        """SC-002 / US2: preferred owner helpers need no cookies or headers."""
        assert get_application_owner_context() is SYSTEM_OWNER
        assert get_application_owner_id() == EXPECTED_OWNER_UUID

    def test_legacy_shims_still_return_static_owner(self):
        """Compatibility shims remain callable and always return SYSTEM_OWNER."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert get_current_user() is SYSTEM_OWNER
            assert get_current_user(None) is SYSTEM_OWNER
            assert get_current_active_user() is SYSTEM_OWNER
            assert get_current_user_sync() is SYSTEM_OWNER
            assert get_current_user_id_sync() == EXPECTED_OWNER_UUID

    def test_owner_context_is_stable_across_calls(self):
        """Edge: repeated resolution returns identical static context."""
        a = get_application_owner_context()
        b = get_application_owner_id()
        assert a.id == b == EXPECTED_OWNER_UUID

    def test_owner_context_ignores_request_object(self):
        """Edge: forged Request does not change owner identity."""
        fake_request = MagicMock()
        fake_request.cookies = {"access_token": "forged.jwt.token"}
        fake_request.headers = {"Authorization": "Bearer forged"}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert get_current_user(fake_request).id == EXPECTED_OWNER_UUID
            assert get_current_user_id_sync(fake_request) == EXPECTED_OWNER_UUID


# ---------------------------------------------------------------------------
# Unit: models default to owner (FR-011-02)
# ---------------------------------------------------------------------------


class TestModelOwnerDefaultsUnit:
    def test_broker_token_user_id_default_is_system_owner(self):
        col = BrokerToken.__table__.c.user_id
        assert col.default is not None
        assert col.default.arg == EXPECTED_OWNER_UUID
        # No FK to users table
        fks = list(BrokerToken.__table__.foreign_keys)
        assert not any("users" in str(fk) for fk in fks)

    def test_paper_trading_account_user_id_default_is_system_owner(self):
        col = PaperTradingAccount.__table__.c.user_id
        assert col.default is not None
        assert col.default.arg == EXPECTED_OWNER_UUID
        fks = list(PaperTradingAccount.__table__.foreign_keys)
        assert not any("users" in str(fk) for fk in fks)

    def test_auth_and_profile_models_not_exported_from_models_package(self):
        """FR-011-01: User / UserProfile models are no longer package exports."""
        import app.models as models

        assert not hasattr(models, "User")
        assert not hasattr(models, "UserSession")
        assert not hasattr(models, "UserProfile")
        assert not hasattr(models, "Device")
        assert not hasattr(models, "OTP")
        assert "User" not in models.__all__
        assert "UserProfile" not in models.__all__


# ---------------------------------------------------------------------------
# Unit: removed modules / security surface (FR-010-01, FR-010-02, SC-001)
# ---------------------------------------------------------------------------


class TestAuthSurfaceRemovedUnit:
    @pytest.mark.parametrize("module_name", REMOVED_MODULES)
    def test_removed_auth_modules_are_not_importable(self, module_name: str):
        """FR-010-01 / FR-011-01: deleted multi-user modules must not import."""
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)

    def test_security_module_has_no_jwt_or_password_helpers(self):
        """FR-010-02: JWT encode/decode and password hashing removed from security."""
        from app.core import security

        forbidden = {
            "create_access_token",
            "create_refresh_token",
            "decode_token",
            "verify_password",
            "hash_password",
            "get_password_hash",
            "pwd_context",
        }
        present = {name for name in dir(security) if not name.startswith("_")}
        assert forbidden.isdisjoint(present)

    def test_security_retains_api_key_helpers_for_diagnostics(self):
        """Regression: diagnostics API key gate remains available."""
        from app.core import security

        assert hasattr(security, "APIKeyAuth")
        assert hasattr(security, "verify_api_key")
        assert hasattr(security, "require_api_key")

    def test_audit_service_log_event_is_async_noop_callable(self):
        """FR-012-01: multi-user audit logging is retained as a no-op API."""
        assert callable(AuditService.log_event)
        assert getattr(AuditService.log_event, "__code__", None) is not None


# ---------------------------------------------------------------------------
# Unit: migration script wiring (edge / integration readiness)
# ---------------------------------------------------------------------------


class TestMigrationScriptUnit:
    def test_migration_file_exists_and_chains_from_prior_head(self):
        mig = (
            Path(__file__).resolve().parents[2]
            / "alembic"
            / "versions"
            / "026_remove_multi_user.py"
        )
        assert mig.is_file()
        text = mig.read_text(encoding="utf-8")
        assert "026_remove_multi_user" in text
        assert "down_revision" in text
        assert "20260723_widen_reason_codes" in text
        assert "00000000-0000-0000-0000-000000000001" in text

    def test_migration_drops_multi_user_tables(self):
        mig = (
            Path(__file__).resolve().parents[2]
            / "alembic"
            / "versions"
            / "026_remove_multi_user.py"
        )
        text = mig.read_text(encoding="utf-8")
        for table in (
            "user_profiles",
            "otps",
            "audit_logs",
            "devices",
            "user_sessions",
            "users",
        ):
            assert f"DROP TABLE IF EXISTS {table}" in text

    def test_migration_updates_owner_uuid_before_drop(self):
        mig = (
            Path(__file__).resolve().parents[2]
            / "alembic"
            / "versions"
            / "026_remove_multi_user.py"
        )
        text = mig.read_text(encoding="utf-8")
        assert "UPDATE broker_tokens" in text
        assert "UPDATE paper_trading_accounts" in text
        # Consolidation appears before DROP users
        assert text.index("UPDATE paper_trading_accounts") < text.index(
            "DROP TABLE IF EXISTS users"
        )

    def test_migration_is_multi_row_safe(self):
        """Audit H1: only one paper account bound; broker dedupe before owner assign."""
        mig = (
            Path(__file__).resolve().parents[2]
            / "alembic"
            / "versions"
            / "026_remove_multi_user.py"
        )
        text = mig.read_text(encoding="utf-8")
        assert "SELECT MIN(id) FROM paper_trading_accounts" in text
        assert "DISTINCT ON" in text or "DELETE FROM broker_tokens" in text
        assert "CREATE UNIQUE INDEX IF NOT EXISTS ix_paper_trading_accounts_user_id" in text
        assert "Irreversible" in text or "snapshot" in text.lower()
        assert "pg_dump" not in text  # backup lives in cutover doc; migration warns


# ---------------------------------------------------------------------------
# Integration: HTTP — auth gone, trading/owner APIs open (US1, US2, SC-002)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSingleOwnerApiIntegration:
    async def test_removed_auth_endpoints_return_404(self):
        """FR-010-01: user auth API endpoints are not registered (404)."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for path in REMOVED_AUTH_PATHS:
                for method in ("get", "post", "put", "patch", "delete"):
                    if path.endswith("sessions") and method == "delete":
                        target = f"{path}/1"
                    else:
                        target = path
                    response = await getattr(client, method)(target)
                    # Must not succeed as auth; must not be 401 session gate either
                    assert response.status_code in {404, 405, 422}, (
                        f"{method.upper()} {target} -> {response.status_code}"
                    )
                    assert response.status_code != 401

    async def test_paper_trading_dashboard_does_not_require_auth_headers(self):
        """US2 / SC-002: paper trading reachable without Authorization or cookies."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/paper-trading/dashboard")
            assert response.status_code != 401
            assert response.status_code != 403
            # 200 when DB available; 5xx acceptable for empty/local DB misconfig
            assert response.status_code in {200, 500, 503}

    async def test_paper_trading_account_summary_no_auth_cookie(self):
        """US2: account summary does not redirect or challenge for login."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/paper-trading/account/summary",
                headers={},  # explicitly no Authorization
            )
            assert response.status_code != 401
            assert response.status_code != 403
            assert "login" not in (response.headers.get("location") or "").lower()

    async def test_broker_tokens_list_no_auth_required(self):
        """US2: broker token APIs use static owner context, not JWT."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/broker-tokens/list")
            assert response.status_code != 401
            assert response.status_code != 403
            assert response.status_code in {200, 500, 503}

    async def test_fyers_auth_url_endpoint_preserved(self):
        """FR-013-02 / edge: FYERS OAuth URL endpoint remains registered."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/fyers/auth/url")
            assert response.status_code == 200
            body = response.json()
            assert "oauth_available" in body
            assert "auth_url" in body

    async def test_fyers_auth_exchange_requires_auth_code_not_user_jwt(self):
        """Failure: exchange without auth_code is 400 domain error, not 401 user auth."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/fyers/auth/exchange", json={})
            assert response.status_code == 400
            assert response.status_code != 401
            detail = response.json().get("detail", "")
            assert "auth_code" in str(detail).lower()

    async def test_governance_routes_endpoint_preserved(self):
        """Regression / quickstart scenario 4: governance routes stay available."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/governance/routes")
            assert response.status_code == 200
            body = response.json()
            # Flexible shape: dict of routes or wrapper with routes/count
            if isinstance(body, dict) and "routes" in body:
                routes = body["routes"]
            else:
                routes = body
            assert isinstance(routes, dict)
            assert "experiment.start" in routes or len(routes) > 0

    async def test_health_endpoint_open(self):
        """Regression: health remains open without session."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
            assert response.status_code != 401
            assert response.status_code in {200, 503}

    async def test_scanner_latest_no_user_session_required(self):
        """FR-013-01 / SC-002: scanner does not demand user JWT."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/scanner/latest")
            assert response.status_code != 401
            assert response.status_code != 403


# ---------------------------------------------------------------------------
# Integration: DI wiring for paper trading service (US2)
# ---------------------------------------------------------------------------


class TestPaperTradingOwnerWiringUnit:
    def test_get_service_dependency_uses_system_owner_id(self):
        """US2: paper trading route DI injects SYSTEM_OWNER_ID."""
        from app.routes.paper_trading import get_service
        from app.services.paper_trading_service import PaperTradingService

        mock_db = MagicMock()
        # Call underlying callable with resolved deps (FastAPI Depends not applied)
        svc = get_service(user_id=get_application_owner_id(), db=mock_db)
        assert isinstance(svc, PaperTradingService)
        assert svc.user_id == EXPECTED_OWNER_UUID

    def test_paper_service_with_system_owner_scopes_account_query(self):
        """US2: service constructed with owner UUID targets owner account only."""
        from app.services.paper_trading_service import PaperTradingService

        mock_db = MagicMock()
        svc = PaperTradingService(mock_db, user_id=SYSTEM_OWNER_ID)
        assert svc.user_id == EXPECTED_OWNER_UUID


# ---------------------------------------------------------------------------
# Regression: preserved trading / permission modules (FR-013-01, FR-013-02)
# ---------------------------------------------------------------------------


class TestPreservedTradingModulesRegression:
    def test_market_permission_service_still_importable(self):
        """FR-013-02: MarketPermissionService must not be removed with user auth."""
        from app.services.market_permission_service import MarketPermissionService

        assert MarketPermissionService is not None

    def test_recommendation_and_scanner_services_importable(self):
        """FR-013-01: core trading services remain."""
        from app.services.recommendation_service import RecommendationService
        from app.services.screener_service import ScreenerService
        from app.services.scan_execution_service import ScanExecutionService
        from app.services.paper_trading_service import PaperTradingService
        from app.services.broker_token_service import save_token  # noqa: F401

        assert RecommendationService is not None
        assert ScreenerService is not None
        assert ScanExecutionService is not None
        assert PaperTradingService is not None

    def test_auth_router_not_included_in_api_router(self):
        """FR-010-01: routes package does not mount auth_router."""
        from app.routes import api_router

        paths = {
            getattr(r, "path", "") or ""
            for r in api_router.routes
        }
        auth_paths = [p for p in paths if "/auth/" in p and "fyers" not in p]
        assert auth_paths == []

    def test_main_app_registers_fyers_but_not_user_auth(self):
        """Edge + FR-013-02: /fyers/auth/* present; /api/v1/auth/* absent."""
        route_paths = {
            getattr(r, "path", None)
            for r in app.routes
            if getattr(r, "path", None)
        }
        assert "/fyers/auth/url" in route_paths
        assert "/fyers/auth/exchange" in route_paths
        assert not any(
            p.startswith("/api/v1/auth") or p.startswith("/auth/login")
            for p in route_paths
            if p
        )


# ---------------------------------------------------------------------------
# Failure / edge: invalid broker ops still domain errors, not session errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBrokerFailurePathsNoUserAuth:
    async def test_broker_token_create_empty_payload_not_401(self):
        """Failure: invalid body yields 4xx domain validation, never 401 login."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/broker-tokens", json={})
            assert response.status_code != 401
            assert response.status_code != 403
            # 422 validation or 400 business rule or 500 if DB unavailable
            assert response.status_code in {400, 422, 500, 503}

    async def test_paper_order_without_body_not_401(self):
        """Failure: missing order body is not an auth failure."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/paper-trading/orders", json={})
            assert response.status_code != 401
            assert response.status_code != 403
            assert response.status_code in {400, 422, 500, 503}


# ---------------------------------------------------------------------------
# Async audit no-op (edge)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_event_async_noop():
    """Edge: audit log_event completes without writing multi-user audit rows."""
    result = await AuditService.log_event(
        db=AsyncMock(),
        user_id=None,
        event_type="password_reset",
        metadata={"ip": "127.0.0.1"},
    )
    assert result is None


# ---------------------------------------------------------------------------
# Production fail-closed gates (audit H2 / M7)
# ---------------------------------------------------------------------------


class TestProductionSecurityGatesUnit:
    def test_token_crypto_requires_key_in_production(self, monkeypatch):
        from app.core import token_crypto

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        token_crypto.reset_fernet_cache()
        with pytest.raises(RuntimeError, match="TOKEN_ENCRYPTION_KEY"):
            token_crypto.encrypt_secret("plain-token")
        token_crypto.reset_fernet_cache()

    def test_token_crypto_rejects_jwt_secret_fallback_in_production(self, monkeypatch):
        from app.core import token_crypto

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("JWT_SECRET", "legacy-only")
        token_crypto.reset_fernet_cache()
        with pytest.raises(RuntimeError, match="TOKEN_ENCRYPTION_KEY"):
            token_crypto.encrypt_secret("plain-token")
        token_crypto.reset_fernet_cache()

    def test_token_crypto_works_with_explicit_key(self, monkeypatch):
        from app.core import token_crypto

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "unit-test-production-key-32b!!")
        token_crypto.reset_fernet_cache()
        cipher = token_crypto.encrypt_secret("secret-value")
        assert cipher and cipher.startswith("enc:v1:")
        assert token_crypto.decrypt_secret(cipher) == "secret-value"
        token_crypto.reset_fernet_cache()

    def test_api_key_auth_fail_closed_when_missing_in_production(self, monkeypatch):
        from app.core.security import APIKeyAuth
        from fastapi import HTTPException

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("API_KEY", raising=False)
        auth = APIKeyAuth(api_key="")
        with pytest.raises(HTTPException) as exc:
            auth(None)
        assert exc.value.status_code == 503

    def test_api_key_auth_open_when_unset_in_development(self, monkeypatch):
        from app.core.security import APIKeyAuth

        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("API_KEY", raising=False)
        assert APIKeyAuth(api_key="")(None) is True

    def test_settings_production_requires_secrets(self, monkeypatch):
        """Production gate rejects missing TOKEN_ENCRYPTION_KEY / API_KEY."""
        from app.config.settings import Settings

        monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("API_KEY", raising=False)
        stub = Settings.model_construct(
            app_env="production",
            token_encryption_key="",
            operator_api_key="",
        )
        with pytest.raises(ValueError, match="Production single-owner"):
            Settings._production_security_gates(stub)

    def test_passlib_not_listed_as_runtime_import(self):
        """FR-010-02: passlib must not be an application dependency."""
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("app.services.auth_service")
        # passlib may still be installed in the venv historically; app must not import it.
        import app.core.security as security_mod

        src = Path(security_mod.__file__).read_text(encoding="utf-8")
        assert "passlib" not in src
        assert "bcrypt" not in src
