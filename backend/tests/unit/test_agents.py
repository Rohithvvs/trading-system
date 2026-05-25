import pytest
from unittest.mock import patch, MagicMock
from backend.app.agents.fundamental_analysis_agent import FundamentalAnalysisAgent
from backend.app.agents.news_analysis_agent import NewsAnalysisAgent
from backend.app.schemas.analysis import FundamentalAnalysisResult, ArticleItem

@patch("backend.app.agents.fundamental_analysis_agent.yf.Ticker")
def test_fundamental_analysis_agent_valid(mock_ticker_class):
    # Setup mock yfinance Ticker info
    mock_ticker = mock_ticker_class.return_value
    mock_ticker.info = {
        "revenueGrowth": 0.25,
        "profitMargins": 0.15,
        "debtToEquity": 0.40,
        "trailingPE": 20.5
    }
    
    agent = FundamentalAnalysisAgent()
    result = agent.run("TCS.NS")
    
    # Assert structured output logic
    assert isinstance(result, FundamentalAnalysisResult)
    assert result.revenue_growth_pct == 25.0
    assert result.profit_margin_pct == 15.0
    assert result.fundamental_score > 0.0

@patch("backend.app.agents.fundamental_analysis_agent.yf.Ticker")
def test_fundamental_analysis_agent_missing_data(mock_ticker_class):
    # Setup mock yfinance with empty info (Hostile Path)
    mock_ticker = mock_ticker_class.return_value
    mock_ticker.info = {}
    
    agent = FundamentalAnalysisAgent()
    result = agent.run("TCS.NS")
    
    # Assert fallback logic prevents crashes
    assert result.revenue_growth_pct is None
    assert result.profit_margin_pct is None
    assert result.fundamental_score == 0.0

@patch("backend.app.agents.news_analysis_agent.NewsService.fetch_recent_news")
@patch("backend.app.services.sentiment_service.LLMService.analyze_sentiment")
def test_news_analysis_agent_llm_mock(mock_analyze_sentiment, mock_fetch_news):
    from datetime import datetime
    articles = [ArticleItem(title="TCS hits record high", url="http://test.com", source="News", published_at=datetime.utcnow(), description="Quarterly earnings beat expectations.", sentiment_score=0.85)]
    mock_fetch_news.return_value = articles
    
    # Setup mock sentiment score
    mock_analyze_sentiment.return_value = 0.85
    
    agent = NewsAnalysisAgent()
    result_articles, score, label, summary = agent.run("TCS.NS")
    
    # Assert LLM interception and Pydantic parsing
    assert label == "positive"
    assert score == 0.85
    assert len(result_articles) == 1
    
    # Verify the mocks were actually called
    mock_fetch_news.assert_called_once_with("TCS.NS")
    mock_analyze_sentiment.assert_called_once()
