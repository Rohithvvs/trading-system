from __future__ import annotations

from ..schemas import AnalysisMode, BacktestResult, FinalRecommendation, OHLCVPoint, TechnicalAnalysisResult
from ..services.llm_service import LLMService
from ..services.recommendation_service import RecommendationService


class RecommendationAgent:
    def __init__(self) -> None:
        self.llm_service = LLMService()
        self.recommendation_service = RecommendationService()

    def run(
        self,
        symbol: str,
        technical_results: list[TechnicalAnalysisResult],
        sentiment_label: str,
        sentiment_score: float,
        backtests: list[BacktestResult],
        candles_by_mode: dict[AnalysisMode, list[OHLCVPoint]],
    ) -> FinalRecommendation:
        primary_technical = technical_results[0]
        best_backtest = max(backtests, key=lambda item: item.total_return)
        primary_candles = candles_by_mode.get(primary_technical.mode, [])
        current_price = primary_candles[-1].close if primary_candles else "unknown"

        llm_reasoning = self.llm_service.build_reasoning(
            symbol,
            {
                "technical_signal": primary_technical.signal,
                "technical_score": primary_technical.score,
                "news_label": sentiment_label,
                "sentiment_score": sentiment_score,
                "backtest_verdict": best_backtest.verdict,
                "backtest_return": best_backtest.total_return,
                "current_price": current_price,
                "modes": [item.mode.value for item in technical_results],
            },
        )
        return self.recommendation_service.build(
            symbol=symbol,
            technical_results=technical_results,
            sentiment_score=sentiment_score,
            backtests=backtests,
            candles_by_mode=candles_by_mode,
            llm_reasoning=llm_reasoning,
        )
