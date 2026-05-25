import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Import the FastAPI application
from backend.app.main import app

client = TestClient(app)

@pytest.fixture
def mock_fyers():
    with patch("backend.app.services.screener_service.FyersService") as mock_fyers_service:
        yield mock_fyers_service

@pytest.fixture
def mock_router_agent():
    with patch("backend.app.routes.analysis.RouterAgent") as mock_router:
        yield mock_router

def test_full_analysis_endpoint(mock_router_agent):
    # Mock the returned FullAnalysisResponse from the Agent
    mock_instance = mock_router_agent.return_value
    
    mock_response = MagicMock()
    mock_response.model_dump.return_value = {
        "items": [
            {
                "symbol": "TCS.NS",
                "score": 85.0,
                "action": "BUY"
            }
        ],
        "generated_at": "2023-10-01T10:00:00Z"
    }
    mock_instance.full_analysis.return_value = mock_response

    payload = {
        "symbols": ["TCS.NS"],
        "mode": "swing",
        "timeframe": {
            "intraday": "5m",
            "swing": "1D",
            "lookback_window": 180
        }
    }

    response = client.post("/analysis/full", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["symbol"] == "TCS.NS"
    assert data["items"][0]["action"] == "BUY"

def test_screener_full_endpoint(mock_router_agent):
    # Testing the /analysis/screener/full endpoint behavior as an SSE stream
    mock_instance = mock_router_agent.return_value
    
    mock_response = MagicMock()
    mock_response.model_dump.return_value = {
        "results": [
            {"symbol": "INFY.NS", "screener_score": 90.0, "matched": True}
        ],
        "stage_summaries": []
    }
    
    # We must mock the side effect so it calls progress_callback if provided
    def side_effect_screener_full(payload, progress_callback=None):
        if progress_callback:
            progress_callback({"stage": "Test Stage 1", "progress": 50})
        return mock_response
        
    mock_instance.screener_full.side_effect = side_effect_screener_full

    payload = {
        "symbols": ["INFY-EQ"],
        "mode": "swing",
        "timeframe": {
            "intraday": "5m",
            "swing": "1D",
            "lookback_window": 260
        },
        "top_n": 5
    }

    with client.stream("POST", "/analysis/screener/full", json=payload) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        content = response.read().decode("utf-8")
        
    # Check that progress events were emitted
    assert 'event: progress' in content
    assert '"stage": "Test Stage 1"' in content
    
    # Check that the final result event was emitted
    assert 'event: result' in content
    assert '"status": "complete"' in content
    assert '"INFY.NS"' in content
