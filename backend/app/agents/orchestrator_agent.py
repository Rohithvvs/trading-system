from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AnalysisHistory, BacktestHistory, WatchedStock
from ..schemas import (
    AnalysisMode,
    AnalysisRequest,
    AnalysisResponse,
    FullAnalysisResponse,
    ScreenerRequest,
    ScreenerResponse,
    StockAnalysisResult,
)
from ..services.fyers_service import FyersService
from ..services.screener_service import ScreenerService
from ..utils import advisory_payload, get_logger
from .backtest_agent import BacktestAgent
from .news_analysis_agent import NewsAnalysisAgent
from .ranking_agent import RankingAgent
from .recommendation_agent import RecommendationAgent
from .technical_analysis_agent import TechnicalAnalysisAgent


class OrchestratorAgent:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.logger = get_logger("app.orchestrator")
        self.fyers_service = FyersService()
        self.screener_service = ScreenerService()
        self.technical_agent = TechnicalAnalysisAgent()
        self.news_agent = NewsAnalysisAgent()
        self.backtest_agent = BacktestAgent()
        self.recommendation_agent = RecommendationAgent()
        self.ranking_agent = RankingAgent()

    def run_full(self, request: AnalysisRequest) -> FullAnalysisResponse:
        self.logger.info(
            "Starting full analysis | symbols=%s | mode=%s | intraday=%s | swing=%s | lookback=%s",
            ",".join(request.symbols),
            request.mode.value,
            request.timeframe.intraday,
            request.timeframe.swing,
            request.timeframe.lookback_window,
        )
        items = [self._analyze_symbol(symbol, request) for symbol in request.symbols]
        rankings = self.ranking_agent.run(items)
        self.logger.info(
            "Completed full analysis | analyzed=%s | best_swing=%s | best_intraday=%s",
            len(items),
            rankings.best_swing_candidate,
            rankings.best_intraday_candidate,
        )
        return FullAnalysisResponse(
            items=items,
            rankings=rankings,
            disclaimer=advisory_payload(),
            generated_at=datetime.now(timezone.utc),
        )

    def run_partial(self, request: AnalysisRequest) -> AnalysisResponse:
        items = [self._analyze_symbol(symbol, request) for symbol in request.symbols]
        rankings = self.ranking_agent.run(items)
        return AnalysisResponse(items=items, rankings=rankings, disclaimer=advisory_payload())

    def run_screener(self, request: ScreenerRequest) -> ScreenerResponse:
        self.logger.info(
            "Starting screener flow | top_n=%s | mode=%s | lookback=%s",
            request.top_n,
            request.mode.value,
            request.timeframe.lookback_window,
        )
        # Use symbols provided in request if present, otherwise fall back to configured universe
        universe = request.symbols if request.symbols else settings.universe_symbols
        screener_results = self.screener_service.screen_symbols_swing(
            universe,
            lookback_window=request.timeframe.lookback_window,
        )
        data_valid_symbols = [item.symbol for item in screener_results]
        eligible_results = [item for item in screener_results if item.conditions.get("broad_trend_eligibility", False)]
        matched_results = [item for item in screener_results if item.matched]
        matched_results.sort(key=lambda item: item.screener_score, reverse=True)
        matched_symbols = [item.symbol for item in matched_results]
        eligible_symbols = [item.symbol for item in eligible_results]

        self.logger.info("STEP 5/8 | Keep top ranked screener set | eligible=%s | taking_top=%s", len(matched_results), request.top_n)
        shortlisted_symbols = matched_symbols[: request.top_n]
        analysis: FullAnalysisResponse | None = None
        buy_candidate_symbols: list[str] = []
        watch_candidate_symbols: list[str] = []

        if shortlisted_symbols:
            self.logger.info("STEP 5/8 | Shortlist ready | shortlisted=%s", ",".join(shortlisted_symbols))
            analysis_request = AnalysisRequest(
                symbols=shortlisted_symbols,
                mode=AnalysisMode.swing,
                timeframe=request.timeframe,
            )
            self.logger.info("STEP 6/8 | Run full analysis only on top set | count=%s", len(shortlisted_symbols))
            shortlist_analysis = self.run_full(analysis_request)
            buy_items = [item for item in shortlist_analysis.items if item.recommendation.action == "BUY"]
            watch_items = [item for item in shortlist_analysis.items if item.recommendation.action == "WATCH"]
            buy_candidate_symbols = [item.symbol for item in buy_items]
            watch_candidate_symbols = [item.symbol for item in watch_items]
            self.logger.info(
                "STEP 7/8 | RecommendationAgent finished | buy=%s | watch=%s | reject=%s",
                len(buy_items),
                len(watch_items),
                len([item for item in shortlist_analysis.items if item.recommendation.action == 'REJECT']),
            )
            analysis = FullAnalysisResponse(
                items=buy_items + watch_items,
                rankings=self.ranking_agent.run(buy_items + watch_items),
                disclaimer=advisory_payload(),
                generated_at=shortlist_analysis.generated_at,
            )
            self.logger.info(
                "STEP 8/8 | Rank BUY and WATCH separately | buy_symbols=%s | watch_symbols=%s",
                ",".join(buy_candidate_symbols) if buy_candidate_symbols else "none",
                ",".join(watch_candidate_symbols) if watch_candidate_symbols else "none",
            )
        else:
            self.logger.info("STEP 6/8 | No shortlisted stocks, so downstream analysis was skipped")

        return ScreenerResponse(
            scanned_symbols=len(universe),
            screener_name=f"Configured Universe Combined Swing Scanner ({len(universe)})",
            data_valid_symbols=data_valid_symbols,
            eligible_symbols=eligible_symbols,
            shortlisted_symbols=shortlisted_symbols,
            buy_candidate_symbols=buy_candidate_symbols,
            watch_candidate_symbols=watch_candidate_symbols,
            matched_symbols=matched_symbols,
            matches=matched_results,
            analysis=analysis,
            disclaimer=advisory_payload(),
            data_source=self._data_source_label(),
            data_warning=self._data_warning(),
            market_context=self._market_context(),
        )

    def _analyze_symbol(self, symbol: str, request: AnalysisRequest) -> StockAnalysisResult:
        self.logger.info("Analyzing symbol | symbol=%s | mode=%s", symbol, request.mode.value)
        stock = self._get_or_create_stock(symbol)
        modes = self._resolve_modes(request.mode)
        candles_by_mode = {
            mode: self.fyers_service.fetch_ohlcv(
                symbol=symbol,
                mode=mode,
                resolution=self._resolution_for_mode(mode, request),
                lookback_window=request.timeframe.lookback_window,
            )
            for mode in modes
        }
        technical_results = [
            self.technical_agent.run(symbol, candles_by_mode[mode], mode)
            for mode in modes
        ]
        backtests = [
            self.backtest_agent.run(symbol, mode, candles_by_mode[mode])
            for mode in modes
        ]
        articles, sentiment_score, sentiment_label, news_summary = self.news_agent.run(symbol)

        technical_score = max(result.score for result in technical_results)
        best_backtest = max(backtests, key=lambda item: item.total_return)
        recommendation = self.recommendation_agent.run(
            symbol=symbol,
            technical_results=technical_results,
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            backtests=backtests,
            candles_by_mode=candles_by_mode,
        )

        self._persist_analysis(stock, request.mode.value, technical_score, sentiment_score, best_backtest, recommendation)
        self.logger.info(
            "Completed symbol analysis | symbol=%s | recommendation=%s | confidence=%s | score=%s",
            symbol,
            recommendation.action,
            recommendation.confidence,
            recommendation.score,
        )

        return StockAnalysisResult(
            symbol=symbol,
            ohlcv=self._primary_candle_set(candles_by_mode),
            technical=technical_results,
            news_articles=articles,
            news_summary=news_summary,
            news_sentiment_label=sentiment_label,
            news_sentiment_score=sentiment_score,
            backtests=backtests,
            recommendation=recommendation,
            disclaimer=advisory_payload(),
            data_source=self._data_source_label(),
            data_quality=self._data_quality_payload(candles_by_mode),
            trade_readiness=self._trade_readiness(recommendation, technical_results),
            confidence_breakdown=self._confidence_breakdown(technical_score, sentiment_score, best_backtest, recommendation),
        )

    def _persist_analysis(
        self,
        stock: WatchedStock,
        mode: str,
        technical_score: float,
        sentiment_score: float,
        backtest: Any,
        recommendation: Any,
    ) -> None:
        analysis_entry = AnalysisHistory(
            stock_id=stock.id,
            mode=mode,
            technical_score=technical_score,
            sentiment_score=sentiment_score,
            backtest_score=backtest.total_return,
            recommendation=recommendation.action,
            confidence=recommendation.confidence,
            reasoning=recommendation.summary,
        )
        self.db.add(analysis_entry)

        backtest_entry = BacktestHistory(
            stock_id=stock.id,
            mode=mode,
            strategy_name=backtest.strategy_name,
            total_return=backtest.total_return,
            cagr=backtest.cagr,
            max_drawdown=backtest.max_drawdown,
            win_rate=backtest.win_rate,
            profit_factor=backtest.profit_factor,
            trade_count=backtest.trade_count,
            verdict=backtest.verdict,
        )
        self.db.add(backtest_entry)
        self.db.commit()

    def _get_or_create_stock(self, symbol: str) -> WatchedStock:
        existing = self.db.scalar(select(WatchedStock).where(WatchedStock.symbol == symbol))
        if existing:
            return existing

        stock = WatchedStock(symbol=symbol, display_name=symbol.replace("-EQ", ""))
        self.db.add(stock)
        self.db.flush()
        return stock

    def _resolve_modes(self, mode: AnalysisMode) -> list[AnalysisMode]:
        if mode == AnalysisMode.both:
            return [AnalysisMode.intraday, AnalysisMode.swing]
        return [mode]

    def _resolution_for_mode(self, mode: AnalysisMode, request: AnalysisRequest) -> str:
        if mode == AnalysisMode.intraday:
            return request.timeframe.intraday
        return request.timeframe.swing

    def _primary_candle_set(self, candles_by_mode: dict[AnalysisMode, list]) -> list:
        return candles_by_mode.get(AnalysisMode.swing) or next(iter(candles_by_mode.values()))

    def _data_source_label(self) -> str:
        if settings.fyers_app_id and settings.fyers_access_token:
            return "FYERS_OR_FALLBACK"
        return "MOCK_FALLBACK"

    def _data_warning(self) -> str | None:
        if settings.fyers_app_id and settings.fyers_access_token:
            return "FYERS is configured, but individual symbols may still fall back if the provider returns no candles."
        return "Using generated mock candles because FYERS credentials are not configured. Do not trade from mock-only results."

    def _market_context(self) -> dict[str, str | float | bool]:
        return {
            "status": "not_evaluated",
            "note": "Index, sector breadth, and VIX filters are not yet connected. Treat market confirmation as manual.",
            "market_filter_pass": False,
        }

    def _data_quality_payload(self, candles_by_mode: dict[AnalysisMode, list]) -> dict[str, str | int | bool | float]:
        primary = self._primary_candle_set(candles_by_mode)
        latest_timestamp = primary[-1].timestamp.isoformat() if primary else "n/a"
        return {
            "source": self._data_source_label(),
            "candles": len(primary),
            "latest_timestamp": latest_timestamp,
            "mock_warning": self._data_source_label() == "MOCK_FALLBACK",
            "minimum_swing_candles_met": len(primary) >= 220,
        }

    def _trade_readiness(self, recommendation, technical_results: list) -> str:
        best_technical = max(technical_results, key=lambda item: item.score)
        plan = recommendation.trade_plans[0] if recommendation.trade_plans else None
        if self._data_source_label() == "MOCK_FALLBACK":
            return "Data unreliable"
        if recommendation.action == "BUY" and best_technical.score >= 72 and plan and plan.risk_reward_ratio >= 2:
            return "Ready to trade"
        if recommendation.action in {"BUY", "WATCH"} and plan:
            return "Wait for entry"
        if recommendation.action == "BUY" and plan and plan.risk_reward_ratio < 2:
            return "Risk-reward weak"
        return "Avoid"

    def _confidence_breakdown(self, technical_score: float, sentiment_score: float, backtest, recommendation) -> dict[str, float | str]:
        sentiment_component = round((sentiment_score + 1) * 20, 2)
        backtest_component = round(min(backtest.total_return * 2, 25), 2)
        return {
            "technical_score": round(technical_score, 2),
            "technical_component": round(technical_score * 0.5, 2),
            "sentiment_score": round(sentiment_score, 2),
            "sentiment_component": sentiment_component,
            "backtest_return": round(backtest.total_return, 2),
            "backtest_component": backtest_component,
            "final_score": round(recommendation.score, 2),
            "confidence": round(recommendation.confidence, 2),
        }
