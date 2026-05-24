import pytest
from backend.app.services.recommendation_service import RecommendationService

def test_calculate_dynamic_weights_standard_regime():
    service = RecommendationService()
    tech_wt, backtest_wt, news_wt, fund_wt = service.calculate_dynamic_weights(
        sentiment_score=0.2,
        fundamental_score=0.5,
        current_volume=100000,
        avg_volume=100000
    )
    # Standard regime triggers when sentiment < 0.75 and vol <= 300%
    assert tech_wt == 0.50
    assert backtest_wt == 0.25
    assert fund_wt == 0.25
    assert news_wt == 0.0

def test_calculate_dynamic_weights_catalyst_regime_sentiment():
    service = RecommendationService()
    tech_wt, backtest_wt, news_wt, fund_wt = service.calculate_dynamic_weights(
        sentiment_score=0.8,  # > 0.75 triggers catalyst
        fundamental_score=0.5,
        current_volume=100000,
        avg_volume=100000
    )
    assert tech_wt == 0.20
    assert backtest_wt == 0.20
    assert fund_wt == 0.30
    assert news_wt == 0.30

def test_calculate_dynamic_weights_catalyst_regime_volume():
    service = RecommendationService()
    tech_wt, backtest_wt, news_wt, fund_wt = service.calculate_dynamic_weights(
        sentiment_score=0.0,
        fundamental_score=0.5,
        current_volume=350000,  # > 300% of avg volume triggers catalyst
        avg_volume=100000
    )
    assert tech_wt == 0.20
    assert backtest_wt == 0.20
    assert fund_wt == 0.30
    assert news_wt == 0.30
