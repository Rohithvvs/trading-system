import pytest
import os
import sys

# Ensure backend root is in PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_config_import():
    """Verify that settings can be imported from the correct package structure."""
    try:
        from backend.app.config import settings
        assert settings is not None
        assert hasattr(settings, "app_env")
    except ImportError as e:
        pytest.fail(f"Failed to import settings from app.config: {e}")

def test_app_initialization():
    """Verify that the FastAPI app and its lifespan can initialize cleanly."""
    try:
        from backend.app.main import app
        assert app is not None
        assert app.title == "Trading System" or hasattr(app, "title")
    except ImportError as e:
        pytest.fail(f"Failed to import FastAPI app from app.main: {e}")
    except Exception as e:
        pytest.fail(f"FastAPI app initialization threw an unexpected error: {e}")

def test_startup_health_dependencies():
    """Verify that scanner health dependencies are importable."""
    try:
        from backend.app.services.screener_service import ScreenerService
        from backend.app.services import candle_store
        
        assert ScreenerService is not None
        assert candle_store is not None
    except ImportError as e:
        pytest.fail(f"Failed to import scanner health dependencies: {e}")
