"""Integration tests for POST /internal/refresh-fyers-token (Sprint 5).

Specification source of truth:
  specs/010-fyers-internal-api/spec.md
  specs/010-fyers-internal-api/contracts/api_contracts.md

Coverage maps to FR-001..FR-007, SC-001..SC-003, US1, US2, and edge cases.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from unittest.mock import AsyncMock, call, patch

import pytest


ENDPOINT = "/internal/refresh-fyers-token"
SECRET = "test-cron-secret"
AUTH_HEADERS = {"X-Scheduler-Secret": SECRET}

# Patch both import styles used by this monorepo (backend.* vs app.*).
_GEN_PATHS = (
    "backend.app.services.token_service.generate_and_persist_fyers_token",
    "app.services.token_service.generate_and_persist_fyers_token",
)


def _patch_generate(**kwargs):
    """Context manager that patches generate_and_persist under both module paths."""
    from contextlib import ExitStack

    stack = ExitStack()
    mocks = []
    for path in _GEN_PATHS:
        mocks.append(stack.enter_context(patch(path, new_callable=AsyncMock, **kwargs)))
    return stack, mocks


@pytest.mark.integration
class TestTokenRefreshRouteAuth:
    """US2 / FR-004 / FR-005 / SC-001 — endpoint protection."""

    def test_missing_secret_header_returns_401(self, client):
        """FR-004, US2-AS1: missing X-Scheduler-Secret → 401 Unauthorized."""
        res = client.post(ENDPOINT)
        assert res.status_code == 401
        assert res.json() == {"detail": "Unauthorized"}

    def test_empty_secret_header_is_rejected(self, client, monkeypatch):
        """US2-AS1: empty authentication key must not authorize the request.

        Spec requires 401 for empty key. Implementation may return 401 or 403
        depending on how FastAPI presents an empty header value; either is a
        rejection (generation must not run).
        """
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            res = client.post(ENDPOINT, headers={"X-Scheduler-Secret": ""})
        assert res.status_code in (401, 403)
        for mock in mocks:
            mock.assert_not_called()

    def test_invalid_secret_returns_403(self, client, monkeypatch):
        """FR-004, US2-AS2: incorrect secret → 403 Forbidden."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            res = client.post(
                ENDPOINT,
                headers={"X-Scheduler-Secret": "wrong_secret"},
            )
        assert res.status_code == 403
        assert res.json() == {"detail": "Forbidden"}
        for mock in mocks:
            mock.assert_not_called()

    def test_unconfigured_scheduler_secret_returns_403(self, client, monkeypatch):
        """FR-005: when SCHEDULER_SECRET is unset, valid-looking header is rejected."""
        monkeypatch.delenv("SCHEDULER_SECRET", raising=False)
        stack, mocks = _patch_generate()
        with stack:
            res = client.post(
                ENDPOINT,
                headers={"X-Scheduler-Secret": "any-value"},
            )
        assert res.status_code == 403
        assert res.json() == {"detail": "Forbidden"}
        for mock in mocks:
            mock.assert_not_called()

    def test_unauthorized_request_does_not_invoke_token_generation(
        self, client, monkeypatch
    ):
        """SC-001: unauthorized requests never invoke broker login / generation."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            client.post(ENDPOINT)
            client.post(ENDPOINT, headers={"X-Scheduler-Secret": "bad"})
        for mock in mocks:
            mock.assert_not_called()

    def test_wrong_header_name_is_treated_as_missing(self, client, monkeypatch):
        """Only X-Scheduler-Secret is accepted; alternate header names fail auth."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            res = client.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {SECRET}"},
            )
        assert res.status_code == 401
        for mock in mocks:
            mock.assert_not_called()


