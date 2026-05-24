import os
import pytest
from pydantic import ValidationError
from backend.app.config.settings import Settings

def test_settings_mutation_validates_env():
    """
    Programmatically mutate environment variables.
    Assert the backend safely rejects impossible variables via Pydantic Settings 
    and validates the fallback paths.
    """
    # Test fallback path for database_url normalizer
    os.environ["DATABASE_URL"] = "custom_db.sqlite3"
    s1 = Settings()
    assert s1.database_url == "sqlite:///./custom_db.sqlite3"
    
    os.environ["DATABASE_URL"] = ""
    s2 = Settings()
    assert s2.database_url == "sqlite:///./trading_system.db"
    
    # Test rejecting impossible variables
    # Since we use pydantic BaseSettings, passing invalid types throws ValidationError
    os.environ["APP_PORT"] = "not_an_integer"
    with pytest.raises(ValidationError) as exc:
        Settings()
    
    assert "Input should be a valid integer" in str(exc.value)

    # Clean up
    del os.environ["APP_PORT"]
    del os.environ["DATABASE_URL"]
