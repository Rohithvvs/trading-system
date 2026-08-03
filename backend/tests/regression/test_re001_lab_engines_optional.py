"""Regression: StockAnalysisResult accepts optional lab_engines without breaking defaults."""

from datetime import datetime

from app.schemas.analysis import (
    AnalysisMode,
    FinalRecommendation,
    OHLCVPoint,
    RecommendationReasoning,
    StockAnalysisResult,
    TechnicalAnalysisResult,
)


def test_stock_analysis_result_without_lab_engines():
    item = StockAnalysisResult(
        symbol="INFY",
        ohlcv=[
            OHLCVPoint(
                timestamp=datetime(2024, 1, 1),
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                volume=1000,
            )
        ],
        technical=[
            TechnicalAnalysisResult(
                mode=AnalysisMode.swing,
                signal="bullish",
                score=70,
                indicators={},
                summary="ok",
            )
        ],
        news_articles=[],
        news_summary="",
        news_sentiment_label="neutral",
        news_sentiment_score=0.0,
        backtests=[],
        recommendation=FinalRecommendation(
            action="WATCH",
            confidence=0.5,
            score=60,
            reasoning=RecommendationReasoning(
                bullets=["b"],
                risk_factors=["r"],
                invalidation_signals=["i"],
            ),
            trade_plans=[],
            summary="s",
        ),
        disclaimer="d",
    )
    assert item.lab_engines is None
    dumped = item.model_dump()
    assert "lab_engines" in dumped


def test_stock_analysis_result_with_re001_block():
    item = StockAnalysisResult(
        symbol="TCS",
        ohlcv=[],
        technical=[],
        news_articles=[],
        news_summary="",
        news_sentiment_label="n",
        news_sentiment_score=0,
        backtests=[],
        recommendation=FinalRecommendation(
            action="BUY",
            confidence=0.8,
            score=80,
            reasoning=RecommendationReasoning(
                bullets=["b"],
                risk_factors=[],
                invalidation_signals=[],
            ),
            trade_plans=[],
            summary="buy",
        ),
        disclaimer="d",
        lab_engines={
            "RE-001": {
                "recommendation_state": "WATCH",
                "engine_id": "RE-001",
            }
        },
    )
    assert item.lab_engines["RE-001"]["recommendation_state"] == "WATCH"
    # production action still BUY — lab is independent
    assert item.recommendation.action == "BUY"
