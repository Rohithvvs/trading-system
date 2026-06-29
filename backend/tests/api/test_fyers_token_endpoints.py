import pytest
from httpx import AsyncClient

def test_fyers_token_save_and_status(client, db_session, monkeypatch):
    # 1. Check initial status
    resp = client.get("/fyers/token/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_token"] is False
    
    # 2. Mock token validation
    monkeypatch.setattr("backend.app.services.fyers_service.FyersService.validate_token_sync", lambda self, token: {"s": "ok"})
    
    # 3. Post a new token with refresh token
    payload = {
        "access_token": "ey12345.access",
        "refresh_token": "ey12345.refresh"
    }
    resp = client.post("/fyers/token", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    
    # 4. Check status again
    resp = client.get("/fyers/token/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_token"] is True
    assert data["access_token_active"] is True
    assert data["has_refresh_token"] is True
    assert data["refresh_token_days_remaining"] == 15
