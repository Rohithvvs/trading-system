import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock
from backend.app.services.fyers_service import FyersService
from backend.app.models.fyers_token import FyersToken
from sqlalchemy import select

@pytest.mark.asyncio
async def test_auto_renewal_flow(async_db_session, monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "fyers_app_id", "TEST_APP")
    monkeypatch.setattr(settings, "fyers_secret_id", "TEST_SECRET")
    monkeypatch.setattr(settings, "fyers_pin", "1234")
    
    # 1. Setup Database with an active token and a refresh token
    service = FyersService()
    encrypted_refresh = service.encrypt_token("raw_refresh_token_123")
    
    token_record = FyersToken(
        access_token="old_access_token",
        access_token_saved_at=datetime.utcnow() - timedelta(days=1),
        refresh_token=encrypted_refresh,
        refresh_token_expires_at=datetime.utcnow() + timedelta(days=10),
        is_active=True,
        status="active"
    )
    async_db_session.add(token_record)
    await async_db_session.commit()
    
    # 2. Mock httpx.AsyncClient.post
    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "s": "ok",
                "access_token": "new_access_token_456",
                "message": "success"
            }
            
    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def post(self, url, json, **kwargs):
            return MockResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: MockClient())
    
    # 3. Call auto_refresh_access_token
    result = await service.auto_refresh_access_token(async_db_session)
    
    # 4. Assert response
    assert result["status"] == "ok"
    assert result["message"] == "Token refreshed successfully"
    
    # 5. Verify database update
    # Need a fresh session or refresh
    row = (await async_db_session.scalars(select(FyersToken).filter_by(is_active=True))).first()
    assert row.access_token == "new_access_token_456"
    assert row.last_auto_renewal_status == "success"
    assert row.last_error is None
