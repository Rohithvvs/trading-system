"""RE-001 engine registration from settings."""

from __future__ import annotations

from ...config.settings import settings
from ...schemas.re001 import Re001Registration, Re001Stage


def get_re001_registration() -> Re001Registration:
    stage = (settings.re001_stage or "OFF").strip().upper()
    if stage not in {"OFF", "LAB_SHADOW", "PAPER_LINKED"}:
        stage = "OFF"
    return Re001Registration(
        engine_id="RE-001",
        name="Trend Continuation Recommendation Engine",
        engine_version=settings.re001_version or "1.0",
        stage=stage,  # type: ignore[arg-type]
        enabled=bool(settings.re001_enabled),
    )


def is_re001_active() -> bool:
    """True when RE-001 should evaluate (enabled and stage is a lab stage)."""
    if not bool(settings.re001_enabled):
        return False
    stage = (settings.re001_stage or "OFF").strip().upper()
    return stage in {"LAB_SHADOW", "PAPER_LINKED"}
