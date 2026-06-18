import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pandas as pd

from backend.app.services.market_data_service import MarketDataService
from backend.app.services.cache_state import CacheState
from backend.app.services.fyers_service import FyersService, QUARANTINED_SYMBOLS
from backend.app.schemas import AnalysisMode

@pytest.fixture
def md_svc():
    return MarketDataService()

def test_cache_validation_fresh_incomplete():
    md_svc = MarketDataService()
    
    with patch.object(md_svc, 'get_candle_count', return_value=100), \
         patch.object(md_svc, 'get_latest_candle_time', return_value=datetime.now(timezone.utc)), \
         patch('app.services.market_data_service.SessionLocal') as mock_session, \
         patch.object(md_svc, 'load_full_history') as mock_history:
        
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []
        mock_session.return_value.__enter__.return_value = mock_db
        mock_history.return_value = pd.DataFrame()
        
        result = md_svc.validate_candle_continuity("TCS-EQ", "1D", 260)
        assert result.cache_state == CacheState.FRESH_INCOMPLETE
        assert result.is_valid_for_indicators is False

def test_cache_validation_corrupted_duplicates():
    md_svc = MarketDataService()
    
    with patch.object(md_svc, 'get_candle_count', return_value=260), \
         patch.object(md_svc, 'get_latest_candle_time', return_value=datetime.now(timezone.utc)), \
         patch('app.services.market_data_service.SessionLocal') as mock_session:
         
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [(datetime.now(),)]
        mock_session.return_value.__enter__.return_value = mock_db
        
        result = md_svc.validate_candle_continuity("TCS-EQ", "1D", 260)
        assert result.cache_state == CacheState.CORRUPTED
        assert result.is_valid_for_indicators is False
        assert result.continuity_gap_count > 0

def test_cache_validation_stale_complete():
    md_svc = MarketDataService()
    
    with patch.object(md_svc, 'get_candle_count', return_value=260), \
         patch.object(md_svc, 'get_latest_candle_time', return_value=datetime.now(timezone.utc) - timedelta(days=5)), \
         patch('app.services.market_data_service.SessionLocal') as mock_session, \
         patch.object(md_svc, 'load_full_history') as mock_history:
         
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []
        mock_session.return_value.__enter__.return_value = mock_db
        mock_history.return_value = pd.DataFrame()
        
        result = md_svc.validate_candle_continuity("TCS-EQ", "1D", 260)
        assert result.cache_state == CacheState.STALE_COMPLETE
        assert result.is_valid_for_indicators is True

def test_quarantine_cooldown():
    fyers = FyersService()
    symbol = "INVALID-EQ"
    fyers._blacklist_symbol(symbol)
    assert fyers._is_blacklisted(symbol) is True
    
    QUARANTINED_SYMBOLS[fyers._cache_symbol(symbol)] = datetime.now(timezone.utc) - timedelta(hours=1)
    assert fyers._is_blacklisted(symbol) is False
