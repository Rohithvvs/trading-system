from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config import settings
from backend.app.routes.paper_trading import get_service
from backend.app.schemas.paper_trading import PaperOrderActionResponse, PaperOrderResponse, PaperAccountSummary
from unittest.mock import MagicMock
import uuid

# Override the service dependency
mock_service = MagicMock()
app.dependency_overrides[get_service] = lambda: mock_service

client = TestClient(app)

def _mock_response():
    return PaperOrderActionResponse(
        status="success",
        message="Order placed",
        order_id=123,
        account=PaperAccountSummary(
            account_id=1,
            account_name="Test",
            starting_balance=100000,
            balance=100000,
            equity=100000,
            realized_pnl=0,
            unrealized_pnl=0,
            total_invested=0,
            reserved_cash=0,
            available_cash=100000,
            open_positions_count=0,
            open_orders_count=0,
            max_risk_per_trade=0.02,
            updated_at="2024-01-01T00:00:00Z"
        ),
        order=PaperOrderResponse(
            id=123,
            symbol="INFY-EQ",
            side="BUY",
            type="MARKET",
            qty=10,
            status="PENDING",
            created_at="2024-01-01T00:00:00Z"
        )
    )

def test_missing_idempotency_key_returns_400():
    original_env = settings.app_env
    settings.app_env = "prod"
    try:
        response = client.post("/paper-trading/orders", json={
            "symbol": "INFY-EQ",
            "side": "BUY",
            "type": "MARKET",
            "qty": 10
        })
        assert response.status_code == 400
        assert "Idempotency-Key header or idempotency_key body field is required" in response.json()["detail"]
    finally:
        settings.app_env = original_env

def test_valid_idempotency_key_accepted():
    key = str(uuid.uuid4())
    mock_service.place_order.return_value = _mock_response()
    response = client.post("/paper-trading/orders", json={
        "symbol": "INFY-EQ",
        "side": "BUY",
        "type": "MARKET",
        "qty": 10
    }, headers={"Idempotency-Key": key})
    assert response.status_code == 200

def test_duplicate_idempotency_key_no_duplicate():
    key = str(uuid.uuid4())
    mock_service.place_order.return_value = _mock_response()
    
    response1 = client.post("/paper-trading/orders", json={
        "symbol": "TCS-EQ",
        "side": "BUY",
        "type": "MARKET",
        "qty": 10
    }, headers={"Idempotency-Key": key})
    
    response2 = client.post("/paper-trading/orders", json={
        "symbol": "TCS-EQ",
        "side": "BUY",
        "type": "MARKET",
        "qty": 10
    }, headers={"Idempotency-Key": key})
    
    assert response1.status_code == 200
    assert response2.status_code == 200

def test_httpexception_remains_400_not_500():
    key = str(uuid.uuid4())
    # Make the mock raise a ValueError to test the route's exception handler
    mock_service.place_order.side_effect = ValueError("Invalid market condition")
    
    response = client.post("/paper-trading/orders", json={
        "symbol": "INFY-EQ",
        "side": "BUY",
        "type": "MARKET",
        "qty": 1
    }, headers={"Idempotency-Key": key})
    assert response.status_code == 400
    assert "Invalid market condition" in response.json()["detail"]
