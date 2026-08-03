"""RE-001 isolation: timeout/errors never raise into caller path via runner."""

import asyncio

from app.services.re001.runner import run_re001_isolated, run_re001_isolated_async


def test_runner_returns_none_when_inactive(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "re001_enabled", False)
    out = run_re001_isolated(symbol="X")
    assert out is None


def test_runner_swallows_engine_errors(monkeypatch):
    from app.config import settings
    from app.services.re001 import runner as runner_mod

    monkeypatch.setattr(settings, "re001_enabled", True)
    monkeypatch.setattr(settings, "re001_stage", "LAB_SHADOW")
    monkeypatch.setattr(settings, "re001_timeout_ms", 5000)
    monkeypatch.setattr(settings, "re001_persist_decisions", False)

    def boom(*_a, **_k):
        raise RuntimeError("forced")

    monkeypatch.setattr(runner_mod, "_evaluate_sync", boom)
    out = run_re001_isolated(symbol="X", market_regime=None)
    # H5: diagnostic Decision Object with evaluation_status=error (not raise)
    assert out is not None
    assert out.evaluation_status == "error"
    assert out.recommendation_state == "REJECT"


def test_async_runner_inactive(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "re001_enabled", False)

    async def _run():
        return await run_re001_isolated_async(symbol="Y")

    assert asyncio.run(_run()) is None
