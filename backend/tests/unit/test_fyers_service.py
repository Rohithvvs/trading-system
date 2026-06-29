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

def test_compute_app_id_hash_missing(fyers_service, monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "fyers_app_id", "")
    monkeypatch.setattr(settings, "fyers_secret_id", "TEST_SECRET")
    
    with pytest.raises(ValueError):
        fyers_service._compute_app_id_hash()

@pytest.mark.asyncio
async def test_refresh_token_days_remaining(fyers_service, monkeypatch):
    # Mock get_fyers_token_row
    mock_row = MagicMock()
    mock_row.access_token = "some_access_token"
    mock_row.is_active = True
    mock_row.refresh_token = "some_refresh_token"
    
    # 5.5 days from now
    mock_row.refresh_token_expires_at = datetime.utcnow() + timedelta(days=5, hours=12)
    
    async def mock_get_row(db):
        return mock_row
        
    monkeypatch.setattr("backend.app.services.token_service.get_fyers_token_row", mock_get_row)
    
    db = AsyncMock()
    status = await fyers_service.get_token_status_with_refresh_info(db)
    
    # 5 full days + 1 partial day = 6 days remaining
    assert status["refresh_token_days_remaining"] == 6
