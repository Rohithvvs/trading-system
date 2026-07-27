"""Feature flag toggle and runtime fallback tests for unified latest scan.

Maps to US3, AC-004, FR-006..FR-008, FR-017, failure-path handling.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import settings
from app.main import app
from app.tests.cache_test_utils import (
    set_scanner_cache_enabled,
    set_scanner_unified_latest_enabled,
)


# ---------------------------------------------------------------------------
# Settings live evaluation (FR-006, AC-004)
# ---------------------------------------------------------------------------


def test_is_scanner_unified_latest_enabled_reads_env(monkeypatch):
    """FR-006: Live env evaluation without process restart."""
    monkeypatch.delenv("SCANNER_UNIFIED_LATEST_ENABLED", raising=False)
    monkeypatch.setattr(settings, "scanner_unified_latest_enabled", False)
    assert settings.is_scanner_unified_latest_enabled() is False

    monkeypatch.setenv("SCANNER_UNIFIED_LATEST_ENABLED", "true")
    assert settings.is_scanner_unified_latest_enabled() is True

    monkeypatch.setenv("SCANNER_UNIFIED_LATEST_ENABLED", "false")
    assert settings.is_scanner_unified_latest_enabled() is False

    monkeypatch.setenv("SCANNER_UNIFIED_LATEST_ENABLED", "1")
    assert settings.is_scanner_unified_latest_enabled() is True

    monkeypatch.setenv("SCANNER_UNIFIED_LATEST_ENABLED", "yes")
    assert settings.is_scanner_unified_latest_enabled() is True


def test_is_scanner_unified_latest_enabled_attribute_fallback(monkeypatch):
    """When env unset, attribute value is used."""
    monkeypatch.delenv("SCANNER_UNIFIED_LATEST_ENABLED", raising=False)
    monkeypatch.setattr(settings, "scanner_unified_latest_enabled", True)
    assert settings.is_scanner_unified_latest_enabled() is True
    monkeypatch.setattr(settings, "scanner_unified_latest_enabled", False)
    assert settings.is_scanner_unified_latest_enabled() is False


# ---------------------------------------------------------------------------
# Dynamic toggle without restart (AC-004 / T013)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feature_flag_dynamic_toggle(monkeypatch):
    """US3 / T013: Runtime OFF → ON → OFF switching returns 200 each step."""
    set_scanner_cache_enabled(monkeypatch, False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        set_scanner_unified_latest_enabled(monkeypatch, False)
        res_off = await client.get("/scanner/latest")
        assert res_off.status_code == 200

        set_scanner_unified_latest_enabled(monkeypatch, True)
        res_on = await client.get("/scanner/latest")
        assert res_on.status_code == 200

        set_scanner_unified_latest_enabled(monkeypatch, False)
        res_rollback = await client.get("/scanner/latest")
        assert res_rollback.status_code == 200


@pytest.mark.asyncio
async def test_feature_flag_dynamic_toggle_analysis_endpoint(monkeypatch):
    """US3: Same zero-downtime toggle for GET /analysis/scan/latest."""
    set_scanner_cache_enabled(monkeypatch, False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        set_scanner_unified_latest_enabled(monkeypatch, False)
        assert (await client.get("/analysis/scan/latest")).status_code == 200

        set_scanner_unified_latest_enabled(monkeypatch, True)
        assert (await client.get("/analysis/scan/latest")).status_code == 200

        set_scanner_unified_latest_enabled(monkeypatch, False)
        assert (await client.get("/analysis/scan/latest")).status_code == 200


@pytest.mark.asyncio
async def test_toggle_switches_execution_path(monkeypatch):
    """AC-004: OFF does not call get_latest_scan; ON does."""
    set_scanner_cache_enabled(monkeypatch, False)
    empty_dash = json.dumps(
        {
            "message": "No completed scans found",
            "buy_candidates": [],
            "watch_candidates": [],
            "rejected_candidates": [],
        }
    )

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_scan",
        new_callable=AsyncMock,
        return_value=(empty_dash, "BYPASS"),
    ) as unified_mock:
        with patch(
            "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                set_scanner_unified_latest_enabled(monkeypatch, False)
                await client.get("/scanner/latest")
                assert unified_mock.await_count == 0

                set_scanner_unified_latest_enabled(monkeypatch, True)
                await client.get("/scanner/latest")
                assert unified_mock.await_count == 1

                set_scanner_unified_latest_enabled(monkeypatch, False)
                await client.get("/scanner/latest")
                assert unified_mock.await_count == 1  # no additional call


# ---------------------------------------------------------------------------
# Exception fallback to legacy (T014 / FR-017 failure path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unified_service_exception_fallback(monkeypatch):
    """US3 / T014: Exception in unified service falls back to legacy path (HTTP 200)."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, False)

    from app.observability import metrics as metrics_mod

    before = metrics_mod._unified_latest_fallbacks

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_scan",
        side_effect=RuntimeError("Simulated Service Error"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res_scanner = await client.get("/scanner/latest")
            assert res_scanner.status_code == 200
            # Legacy empty dashboard contract
            body = res_scanner.json()
            assert "buy_candidates" in body or "message" in body

            res_analysis = await client.get("/analysis/scan/latest")
            assert res_analysis.status_code == 200
            assert "available" in res_analysis.json()

    assert metrics_mod._unified_latest_fallbacks >= before + 2


@pytest.mark.asyncio
async def test_unified_service_exception_fallback_scanner_uses_legacy_empty(monkeypatch):
    """Failure path: after unified error, legacy empty dashboard message is returned."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, False)

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_scan",
        side_effect=RuntimeError("boom"),
    ):
        with patch(
            "app.services.latest_scan_service.LatestScanService.get_latest_completed_scan",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get("/scanner/latest")

    assert res.status_code == 200
    assert res.json()["message"] == "No completed scans found"
    assert res.json()["buy_candidates"] == []


@pytest.mark.asyncio
async def test_unified_service_exception_fallback_analysis_uses_legacy_empty(monkeypatch):
    """Failure path: after unified error, analysis legacy empty available=false."""
    set_scanner_unified_latest_enabled(monkeypatch, True)
    set_scanner_cache_enabled(monkeypatch, False)

    with patch(
        "app.services.latest_scan_service.LatestScanService.get_latest_scan",
        side_effect=RuntimeError("boom"),
    ):
        with patch(
            "app.routes.analysis.load_latest_scan",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get("/analysis/scan/latest")

    assert res.status_code == 200
    assert res.json() == {"available": False}


@pytest.mark.asyncio
async def test_both_endpoints_survive_rapid_flag_flips(monkeypatch):
    """Regression / reliability: rapid flag flips do not produce non-200 responses."""
    set_scanner_cache_enabled(monkeypatch, False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(6):
            set_scanner_unified_latest_enabled(monkeypatch, i % 2 == 0)
            r1 = await client.get("/scanner/latest")
            r2 = await client.get("/analysis/scan/latest")
            assert r1.status_code == 200
            assert r2.status_code == 200
            assert "x-cache-status" in r1.headers
            assert "x-cache-status" in r2.headers
