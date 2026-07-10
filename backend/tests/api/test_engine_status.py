import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock

from backend.app.main import app
from backend.app.services.paper_trading_service import PaperTradingService
from backend.app.routes.paper_trading import get_service

@pytest.fixture
def test_client():
    return TestClient(app)

@pytest.fixture
def mock_service():
    service = MagicMock(spec=PaperTradingService)
    service.get_engine_status = AsyncMock()
    app.dependency_overrides[get_service] = lambda: service
    yield service
    app.dependency_overrides.clear()

def test_engine_status_success_running(test_client, mock_service):
    """
    TEST CATEGORY 8 — ENGINE STATUS API
    Case 2: Engine running
    """
    mock_service.get_engine_status.return_value = {
        "status": "RUNNING",
        "open_positions": 5,
        "tracked_symbols": 3,
        "last_tick_at": "2023-01-01T10:00:00Z",
        "last_reconciliation_at": "2023-01-01T10:00:00Z"
    }
    
    response = test_client.get("/paper-trading/engine-status")
    assert response.status_code == 200
    assert response.json()["status"] == "RUNNING"
    assert response.json()["open_positions"] == 5

def test_engine_status_success_stopped(test_client, mock_service):
    """
    TEST CATEGORY 8 — ENGINE STATUS API
    Case 3: Engine stopped
    """
    mock_service.get_engine_status.return_value = {
        "status": "STOPPED",
        "open_positions": 0,
        "tracked_symbols": 0,
        "last_tick_at": None,
        "last_reconciliation_at": None
    }
    
    response = test_client.get("/paper-trading/engine-status")
    assert response.status_code == 200
    assert response.json()["status"] == "STOPPED"

def test_engine_status_no_positions(test_client, mock_service):
    """
    TEST CATEGORY 8 — ENGINE STATUS API
    Case 1: No positions exist
    """
    mock_service.get_engine_status.return_value = {
        "status": "RUNNING",
        "open_positions": 0,
        "tracked_symbols": 0,
        "last_tick_at": "2023-01-01T10:00:00Z",
        "last_reconciliation_at": "2023-01-01T10:00:00Z"
    }
    
    response = test_client.get("/paper-trading/engine-status")
    assert response.status_code == 200
    assert response.json()["open_positions"] == 0

def test_engine_status_db_unavailable(test_client, mock_service):
    """
    TEST CATEGORY 8 — ENGINE STATUS API
    Case 5: Database unavailable
    """
    mock_service.get_engine_status.side_effect = Exception("DB Connection Refused")
    
    response = test_client.get("/paper-trading/engine-status")
    assert response.status_code == 500
    assert "Internal Server Error" in response.json()["detail"]
