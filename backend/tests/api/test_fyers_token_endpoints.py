import pytest
from httpx import AsyncClient

def test_fyers_token_save_and_status(client, db_session, monkeypatch):
    # 1. Check initial status
    resp = client.get("/fyers/token/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("has_token") is False or data.get("access_token_active") is False
    
    # 2. Mock token validation
    monkeypatch.setattr("backend.app.services.fyers_service.FyersService.validate_token_sync", lambda self, token: {"s": "ok"})
    
    # 3. Post a new access token only (refresh removed)
    payload = {
        "access_token": "ey12345.access"
    }
    resp = client.post("/fyers/token", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    
    # 4. Check status again - no refresh fields
    resp = client.get("/fyers/token/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("has_token") is True or data.get("access_token_active") is True
    # refresh fields intentionally absent
