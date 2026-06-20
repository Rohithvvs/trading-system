import pytest
import datetime
import asyncio
from unittest.mock import patch
from backend.app.agents.orchestrator_agent import OrchestratorAgent
from backend.app.schemas.analysis import AnalysisMode, AnalysisRequest, OHLCVPoint
from backend.app.models.analysis import AnalysisHistory
import backend.app.services.fyers_service as fyers

@pytest.mark.asyncio
async def test_orchestrator_service_integration(db_session, monkeypatch):
    request = AnalysisRequest(symbols=["HDFCBANK.NS"], mode=AnalysisMode.swing)
    
    # We need at least 250 candles so Technical Analysis indicators (like SMA 200, ATR) compute properly
    base_date = datetime.datetime(2023, 1, 1)
    candles = [
        OHLCVPoint(
            timestamp=base_date + datetime.timedelta(days=i), 
            open=100.0 + (i * 0.1), 
            high=105.0 + (i * 0.1), 
            low=95.0 + (i * 0.1), 
            close=102.0 + (i * 0.1), 
            volume=1000 + i
        )
        for i in range(250)
    ]
    
    # External boundary mock for Fyers
    class FakeFyersService:
        def __init__(self, *args, **kwargs): pass
        def get_candles_cached(self, *args, **kwargs): return candles
        async def fetch_ohlcv(self, *args, **kwargs): return candles
        def fetch_incremental_ohlcv(self, *args, **kwargs): return candles
        def combine_candles(self, *args, **kwargs): return candles
        def get_ohlcv_source(self, *args, **kwargs): return "MOCK"
        def _cache_symbol(self, symbol: str) -> str: return symbol
        def _is_fyers_configured(self) -> bool: return True
        
    monkeypatch.setattr(fyers, "FyersService", FakeFyersService)
    # Monkeypatch inside the orchestrator module as well just in case
    import backend.app.agents.orchestrator_agent as orch_mod
    monkeypatch.setattr(orch_mod, "FyersService", FakeFyersService)
    
    import backend.app.services.screener_service as screener_service
    monkeypatch.setattr(screener_service, "FyersService", FakeFyersService)
    
    # External boundary mock for yfinance (used by FundamentalAnalysisAgent)
    with patch("backend.app.agents.fundamental_analysis_agent.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.info = {"revenueGrowth": 0.15, "profitMargins": 0.2}
        
        # External boundary mock for News/Sentiment (used by NewsAnalysisAgent)
        with patch("backend.app.agents.news_analysis_agent.NewsService.fetch_recent_news") as mock_news:
            mock_news.return_value = [{"title": "Good earnings", "link": "url"}]
            with patch("backend.app.services.sentiment_service.LLMService.analyze_sentiment") as mock_llm:
                mock_llm.return_value = 0.8 # Positive sentiment
                
                # Instantiate OrchestratorAgent AFTER monkeypatching
                orchestrator = OrchestratorAgent(db_session)
                # Execute the real pipeline end-to-end
                response = orchestrator.run_full(request)
            
    # Assertions on the real pipeline output
    assert len(response.items) == 1
    item = response.items[0]
    assert item.symbol == "HDFCBANK.NS"
    assert item.technical is not None
    assert len(item.technical) > 0
    assert item.technical[0].score > 0  # Should be computed by real TechnicalAnalysisAgent
    
    assert item.fundamental is not None
    assert item.fundamental.fundamental_score > 0 # Computed by real FundamentalAnalysisAgent
    
    assert item.news_sentiment_score is not None # Computed by real NewsAnalysisAgent
    
    # Ensure persistence ran successfully
    history_count = db_session.query(AnalysisHistory).count()
    assert history_count > 0
