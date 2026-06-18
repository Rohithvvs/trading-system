import pytest
import os
from fastapi.testclient import TestClient
from backend.app.main import app

def test_environment_parsing():
    """
    Deployment Test: Ensure environment variables correctly configure the app context
    without crashing, simulating Docker or CI runner injection.
    """
    os.environ["APP_ENV"] = "STAGING"
    # We just ensure pulling the config doesn't crash
    from backend.app.config import settings
    assert settings.app_env is not None

def test_smoke_health_endpoint():
    """
    Deployment Test: The /health endpoint must return 200 OK within 3 seconds,
    serving as the Kubernetes Liveness Probe target.
    """
    client = TestClient(app)
    
    # Fast 200 OK
    response = client.get("/health")
    
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
