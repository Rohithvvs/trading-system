import os
import pytest
from pydantic import ValidationError
from backend.app.config.settings import Settings


def test_settings_mutation_validates_env(monkeypatch: pytest.MonkeyPatch):
    """
    Programmatically mutate environment variables.
    Assert the backend safely rejects impossible variables via Pydantic Settings
    and validates the fallback paths.
    """
    # Bare sqlite path is accepted as-is (no automatic sqlite:/// prefixing).
    monkeypatch.setenv("DATABASE_URL", "custom_db.sqlite3")
    s1 = Settings(_env_file=None)
    assert s1.database_url == "custom_db.sqlite3"

    # Empty DATABASE_URL falls back to the Settings validator default.
    monkeypatch.setenv("DATABASE_URL", "")
    s2 = Settings(_env_file=None)
    assert s2.database_url == (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_system"
    )

    # Reject impossible typed variables.
    monkeypatch.setenv("APP_PORT", "not_an_integer")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)

    assert "Input should be a valid integer" in str(exc.value)

    # Cleanup for process-level safety (monkeypatch also restores after test).
    monkeypatch.delenv("APP_PORT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
