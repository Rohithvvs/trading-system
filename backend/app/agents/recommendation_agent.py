from __future__ import annotations

from typing import Any

from ..schemas import AnalysisMode, BacktestResult, FinalRecommendation, OHLCVPoint, TechnicalAnalysisResult, FundamentalAnalysisResult
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
        fundamental_result: FundamentalAnalysisResult | None,
        backtests: list[BacktestResult],
        candles_by_mode: dict[AnalysisMode, list[OHLCVPoint]],
        feat004_config: dict[str, Any] | None = None,
        benchmark_ohlcv: list[OHLCVPoint] | None = None,
        benchmark_failure_reason: str | None = None,
        benchmark_symbol: str | None = None,
        sector_mapping: dict[str, str] | None = None,
        sector_ohlcv_cache: dict[str, list[OHLCVPoint]] | None = None,
        feat007_config: dict[str, Any] | None = None,
        sector_rs_value: float | None = None,
        sector_index_symbol: str | None = None,
        sector_roc20: float | None = None,
        benchmark_roc20: float | None = None,
        feat007_abstained_reason: str | None = None,
        market_breadth_soft_score: float | None = None,
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
                "fundamental_score": fundamental_result.fundamental_score if fundamental_result else 0.0,
                "current_price": current_price,
                "modes": [item.mode.value for item in technical_results],
            },
        )
        return self.recommendation_service.build(
            symbol=symbol,
            technical_results=technical_results,
            sentiment_score=sentiment_score,
            fundamental_result=fundamental_result,
            backtests=backtests,
            candles_by_mode=candles_by_mode,
            llm_reasoning=llm_reasoning,
            feat004_config=feat004_config,
            benchmark_ohlcv=benchmark_ohlcv,
            benchmark_failure_reason=benchmark_failure_reason,
            benchmark_symbol=benchmark_symbol,
            sector_mapping=sector_mapping,
            sector_ohlcv_cache=sector_ohlcv_cache,
            feat007_config=feat007_config,
            sector_rs_value=sector_rs_value,
            sector_index_symbol=sector_index_symbol,
            sector_roc20=sector_roc20,
            benchmark_roc20=benchmark_roc20,
            feat007_abstained_reason=feat007_abstained_reason,
            market_breadth_soft_score=market_breadth_soft_score,
        )
