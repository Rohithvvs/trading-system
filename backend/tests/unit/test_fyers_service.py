import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from backend.app.services.fyers_service import FyersService

@pytest.fixture
def fyers_service():
    return FyersService()

def test_compute_app_id_hash(fyers_service, monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "fyers_app_id", "TEST_APP_ID")
    monkeypatch.setattr(settings, "fyers_secret_id", "TEST_SECRET")
    
    # Expected hash for "TEST_APP_ID:TEST_SECRET"
    import hashlib
    expected = hashlib.sha256(b"TEST_APP_ID:TEST_SECRET").hexdigest()
    
    assert fyers_service._compute_app_id_hash() == expected

def test_save_tokens_only_access(fyers_service, monkeypatch):
    # After refresh removal, save_tokens accepts only access_token
    import asyncio
    from unittest.mock import AsyncMock
    
    async def mock_save(token, db):
        return {"status": "ok"}
    
    monkeypatch.setattr("backend.app.services.token_service.save_access_token", mock_save)
    
    db = AsyncMock()
    # call signature now (access_token, db) only
    result = asyncio.get_event_loop().run_until_complete(
        fyers_service.save_tokens("test_access", db)
    )
    assert result.get("status") == "ok"
