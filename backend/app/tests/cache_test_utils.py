"""Shared helpers for scanner dashboard cache tests."""

from __future__ import annotations


def set_scanner_cache_enabled(monkeypatch, enabled: bool) -> None:
    """Toggle cache flag for tests (env + settings attribute stay in sync).

    ``settings.is_scanner_latest_cache_enabled()`` re-reads ``os.environ`` on every
    call, so tests must set both the env var and the settings attribute.
    """
    from app.config.settings import settings

    monkeypatch.setenv(
        "SCANNER_LATEST_CACHE_ENABLED", "true" if enabled else "false"
    )
    monkeypatch.setattr(settings, "scanner_latest_cache_enabled", enabled)
