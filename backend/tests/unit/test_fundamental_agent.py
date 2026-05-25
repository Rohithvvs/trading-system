import pytest
from unittest.mock import patch, MagicMock
import asyncio

# Assuming fundamental agent is a class FundamentalAnalysisAgent
# Note: Actual import path depends on where it was placed, using standard location from prompt.
from backend.app.agents.fundamental_analysis_agent import FundamentalAnalysisAgent
from backend.app.schemas.analysis import FundamentalAnalysisResult

@pytest.fixture
def mock_yfinance():
    with patch("backend.app.agents.fundamental_analysis_agent.yf.Ticker") as MockTicker:
        mock_instance = MockTicker.return_value
        
        # Valid data response
        mock_instance.info = {
            "revenueGrowth": 0.15,
            "profitMargins": 0.12,
            "debtToEquity": 0.5,
            "trailingPE": 25.0
        }
        yield MockTicker

def test_fundamental_agent_valid_data(mock_yfinance):
    agent = FundamentalAnalysisAgent()
    result = agent.run("RELIANCE.NS")
    
    assert isinstance(result, FundamentalAnalysisResult)
    assert result.revenue_growth_pct == 15.0
    assert result.profit_margin_pct == 12.0
    # Ensure fundamental score is calculated (bounds between 0 and 100, or scaled)
    assert result.fundamental_score > 0.0

def test_fundamental_agent_missing_data_fallback():
    with patch("backend.app.agents.fundamental_analysis_agent.yf.Ticker") as MockTicker:
        mock_instance = MockTicker.return_value
        # Completely empty info dict representing missing data
        mock_instance.info = {}
        
        agent = FundamentalAnalysisAgent()
        result = agent.run("RELIANCE.NS")
        
        assert isinstance(result, FundamentalAnalysisResult)
        # Should gracefully fallback to neutral scores rather than crashing
        assert result.revenue_growth_pct is None
        assert result.profit_margin_pct is None
        # Score should be a neutral default
        assert result.fundamental_score == 0.0
