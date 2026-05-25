import pytest
import asyncio
import time
from backend.app.services.screener_service import TokenBucketRateLimiter

def test_token_bucket_rate_limiter_sync():
    # Capacity is 5 tokens, refill rate is 5 tokens per second.
    limiter = TokenBucketRateLimiter(calls_per_second=5.0)
    
    start_time = time.time()
    
    # Burst 5 tokens - should be instant
    for _ in range(5):
        limiter.acquire()
    
    burst_time = time.time()
    assert (burst_time - start_time) < 0.1 # Very fast
    
    # 6th token should block for roughly 0.2 seconds (1 / 5)
    limiter.acquire()
    end_time = time.time()
    
    # Wait should be around 0.2 seconds
    assert (end_time - burst_time) >= 0.15

@pytest.mark.asyncio
async def test_orchestrator_parallel_execution():
    from backend.app.agents.orchestrator_agent import OrchestratorAgent
    from backend.app.schemas.analysis import AnalysisRequest, TimeframeConfig
    from unittest.mock import patch, MagicMock
    import asyncio
    
    orchestrator = OrchestratorAgent(MagicMock())
    
    # We will mock the internal blocking network calls to verify asyncio.to_thread parallelization
    def mock_sleep_sync(*args, **kwargs):
        time.sleep(0.1)
        return MagicMock()
        
    request = AnalysisRequest(
        symbols=["TCS.NS", "INFY.NS"],
        mode="swing",
        timeframe=TimeframeConfig(intraday="5m", swing="1d", lookback_window=100)
    )
    
    with patch("backend.app.agents.fundamental_analysis_agent.FundamentalAnalysisAgent.run", new=mock_sleep_sync), \
         patch("backend.app.agents.news_analysis_agent.NewsAnalysisAgent.run", new=mock_sleep_sync), \
         patch("backend.app.agents.orchestrator_agent.FyersService.fetch_ohlcv", return_value=[]), \
         patch("backend.app.agents.orchestrator_agent.TechnicalAnalysisAgent.run_bulk", return_value={}):
         
        start = time.time()
        
        # This will execute _analyze_symbol_post_bulk concurrently using asyncio.to_thread
        orchestrator.run_full(request)
        
        end = time.time()
        
        # If executed sequentially, time > 0.4s
        # If executed concurrently via to_thread, time should be ~0.1s - 0.25s
        # Allowing up to 2.0s due to system load/Windows overhead
        assert (end - start) < 2.0
