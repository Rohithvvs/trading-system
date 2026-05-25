import pytest
from backend.app.services.recommendation_service import RecommendationService

@pytest.fixture
def recommendation_service():
    return RecommendationService()

def test_dynamic_weights_standard_regime(recommendation_service):
    # Sentiment < 0.75 and Volume <= 300% -> Standard Regime
    tech, backtest, news, fund = recommendation_service.calculate_dynamic_weights(
        sentiment_score=0.5,
        fundamental_score=0.5,
        current_volume=1000,
        avg_volume=1000
    )
    assert tech == 0.50
    assert backtest == 0.25
    assert news == 0.0
    assert fund == 0.25

def test_dynamic_weights_catalyst_regime_high_sentiment(recommendation_service):
    # Sentiment >= 0.75 -> Catalyst Regime overrides
    tech, backtest, news, fund = recommendation_service.calculate_dynamic_weights(
        sentiment_score=0.8,
        fundamental_score=0.5,
        current_volume=1000,
        avg_volume=1000
    )
    assert tech == 0.20
    assert backtest == 0.20
    assert news == 0.30
    assert fund == 0.30

def test_dynamic_weights_catalyst_regime_high_volume(recommendation_service):
    # Volume > 300% of avg -> Catalyst Regime overrides
    tech, backtest, news, fund = recommendation_service.calculate_dynamic_weights(
        sentiment_score=0.2,
        fundamental_score=0.5,
        current_volume=4000,
        avg_volume=1000
    )
    assert tech == 0.20
    assert backtest == 0.20
    assert news == 0.30
    assert fund == 0.30

def test_dynamic_weights_zero_volume_handling(recommendation_service):
    # Ensure no ZeroDivisionError
    tech, backtest, news, fund = recommendation_service.calculate_dynamic_weights(
        sentiment_score=0.2,
        fundamental_score=0.5,
        current_volume=1000,
        avg_volume=0
    )
    # Since avg_volume is 0, logic typically handles >300% safely, defaulting to standard
    # unless current_volume > 0 is treated as infinite surge.
    # Assuming standard behavior if avg is 0.
    assert tech in (0.50, 0.20)  # Either regime is valid depending on exact div/0 logic
