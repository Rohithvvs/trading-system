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
    ScreenerStageSummary,
    ScreenerRequest,
    ScreenerResponse,
    StockAnalysisResult,
    TechnicalAnalysisResult,
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
        self.screener_service = ScreenerService(self.fyers_service)
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
            "Starting screener flow | top_n=%s | mode=%s | lookback=%s | custom_symbol_count=%s",
            request.top_n,
            request.mode.value,
            request.timeframe.lookback_window,
            len(request.symbols),
        )
        if request.symbols:
            self.logger.info(
                "Custom screener symbols provided | count=%s | symbols=%s",
                len(request.symbols),
                ",".join(request.symbols),
            )
            return self._run_screener_stage(
                request=request,
                stage_name="Custom symbols",
                source_universe=request.symbols,
                duplicate_symbols_skipped=0,
            )

        seen_symbols: set[str] = set()
        duplicate_symbols_skipped = 0
        scan_stages: list[ScreenerStageSummary] = []
        final_response: ScreenerResponse | None = None
        stopped_at_stage: str | None = None

        universes = self._prioritized_universes()
        self.logger.info(
            "Universe scan plan | stages=%s | stage_list=%s",
            len(universes),
            ",".join(name for name, _ in universes),
        )

        for stage_name, source_universe in universes:
            self.logger.info(
                "STAGE START | stage=%s | universe_size=%s | symbols=%s",
                stage_name,
                len(source_universe),
                ",".join(source_universe[:5]) + ("..." if len(source_universe) > 5 else ""),
            )
            unique_symbols, skipped = self._dedupe_symbols(source_universe, seen_symbols)
            duplicate_symbols_skipped += skipped
            if not unique_symbols:
                self.logger.warning(
                    "STAGE SKIPPED | stage=%s | reason=all_symbols_duplicated | skipped=%s",
                    stage_name,
                    skipped,
                )
                scan_stages.append(
                    ScreenerStageSummary(
                        stage_name=stage_name,
                        source_universe_size=len(source_universe),
                        unique_symbols_scanned=0,
                        duplicate_symbols_skipped=skipped,
                        matched_symbols=0,
                        shortlisted_symbols=0,
                    )
                )
                continue

            stage_response = self._run_screener_stage(
                request=request,
                stage_name=stage_name,
                source_universe=unique_symbols,
                duplicate_symbols_skipped=skipped,
            )
            scan_stages.extend(stage_response.scan_stages)
            final_response = stage_response
            if stage_response.buy_candidate_symbols:
                stopped_at_stage = stage_name
                scan_stages[-1].stopped_here = True
                self.logger.info(
                    "STAGE STOPPED | stage=%s | reason=buy_candidates_found | buy_count=%s",
                    stage_name,
                    len(stage_response.buy_candidate_symbols),
                )
                break
            self.logger.info(
                "STAGE COMPLETED | stage=%s | no_buy_candidates | continuing_to_next_stage",
                stage_name,
            )

        if final_response is None:
            final_response = self._empty_screener_response()

        final_response.scan_stages = scan_stages
        final_response.stopped_at_stage = stopped_at_stage
        final_response.duplicate_symbols_skipped = duplicate_symbols_skipped
        if stopped_at_stage:
            final_response.screener_name = f"{final_response.screener_name} | stopped_at={stopped_at_stage}"
        self.logger.info(
            "Completed screener flow | scanned=%s | valid=%s | eligible=%s | matched=%s | shortlisted=%s | buy=%s | watch=%s | duplicate_symbols_skipped=%s | stopped_at=%s",
            final_response.scanned_symbols,
            len(final_response.data_valid_symbols),
            len(final_response.eligible_symbols),
            len(final_response.matched_symbols),
            len(final_response.shortlisted_symbols),
            len(final_response.buy_candidate_symbols),
            len(final_response.watch_candidate_symbols),
            duplicate_symbols_skipped,
            stopped_at_stage,
        )
        return final_response

    def _run_screener_stage(
        self,
        request: ScreenerRequest,
        stage_name: str,
        source_universe: list[str],
        duplicate_symbols_skipped: int,
    ) -> ScreenerResponse:
        screener_results = self.screener_service.screen_symbols_swing(
            source_universe,
            lookback_window=request.timeframe.lookback_window,
            stage_name=stage_name,
        )
        data_valid_symbols = [
            item.symbol
            for item in screener_results
            if not item.conditions.get("data_source_failed", False) and not item.conditions.get("data_quality_failed", False)
        ]
        eligible_results = [item for item in screener_results if item.conditions.get("broad_trend_eligibility", False)]
        matched_results = [item for item in screener_results if item.matched]
        matched_results.sort(key=lambda item: item.screener_score, reverse=True)
        matched_symbols = [item.symbol for item in matched_results]
        eligible_symbols = [item.symbol for item in eligible_results]

        data_source_failed = sum(1 for item in screener_results if item.conditions.get("data_source_failed", False))
        data_quality_failed = sum(1 for item in screener_results if item.conditions.get("data_quality_failed", False))
        rejected_by_conditions = len(
            [item for item in screener_results if not item.matched and not item.conditions.get("data_source_failed", False) and not item.conditions.get("data_quality_failed", False)]
        )

        self.logger.info(
            "STEP 5/8 | Keep top ranked screener set | stage=%s | universe=%s | requested=%s | deduped=%s | valid=%s | eligible=%s | matched=%s | data_source_failed=%s | data_quality_failed=%s | rejected_by_conditions=%s | taking_top=%s",
            stage_name,
            stage_name,
            len(source_universe) + duplicate_symbols_skipped,
            len(source_universe),
            len(data_valid_symbols),
            len(eligible_results),
            len(matched_results),
            data_source_failed,
            data_quality_failed,
            rejected_by_conditions,
            request.top_n,
        )
        shortlisted_symbols = matched_symbols[: request.top_n]
        analysis: FullAnalysisResponse | None = None
        buy_candidate_symbols: list[str] = []
        watch_candidate_symbols: list[str] = []

        if shortlisted_symbols:
            self.logger.info("STEP 5/8 | Shortlist ready | stage=%s | shortlisted=%s", stage_name, ",".join(shortlisted_symbols))
            analysis_request = AnalysisRequest(
                symbols=shortlisted_symbols,
                mode=AnalysisMode.swing,
                timeframe=request.timeframe,
            )
            self.logger.info("STEP 6/8 | Run full analysis only on top set | stage=%s | count=%s", stage_name, len(shortlisted_symbols))
            shortlist_analysis = self.run_full(analysis_request)
            buy_items = [item for item in shortlist_analysis.items if item.recommendation.action == "BUY"]
            watch_items = [item for item in shortlist_analysis.items if item.recommendation.action == "WATCH"]
            buy_candidate_symbols = [item.symbol for item in buy_items]
            watch_candidate_symbols = [item.symbol for item in watch_items]
            self.logger.info(
                "STEP 7/8 | RecommendationAgent finished | stage=%s | buy=%s | watch=%s | reject=%s",
                stage_name,
                len(buy_items),
                len(watch_items),
                len([item for item in shortlist_analysis.items if item.recommendation.action == 'REJECT']),
            )
            analysis_items = buy_items + watch_items
            analysis = FullAnalysisResponse(
                items=analysis_items,
                rankings=self.ranking_agent.run(analysis_items),
                disclaimer=advisory_payload(),
                generated_at=shortlist_analysis.generated_at,
            )
            self.logger.info(
                "STEP 8/8 | Rank BUY and WATCH separately | stage=%s | buy_symbols=%s | watch_symbols=%s",
                stage_name,
                ",".join(buy_candidate_symbols) if buy_candidate_symbols else "none",
                ",".join(watch_candidate_symbols) if watch_candidate_symbols else "none",
            )
        else:
            self.logger.info("STEP 6/8 | No shortlisted stocks, so downstream analysis was skipped | stage=%s", stage_name)
            if screener_results:
                top_ranked = ",".join(f"{item.symbol}:{item.screener_score}" for item in matched_results[:5]) or "none"
                self.logger.info(
                    "STEP 6/8 | No shortlist diagnostics | stage=%s | top_matched=%s | sample_rejections=%s",
                    stage_name,
                    top_ranked,
                    ",".join(
                        f"{item.symbol}:{item.screener_score}"
                        for item in sorted(
                            [row for row in screener_results if not row.matched],
                            key=lambda row: row.screener_score,
                            reverse=True,
                        )[:5]
                    ) or "none",
                )

        self.logger.info(
            "STEP 5/8 | Stage summary | stage=%s | universe=%s | valid=%s | eligible=%s | matched=%s | shortlisted=%s | buy=%s | watch=%s | data_source_failed=%s | data_quality_failed=%s | condition_rejected=%s",
            stage_name,
            stage_name,
            len(data_valid_symbols),
            len(eligible_results),
            len(matched_results),
            len(shortlisted_symbols),
            len(buy_candidate_symbols),
            len(watch_candidate_symbols),
            data_source_failed,
            data_quality_failed,
            rejected_by_conditions,
        )

        return ScreenerResponse(
            scanned_symbols=len(source_universe),
            screener_name=f"{stage_name} Combined Swing Scanner ({len(source_universe)})",
            data_valid_symbols=data_valid_symbols,
            eligible_symbols=eligible_symbols,
            shortlisted_symbols=shortlisted_symbols,
            buy_candidate_symbols=buy_candidate_symbols,
            watch_candidate_symbols=watch_candidate_symbols,
            matched_symbols=matched_symbols,
            matches=matched_results,
            all_analyzed_stocks=screener_results,
            analysis=analysis,
            disclaimer=advisory_payload(),
            data_source=self._data_source_label(),
            data_warning=self._data_warning(),
            market_context=self._market_context(),
            scan_stages=[
                ScreenerStageSummary(
                    stage_name=stage_name,
                    source_universe_size=len(source_universe) + duplicate_symbols_skipped,
                    unique_symbols_scanned=len(source_universe),
                    duplicate_symbols_skipped=duplicate_symbols_skipped,
                    matched_symbols=len(matched_symbols),
                    shortlisted_symbols=len(shortlisted_symbols),
                    buy_candidate_symbols=buy_candidate_symbols,
                    watch_candidate_symbols=watch_candidate_symbols,
                )
            ],
            duplicate_symbols_skipped=duplicate_symbols_skipped,
        )

    def _prioritized_universes(self) -> list[tuple[str, list[str]]]:
        stages = [
            ("NIFTY 500", settings.nifty500_symbols),
            ("NIFTY NEXT 500", settings.nifty_next_500_symbols),
            ("BSE 500", settings.bse500_symbols),
            ("BSE 1000", settings.bse1000_symbols),
        ]
        return [(name, symbols) for name, symbols in stages if symbols]

    def _dedupe_symbols(
        self,
        source_universe: list[str],
        seen_symbols: set[str],
    ) -> tuple[list[str], int]:
        unique_symbols: list[str] = []
        duplicates_skipped = 0
        for symbol in source_universe:
            canonical = self._canonical_symbol(symbol)
            if canonical in seen_symbols:
                duplicates_skipped += 1
                continue
            seen_symbols.add(canonical)
            unique_symbols.append(symbol)
        return unique_symbols, duplicates_skipped

    def _canonical_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if ":" in normalized:
            _, normalized = normalized.split(":", 1)
        return normalized.replace("-EQ", "")

    def _empty_screener_response(self) -> ScreenerResponse:
        self.logger.warning("Screener flow returned empty response | no universes available or nothing scanned")
        return ScreenerResponse(
            scanned_symbols=0,
            screener_name="Configured Universe Combined Swing Scanner (0)",
            data_valid_symbols=[],
            eligible_symbols=[],
            shortlisted_symbols=[],
            buy_candidate_symbols=[],
            watch_candidate_symbols=[],
            matched_symbols=[],
            matches=[],
            analysis=None,
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
        if any(not candles for candles in candles_by_mode.values()):
            self.logger.warning(
                "Skipping deep analysis because live OHLCV is unavailable | symbol=%s | modes_without_data=%s",
                symbol,
                ",".join(mode.value for mode, candles in candles_by_mode.items() if not candles),
            )
            return self._unavailable_analysis_result(symbol, request, candles_by_mode)
        for mode in modes:
            resolution = self._resolution_for_mode(mode, request)
            source = self.fyers_service.get_ohlcv_source(symbol, mode, resolution)
            candle_count = len(candles_by_mode[mode])
            latest_ts = candles_by_mode[mode][-1].timestamp.isoformat() if candles_by_mode[mode] else "n/a"
            self.logger.info(
                "Symbol candle summary | symbol=%s | mode=%s | resolution=%s | source=%s | candles=%s | latest_ts=%s",
                symbol,
                mode.value,
                resolution,
                source,
                candle_count,
                latest_ts,
            )
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
        data_quality = self._data_quality_payload(candles_by_mode, request, symbol)
        recommendation = self._enforce_strict_buy_gate(
            symbol=symbol,
            request=request,
            recommendation=recommendation,
            technical_results=technical_results,
            backtests=backtests,
            candles_by_mode=candles_by_mode,
            data_quality=data_quality,
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
            data_source=self._data_source_label(candles_by_mode, request),
            data_quality=data_quality,
            trade_readiness=self._trade_readiness(recommendation, technical_results, data_quality),
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

    def _default_data_source_label(self) -> str:
        if self.fyers_service._is_fyers_configured():
            return "FYERS_PRIMARY"
        if self.fyers_service.has_fyers_credentials():
            return "FYERS_SDK_MISSING"
        return "NO_DATA"

    def _data_source_label(
        self,
        candles_by_mode: dict[AnalysisMode, list] | None = None,
        request: AnalysisRequest | None = None,
    ) -> str:
        if not candles_by_mode or not request:
            return self._default_data_source_label()
        primary_mode = AnalysisMode.swing if AnalysisMode.swing in candles_by_mode else next(iter(candles_by_mode.keys()))
        resolution = self._resolution_for_mode(primary_mode, request)
        symbol = request.symbols[0] if len(request.symbols) == 1 else None
        if symbol:
            return self.fyers_service.get_ohlcv_source(symbol, primary_mode, resolution)
        return self._default_data_source_label()

    def _data_warning(self) -> str | None:
        if self.fyers_service._is_fyers_configured():
            return "FYERS is configured as the only market data source."
        if self.fyers_service.has_fyers_credentials() and not self.fyers_service.is_fyers_sdk_available():
            return "FYERS credentials are present, but the FYERS SDK is not installed in this Python environment, so live FYERS requests cannot run."
        return "FYERS market data is not available in the current backend environment."

    def _market_context(self) -> dict[str, str | float | bool]:
        return {
            "status": "not_evaluated",
            "note": "Index, sector breadth, and VIX filters are not yet connected. Treat market confirmation as manual.",
            "market_filter_pass": False,
        }

    def _data_quality_payload(
        self,
        candles_by_mode: dict[AnalysisMode, list],
        request: AnalysisRequest,
        symbol: str,
    ) -> dict[str, str | int | bool | float]:
        primary = self._primary_candle_set(candles_by_mode)
        primary_mode = AnalysisMode.swing if AnalysisMode.swing in candles_by_mode else next(iter(candles_by_mode.keys()))
        primary_source = self.fyers_service.get_ohlcv_source(
            symbol,
            primary_mode,
            self._resolution_for_mode(primary_mode, request),
        )
        latest_timestamp = primary[-1].timestamp.isoformat() if primary else "n/a"
        return {
            "source": primary_source,
            "candles": len(primary),
            "candles_fetched": len(primary),
            "latest_timestamp": latest_timestamp,
            "mock_warning": primary_source != "FYERS_PRIMARY",
            "minimum_swing_candles_met": len(primary) >= 220,
        }

    def _unavailable_analysis_result(
        self,
        symbol: str,
        request: AnalysisRequest,
        candles_by_mode: dict[AnalysisMode, list],
    ) -> StockAnalysisResult:
        technical_results = []
        backtests = []
        for mode in self._resolve_modes(request.mode):
            technical_results.append(
                self.technical_agent.service.analyze(symbol, candles_by_mode.get(mode, []), mode)
                if candles_by_mode.get(mode)
                else self._empty_technical_result(mode)
            )
            backtests.append(self.backtest_agent.run(symbol, mode, candles_by_mode.get(mode, [])))

        data_quality = self._data_quality_payload(candles_by_mode, request, symbol)
        recommendation = self.recommendation_agent.recommendation_service.build(
            symbol=symbol,
            technical_results=technical_results,
            sentiment_score=0.0,
            backtests=backtests,
            candles_by_mode=candles_by_mode,
            llm_reasoning={
                "bullets": ["Live OHLCV data was unavailable for this symbol, so the recommendation engine could not evaluate the setup."],
                "risk_factors": ["No live market data was returned from the configured providers."],
                "invalidation_signals": ["Wait for the backend to return fresh live candles before reviewing this symbol."],
                "summary": f"{symbol} could not be analyzed because no live market data was available.",
            },
        ).model_copy(update={"action": "REJECT", "confidence": 0.0, "score": 0.0, "trade_plans": []})

        return StockAnalysisResult(
            symbol=symbol,
            ohlcv=self._primary_candle_set(candles_by_mode),
            technical=technical_results,
            news_articles=[],
            news_summary="No recent news articles were loaded.",
            news_sentiment_label="neutral",
            news_sentiment_score=0.0,
            backtests=backtests,
            recommendation=recommendation,
            disclaimer=advisory_payload(),
            data_source=self._data_source_label(candles_by_mode, request),
            data_quality=data_quality,
            trade_readiness="Data unavailable",
            confidence_breakdown=self._confidence_breakdown(0.0, 0.0, backtests[0], recommendation),
        )

    def _empty_technical_result(self, mode: AnalysisMode) -> TechnicalAnalysisResult:
        return TechnicalAnalysisResult(
            mode=mode,
            signal="unknown",
            score=0.0,
            indicators={},
            summary="No live OHLCV candles were available for technical analysis.",
        )

    def _enforce_strict_buy_gate(
        self,
        symbol: str,
        request: AnalysisRequest,
        recommendation,
        technical_results: list,
        backtests: list,
        candles_by_mode: dict[AnalysisMode, list],
        data_quality: dict[str, str | int | bool | float],
    ):
        # If recommendation is not BUY, nothing to enforce
        if recommendation.action != "BUY":
            self.logger.debug("STRICT BUY GATE SKIP | symbol=%s | recommendation=%s", symbol, recommendation.action)
            return recommendation

        primary_plan = recommendation.trade_plans[0] if recommendation.trade_plans else None
        best_technical = max(technical_results, key=lambda item: item.score)
        best_backtest = max(backtests, key=lambda item: item.total_return)

        # Log a compact diagnostic snapshot for debugging why BUY may be blocked
        try:
            self.logger.info(
                "STRICT BUY GATE EVALUATE | symbol=%s | rec_score=%.2f | rec_conf=%.2f | best_tech_score=%.2f | backtest_verdict=%s | backtest_return=%.2f | plan_rw=%s | data_source=%s | mock_warning=%s | min_candles_met=%s",
                symbol,
                float(recommendation.score),
                float(recommendation.confidence),
                float(best_technical.score) if best_technical is not None else 0.0,
                getattr(best_backtest, "verdict", "n/a"),
                float(getattr(best_backtest, "total_return", 0.0)),
                (primary_plan.risk_reward_ratio if primary_plan and getattr(primary_plan, "risk_reward_ratio", None) is not None else None),
                data_quality.get("source"),
                data_quality.get("mock_warning"),
                data_quality.get("minimum_swing_candles_met"),
            )
        except Exception:
            # Don't let logging issues break flow
            pass

        strong_live_data = (
            not bool(data_quality.get("mock_warning"))
            and bool(data_quality.get("minimum_swing_candles_met"))
            and data_quality.get("source") == "FYERS_PRIMARY"
        )
        strong_execution = bool(
            primary_plan is not None
            and getattr(primary_plan, "risk_reward_ratio", None) is not None
            and primary_plan.risk_reward_ratio >= 1.25
        )
        supportive_backtest = bool(
            best_backtest is not None
            and getattr(best_backtest, "verdict", None) in {"favorable", "mixed"}
        )
        strong_technical = bool(best_technical is not None and float(best_technical.score) >= 75)

        self.logger.debug(
            "STRICT BUY GATE CHECK | symbol=%s | strong_live_data=%s | strong_technical=%s | strong_execution=%s | supportive_backtest=%s",
            symbol,
            strong_live_data,
            strong_technical,
            strong_execution,
            supportive_backtest,
        )

        # Only allow BUY when all strict confirmations are present
        if strong_live_data and strong_technical and strong_execution:
            self.logger.info("STRICT BUY GATE PASS | symbol=%s | BUY allowed", symbol)
            return recommendation

        # Downgrade to WATCH and log reasons
        updated_risks = list(recommendation.reasoning.risk_factors)
        updated_risks.append(
            "Strict BUY gate blocked this setup because live-data quality, backtest strength, or risk-reward confirmation was not strong enough."
        )
        try:
            self.logger.info(
                "STRICT BUY GATE DOWNGRADE | symbol=%s | downgraded_to=WATCH | rec_score=%.2f | rec_conf=%.2f | best_tech_score=%.2f | plan_rw=%s | data_source=%s | mock_warning=%s | min_candles_met=%s | backtest_verdict=%s",
                symbol,
                float(recommendation.score),
                float(recommendation.confidence),
                float(best_technical.score) if best_technical is not None else 0.0,
                (primary_plan.risk_reward_ratio if primary_plan and getattr(primary_plan, "risk_reward_ratio", None) is not None else None),
                data_quality.get("source"),
                data_quality.get("mock_warning"),
                data_quality.get("minimum_swing_candles_met"),
                getattr(best_backtest, "verdict", "n/a"),
            )
        except Exception:
            pass

        return recommendation.model_copy(
            update={
                "action": "WATCH",
                "reasoning": recommendation.reasoning.model_copy(update={"risk_factors": updated_risks}),
                "summary": f"{recommendation.summary} BUY was downgraded to WATCH by the strict confirmation gate.",
            }
        )

    def _trade_readiness(self, recommendation, technical_results: list, data_quality: dict[str, str | int | bool | float]) -> str:
        best_technical = max(technical_results, key=lambda item: item.score)
        plan = recommendation.trade_plans[0] if recommendation.trade_plans else None
        if bool(data_quality.get("mock_warning")):
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
        if backtest.verdict == "insufficient" or backtest.trade_count < 5:
            backtest_component = 0.0
        else:
            backtest_component = round(min(max(backtest.total_return * 2, -5), 25), 2)
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
