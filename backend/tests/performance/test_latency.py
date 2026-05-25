import pytest
import time
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Import the FastAPI application
from backend.app.main import app

client = TestClient(app)

@pytest.fixture
def mock_router_agent_fast():
    with patch("backend.app.routes.analysis.RouterAgent") as mock_router:
        mock_instance = mock_router.return_value
        
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "items": [],
            "generated_at": "2023-10-01T10:00:00Z"
        }
        mock_instance.full_analysis.return_value = mock_response
        yield mock_router

def test_api_latency_under_100ms(mock_router_agent_fast):
    # Testing the strict HTTP parsing and validation latency of the FastAPI layer
    # Since the agent logic is mocked, this isolates the network serialization overhead.
    
    payload = {
        "symbols": ["TCS.NS", "INFY.NS", "RELIANCE.NS"],
        "mode": "swing",
        "timeframe": {
            "intraday": "5m",
            "swing": "1D",
            "lookback_window": 180
        }
    }

    start_time = time.time()
    response = client.post("/analysis/full", json=payload)
    end_time = time.time()
    
    assert response.status_code == 200
    
    # Latency should be well under 100ms for pure HTTP routing and Pydantic validation
    latency_ms = (end_time - start_time) * 1000
    assert latency_ms < 100.0, f"API Routing Latency too high: {latency_ms:.2f}ms"