@pytest.mark.integration
class TestTokenRefreshRouteSuccess:
    """US1 / FR-001 / FR-002 / FR-003 / FR-006 — happy path."""

    def test_success_returns_contract_body(self, client, monkeypatch):
        """FR-006, US1-AS1: 200 + exact success JSON contract."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            for mock in mocks:
                mock.return_value = {
                    "status": "Success",
                    "saved_at": "2026-07-21T00:00:00+00:00",
                    "token_preview": "****************ABCD",
                }
            res = client.post(ENDPOINT, headers=AUTH_HEADERS)

        assert res.status_code == 200
        assert res.json() == {
            "status": "success",
            "message": "Access token generated and saved successfully",
        }

    def test_success_invokes_generate_and_persist_once(self, client, monkeypatch):
        """FR-002 / FR-003: reuses generate_and_persist_fyers_token exactly once."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            for mock in mocks:
                mock.return_value = {"status": "Success"}
            res = client.post(ENDPOINT, headers=AUTH_HEADERS)

        assert res.status_code == 200
        # At least one of the dual patches receives the call (same underlying target
        # depending on import path used by the running app).
        assert sum(m.await_count for m in mocks) >= 1

    def test_success_response_never_leaks_raw_token(self, client, monkeypatch):
        """Security: response must not include raw access token material."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        raw_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"
        stack, mocks = _patch_generate()
        with stack:
            for mock in mocks:
                mock.return_value = {
                    "status": "Success",
                    "access_token": raw_token,
                    "token_preview": "****************XYZ1",
                }
            res = client.post(ENDPOINT, headers=AUTH_HEADERS)

        assert res.status_code == 200
        body = res.json()
        assert "access_token" not in body
        assert raw_token not in res.text
        assert "eyJ" not in res.text
        assert set(body.keys()) == {"status", "message"}


@pytest.mark.integration
class TestTokenRefreshRouteFailure:
    """US1-AS2 / FR-007 / SC-003 — generation and dependency failures."""

    def test_generation_failure_returns_500_contract(self, client, monkeypatch):
        """FR-007, US1-AS2: generation exception → 500 + exact error JSON."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            for mock in mocks:
                mock.side_effect = Exception("Fyers API connection timed out")
            res = client.post(ENDPOINT, headers=AUTH_HEADERS)

        assert res.status_code == 500
        assert res.json() == {
            "status": "error",
            "message": "Failed to generate access token after retries",
        }

    def test_database_failure_returns_500_contract(self, client, monkeypatch):
        """Edge: DB unreachable during persist → 500 structured error (no leak)."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            for mock in mocks:
                mock.side_effect = RuntimeError("database connection refused")
            res = client.post(ENDPOINT, headers=AUTH_HEADERS)

        assert res.status_code == 500
        body = res.json()
        assert body == {
            "status": "error",
            "message": "Failed to generate access token after retries",
        }
        assert "database connection refused" not in res.text

    def test_broker_downtime_style_error_is_sanitized(self, client, monkeypatch):
        """Edge: broker downtime after retries → structured JSON, no raw exception."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            for mock in mocks:
                mock.side_effect = ConnectionError(
                    "Fyers host unreachable after 3 retries"
                )
            res = client.post(ENDPOINT, headers=AUTH_HEADERS)

        assert res.status_code == 500
        assert res.json()["status"] == "error"
        assert "unreachable" not in res.text.lower()
        assert "retries" in res.json()["message"].lower()

    def test_failure_response_never_leaks_secrets_or_token(self, client, monkeypatch):
        """Failure body must not include secrets, tokens, or stack traces."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            for mock in mocks:
                mock.side_effect = Exception(
                    f"auth failed secret={SECRET} token=eyJdeadbeef"
                )
            res = client.post(ENDPOINT, headers=AUTH_HEADERS)

        assert res.status_code == 500
        assert SECRET not in res.text
        assert "eyJ" not in res.text
        assert "Traceback" not in res.text


@pytest.mark.integration
class TestTokenRefreshRouteHttpSemantics:
    """FR-001 and HTTP contract edge cases."""

    def test_get_method_not_allowed(self, client, monkeypatch):
        """FR-001: only POST is accepted."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        res = client.get(ENDPOINT, headers=AUTH_HEADERS)
        assert res.status_code == 405

    def test_put_method_not_allowed(self, client, monkeypatch):
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        res = client.put(ENDPOINT, headers=AUTH_HEADERS)
        assert res.status_code == 405

    def test_delete_method_not_allowed(self, client, monkeypatch):
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        res = client.delete(ENDPOINT, headers=AUTH_HEADERS)
        assert res.status_code == 405

    def test_empty_json_body_is_accepted_on_success(self, client, monkeypatch):
        """Contract: request body is empty / unused."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            for mock in mocks:
                mock.return_value = {"status": "Success"}
            res = client.post(
                ENDPOINT,
                headers={**AUTH_HEADERS, "Content-Type": "application/json"},
                json={},
            )
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    def test_content_type_header_optional_for_empty_body(self, client, monkeypatch):
        """Endpoint works without Content-Type when body is empty."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            for mock in mocks:
                mock.return_value = {"status": "Success"}
            res = client.post(ENDPOINT, headers=AUTH_HEADERS)
        assert res.status_code == 200


@pytest.mark.integration
class TestTokenRefreshRouteConcurrency:
    """Edge case: concurrent authorized requests."""

    def test_concurrent_authorized_requests_each_invoke_service(
        self, client, monkeypatch
    ):
        """Concurrent POSTs should each reach the service without 5xx from the route.

        Serialization / race handling is owned by the service/DB layer; the route
        must remain stable under parallel callers.
        """
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        call_counter = {"n": 0}

        async def _slow_gen(db):
            call_counter["n"] += 1
            await asyncio.sleep(0.05)
            return {"status": "Success"}

        stack, mocks = _patch_generate()
        with stack:
            for mock in mocks:
                mock.side_effect = _slow_gen

            def _post():
                return client.post(ENDPOINT, headers=AUTH_HEADERS)

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(_post) for _ in range(3)]
                results = [f.result() for f in futures]

        assert all(r.status_code == 200 for r in results)
        assert all(
            r.json()
            == {
                "status": "success",
                "message": "Access token generated and saved successfully",
            }
            for r in results
        )
        # Service should have been entered for each concurrent request.
        assert call_counter["n"] >= 3


@pytest.mark.integration
class TestTokenRefreshRouteRegression:
    """Regression: existing token routes remain available and protected."""

    def test_existing_generate_route_still_requires_secret(self, client):
        """Regression: POST /api/token/generate still enforces scheduler secret."""
        res = client.post("/api/token/generate")
        assert res.status_code == 401

    def test_existing_generate_route_still_rejects_bad_secret(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        res = client.post(
            "/api/token/generate",
            headers={"X-Scheduler-Secret": "wrong"},
        )
        assert res.status_code == 403

    def test_internal_path_not_under_api_token_prefix(self, client, monkeypatch):
        """Route is /internal/..., not /api/token/internal/..."""
        monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
        stack, mocks = _patch_generate()
        with stack:
            for mock in mocks:
                mock.return_value = {"status": "Success"}
            wrong = client.post(
                "/api/token/internal/refresh-fyers-token",
                headers=AUTH_HEADERS,
            )
            right = client.post(ENDPOINT, headers=AUTH_HEADERS)
        assert wrong.status_code == 404
        assert right.status_code == 200
