"""Failure paths: runner timeout returns diagnostic Decision Object (FR-012 / H5)."""

import asyncio
import time

from app.services.re001 import runner as runner_mod
from app.services.re001.runner import run_re001_isolated_async


def test_timeout_returns_diagnostic(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "re001_enabled", True)
    monkeypatch.setattr(settings, "re001_stage", "LAB_SHADOW")
    monkeypatch.setattr(settings, "re001_timeout_ms", 50)
    monkeypatch.setattr(settings, "re001_persist_decisions", False)

    def slow(*_a, **_k):
        time.sleep(0.5)
        raise AssertionError("should have timed out")

    monkeypatch.setattr(runner_mod, "_evaluate_sync", slow)

    async def _run():
        return await run_re001_isolated_async(symbol="TIMEOUT")

    out = asyncio.run(_run())
    assert out is not None
    assert out.evaluation_status == "timeout"
    assert out.recommendation_state == "REJECT"
    assert "re001_timeout" in (out.reason_codes or [])


def test_active_stage_paper_linked(monkeypatch):
    from app.config import settings
    from app.services.re001.registry import is_re001_active

    monkeypatch.setattr(settings, "re001_enabled", True)
    monkeypatch.setattr(settings, "re001_stage", "PAPER_LINKED")
    assert is_re001_active() is True
