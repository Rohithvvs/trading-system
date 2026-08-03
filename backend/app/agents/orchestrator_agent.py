from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os
import threading
from typing import Any

_db_lock = threading.Lock()

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..models import AnalysisHistory, BacktestHistory, WatchedStock
from ..schemas import (
    AnalysisMode,
    AnalysisRequest,
    AnalysisResponse,
    FullAnalysisResponse,
    OHLCVPoint,
    ScreenerStageSummary,
    ScreenerRequest,
    ScreenerResponse,
    ShadowExecutionContext,
    StockAnalysisResult,
    TechnicalAnalysisResult,
)
from ..services.fyers_service import FyersService
from ..services.screener_service import ScreenerService
from ..utils import advisory_payload, get_logger, safe_int
from .backtest_agent import BacktestAgent
from .news_analysis_agent import NewsAnalysisAgent
from .ranking_agent import RankingAgent
from .recommendation_agent import RecommendationAgent
from .technical_analysis_agent import TechnicalAnalysisAgent
from .fundamental_analysis_agent import FundamentalAnalysisAgent

# Spec §5: dedicated shadow observability stream (FEAT-011 Spec 1).
shadow_logger = get_logger("app.shadow_executor")

# Hardening (audit M4): bound shadow executor latency on the request path.
# Spec 5 may move execution off-thread; until then never wait indefinitely.
_SHADOW_EXECUTOR_TIMEOUT_SECONDS = 5.0
_TRUSTED_OHLCV_SOURCES = {"FYERS_PRIMARY", "CANDLE_CACHE_DB"}


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
        self.fundamental_agent = FundamentalAnalysisAgent()

    async def run_full(self, request: AnalysisRequest, progress_callback=None, prefetched_candles: dict[str, dict[AnalysisMode, list[OHLCVPoint]]] | None = None) -> FullAnalysisResponse:
        self.logger.info(
            "Starting full analysis | symbols=%s | mode=%s | intraday=%s | swing=%s | lookback=%s",
            ",".join(request.symbols),
            request.mode.value,
            request.timeframe.intraday,
            request.timeframe.swing,
            request.timeframe.lookback_window,
        )
        import asyncio
        from ..services.re001.scan_context import (
            get_scan_run_id,
            new_scan_run_id,
            reset_scan_run_id,
            set_scan_run_id,
        )

        # Stable scan cohort id for RE-001 lab decisions (FR-027)
        _scan_tok = None
        if not get_scan_run_id():
            _scan_tok = set_scan_run_id(new_scan_run_id("full"))
        try:
            return await self._run_full_impl(
                request,
                progress_callback=progress_callback,
                prefetched_candles=prefetched_candles,
            )
        finally:
            if _scan_tok is not None:
                reset_scan_run_id(_scan_tok)

    async def _run_full_impl(
        self,
        request: AnalysisRequest,
        progress_callback=None,
        prefetched_candles: dict[str, dict[AnalysisMode, list[OHLCVPoint]]] | None = None,
    ) -> FullAnalysisResponse:
        import asyncio

        modes = self._resolve_modes(request.mode)

        # Seed from screener prefetched candles when available (avoids duplicate OHLCV fetch).
        # IMPORTANT: prefetched dict may be a *partial* map (shortlist ∩ frames with ≥220 bars).
        # Always fill missing request.symbols so analysis never KeyErrors.
        #
        # When Authoritative Candle Store is ON, do NOT use parallel screener arrays as the
        # analysis source of truth. Warm L1 from normalized prefetch, then resolve every
        # symbol through ACS.get_candles so scanner/analysis share one owner (US1 / FR-001).
        acs_enabled = settings.is_authoritative_candle_store_enabled()
        candles_by_symbol_and_mode: dict[str, dict[AnalysisMode, list[OHLCVPoint]]] = {}
        if prefetched_candles and not acs_enabled:
            candles_by_symbol_and_mode = dict(prefetched_candles)
        elif prefetched_candles and acs_enabled:
            try:
                from ..services.authoritative_candle_store import authoritative_candle_store
                from ..services.candle_validation_engine import validate_candle_series

                for sym, mode_map in prefetched_candles.items():
                    for mode, points in (mode_map or {}).items():
                        if not points:
                            continue
                        # Preserve UTC awareness — never strip tz before L1 seed
                        normalized = []
                        for p in points:
                            ts = p.timestamp
                            if getattr(ts, "tzinfo", None) is None:
                                from datetime import timezone as _tz

                                ts = ts.replace(tzinfo=_tz.utc)
                                p = p.model_copy(update={"timestamp": ts})
                            normalized.append(p)
                        validated = validate_candle_series(normalized)
                        resolution = self._resolution_for_mode(mode, request)
                        authoritative_candle_store.cache.set(sym, str(resolution), validated)
            except Exception as warm_exc:
                self.logger.debug(
                    "ACS L1 warm from prefetch failed | error=%s",
                    warm_exc,
                )

        prefetched_count = len(prefetched_candles or {}) if prefetched_candles else 0
        missing_for_fetch = [s for s in request.symbols if s not in candles_by_symbol_and_mode]
        self.logger.info(
            "ANALYSIS_CANDLE_INPUT | requested=%s | prefetched=%s | missing_need_fetch=%s | acs=%s | missing_symbols=%s",
            len(request.symbols),
            prefetched_count,
            len(missing_for_fetch),
            acs_enabled,
            ",".join(missing_for_fetch[:20]) + ("..." if len(missing_for_fetch) > 20 else ""),
        )

        async def fetch_for_symbol(symbol: str) -> dict[AnalysisMode, list[OHLCVPoint]]:
            import time
            from ..services.market_data_service import MarketDataService
            start = time.perf_counter()
            candles_by_mode: dict[AnalysisMode, list[OHLCVPoint]] = {}

            # Authoritative path: single owner for all modes (C3).
            if settings.is_authoritative_candle_store_enabled():
                try:
                    from ..services.authoritative_candle_store import authoritative_candle_store

                    for mode in modes:
                        resolution = self._resolution_for_mode(mode, request)
                        candles_by_mode[mode] = await authoritative_candle_store.get_candles(
                            symbol=symbol,
                            resolution=str(resolution),
                        )
                except Exception as exc:
                    self.logger.error(
                        "ACS_OHLCV_FETCH_FAILED | symbol=%s | error=%s | marking empty",
                        symbol,
                        exc,
                    )
                    for mode in modes:
                        candles_by_mode.setdefault(mode, [])
                elapsed = time.perf_counter() - start
                total_rows = sum(len(c) for c in candles_by_mode.values())
                self.logger.info(
                    "OHLCV_FETCH_DONE | symbol=%s | source=acs | rows=%s | elapsed_ms=%.0f",
                    symbol,
                    total_rows,
                    elapsed * 1000,
                )
                return candles_by_mode

            md_service = MarketDataService()
            for mode in modes:
                resolution = self._resolution_for_mode(mode, request)
                if mode == AnalysisMode.swing and str(resolution).lower() in {"1d", "1D", "d", "day", "daily"}:
                    try:
                        df = await md_service.load_full_history(symbol, "1D")
                        if df is not None and not df.empty and len(df) >= 220:
                            points: list = []
                            for ts, row in df.iterrows():
                                dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
                                if getattr(dt, "tzinfo", None) is not None:
                                    dt = dt.replace(tzinfo=None)
                                points.append(
                                    OHLCVPoint(
                                        timestamp=dt,
                                        open=float(row["open"]),
                                        high=float(row["high"]),
                                        low=float(row["low"]),
                                        close=float(row["close"]),
                                        volume=safe_int(row["volume"], symbol=symbol, field="volume"),
                                    )
                                )
                            candles_by_mode[mode] = points
                            self.fyers_service._store_ohlcv_cache(
                                (self.fyers_service._cache_symbol(symbol), mode.value, resolution.lower()),
                                request.timeframe.lookback_window,
                                points,
                                "CANDLE_CACHE_DB",
                            )
                            continue
                    except Exception as exc:
                        self.logger.warning(
                            "DB OHLCV reuse failed, falling back to live fetch | symbol=%s | error=%s",
                            symbol,
                            exc,
                        )
                try:
                    candles_by_mode[mode] = await self.fyers_service.fetch_ohlcv(
                        symbol=symbol,
                        mode=mode,
                        resolution=resolution,
                        lookback_window=request.timeframe.lookback_window,
                    )
                except Exception as exc:
                    self.logger.error(
                        "OHLCV_FETCH_FAILED | symbol=%s | mode=%s | error=%s | marking empty",
                        symbol,
                        mode.value,
                        exc,
                    )
                    candles_by_mode[mode] = []
            elapsed = time.perf_counter() - start
            total_rows = sum(len(c) for c in candles_by_mode.values())
            self.logger.info(
                "OHLCV_FETCH_DONE | symbol=%s | rows=%s | elapsed_ms=%.0f",
                symbol,
                total_rows,
                elapsed * 1000,
            )
            return candles_by_mode

        if missing_for_fetch:
            async def prefetch_missing():
                sem = asyncio.Semaphore(20)

                async def _bounded(symbol: str):
                    async with sem:
                        candles_by_symbol_and_mode[symbol] = await fetch_for_symbol(symbol)

                await asyncio.gather(*(_bounded(symbol) for symbol in missing_for_fetch))

            await prefetch_missing()

        downloaded = [
            s for s in request.symbols
            if any(candles_by_symbol_and_mode.get(s, {}).get(m) for m in modes)
        ]
        still_missing = [s for s in request.symbols if s not in downloaded]
        self.logger.info(
            "ANALYSIS_CANDLE_READY | downloaded=%s | data_unavailable=%s | unavailable_symbols=%s",
            len(downloaded),
            len(still_missing),
            ",".join(still_missing[:20]) + ("..." if len(still_missing) > 20 else ""),
        )

        # Build the bulk candles dictionary for the technical matrix
        candles_dict_by_mode = {mode: {} for mode in modes}
        for symbol, c_map in candles_by_symbol_and_mode.items():
            if not isinstance(c_map, dict):
                continue
            for mode in modes:
                series = c_map.get(mode) or []
                if series:
                    candles_dict_by_mode[mode][symbol] = series
                    
        if progress_callback:
            progress_callback({"stage": "Calculating Technical Indicators...", "progress": 55, "heartbeat": True})
        # Execute the vectorized bulk technical analysis once
        bulk_technical_results = {}
        for mode in modes:
            self.logger.info("Executing batched deep analysis | mode=%s | symbols=%s", mode.value, len(candles_dict_by_mode[mode]))
            bulk_technical_results[mode] = self.technical_agent.run_bulk(candles_dict_by_mode[mode], mode)
            
        if progress_callback:
            progress_callback({"stage": "Running AI Pattern Recognition...", "progress": 70, "heartbeat": True})
        # Pre-resolve FEAT-004 benchmark ONCE (was called per-symbol before — HUGE bottleneck)
        feat004_config = self._build_feat004_config()
        feat007_config = self._build_feat007_config()
        benchmark_ohlcv, sector_ohlcv_cache, benchmark_failure_reason, benchmark_symbol = await self._resolve_feat004_benchmark()
        # Pre-resolve market regime once (was called per-symbol before with same scan_date)
        from ..services.market_permission_service import MarketPermissionService
        _primary_candles = next(iter(candles_by_symbol_and_mode.values()), {}).get(modes[0], [])
        _scan_date = _primary_candles[-1].timestamp if _primary_candles else datetime.now(timezone.utc)
        _market_regime = await MarketPermissionService().evaluate_market_permission(scan_date=_scan_date)
        # Batch-resolve stock IDs (avoids per-symbol DB session in _analyze_symbol_post_bulk)
        stock_ids: dict[str, int] = {}
        if request.symbols:
            from sqlalchemy import select as _select
            from ..db.session import AsyncSessionLocal as _AsyncSessionLocal
            async with _AsyncSessionLocal() as _db:
                existing = (await _db.scalars(
                    _select(WatchedStock).where(WatchedStock.symbol.in_(request.symbols))
                )).all()
                for s in existing:
                    stock_ids[s.symbol] = s.id
            # Create missing stocks in batch
            missing = [s for s in request.symbols if s not in stock_ids]
            if missing:
                async with _AsyncSessionLocal() as _db:
                    for sym in missing:
                        stock = WatchedStock(symbol=sym, display_name=sym.replace("-EQ", ""))
                        _db.add(stock)
                    await _db.commit()
                    for sym in missing:
                        stock_ids[sym] = (await _db.scalars(
                            _select(WatchedStock).where(WatchedStock.symbol == sym)
                        )).first().id
        # Dispatch Backtest / News / Fundamental agents with bounded concurrency.
        async def run_remaining_agents():
            agent_sem = asyncio.Semaphore(6)
            completed_count = {"n": 0}
            total_symbols = len(request.symbols)

            async def _one(symbol: str):
                async with agent_sem:
                    candles_by_mode = candles_by_symbol_and_mode.get(symbol)
                    try:
                        if not candles_by_mode or not any(candles_by_mode.get(m) for m in modes):
                            self.logger.warning(
                                "DATA_UNAVAILABLE | symbol=%s | reason=no_ohlcv_after_prefetch_and_fetch | continuing",
                                symbol,
                            )
                            result = self._unavailable_analysis_result(
                                symbol, request, candles_by_mode or {}
                            )
                        else:
                            result = await self._analyze_symbol_post_bulk(
                                symbol,
                                request,
                                candles_by_mode,
                                bulk_technical_results,
                                feat004_config=feat004_config,
                                benchmark_ohlcv=benchmark_ohlcv,
                                benchmark_failure_reason=benchmark_failure_reason,
                                benchmark_symbol=benchmark_symbol,
                                feat007_config=feat007_config,
                                stock_id=stock_ids.get(symbol),
                                market_regime=_market_regime,
                            )
                    except Exception as exc:
                        self.logger.error(
                            "SYMBOL_ANALYSIS_FAILED | symbol=%s | error=%s | marking DATA_UNAVAILABLE",
                            symbol,
                            exc,
                            exc_info=True,
                        )
                        result = self._unavailable_analysis_result(
                            symbol, request, candles_by_symbol_and_mode.get(symbol) or {}
                        )

                    completed_count["n"] += 1
                    done = completed_count["n"]
                    if progress_callback and (done % 5 == 0 or done == total_symbols):
                        pct = 70 + int(15 * done / max(1, total_symbols))
                        progress_callback({
                            "stage": f"Running AI Analysis... ({done}/{total_symbols})",
                            "progress": min(pct, 85),
                            "current_symbol": symbol,
                            "done": done,
                            "remaining": total_symbols - done,
                            "total_scoring": total_symbols,
                        })
                    return result

            return await asyncio.gather(*(_one(symbol) for symbol in request.symbols))

        items = await run_remaining_agents()
        self.logger.info(
            "ANALYSIS_OUTPUT | input_symbols=%s | analyzed_items=%s | buy=%s | watch=%s | reject_or_other=%s",
            len(request.symbols),
            len(items),
            sum(1 for i in items if getattr(i.recommendation, "action", "").upper() == "BUY"),
            sum(1 for i in items if getattr(i.recommendation, "action", "").upper() == "WATCH"),
            sum(1 for i in items if getattr(i.recommendation, "action", "").upper() not in {"BUY", "WATCH"}),
        )

        if progress_callback:
            progress_callback({"stage": "Applying Risk Management Filters...", "progress": 85, "heartbeat": True})
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

    async def run_screener(self, request: ScreenerRequest, progress_callback=None) -> ScreenerResponse:
        from ..services.re001.scan_context import (
            get_scan_run_id,
            new_scan_run_id,
            reset_scan_run_id,
            set_scan_run_id,
        )

        # FR-027: prefer platform scan_id when scan execution already set context.
        _scan_tok = None
        if not get_scan_run_id():
            _scan_tok = set_scan_run_id(new_scan_run_id("screener"))
        try:
            return await self._run_screener_impl(request, progress_callback=progress_callback)
        finally:
            if _scan_tok is not None:
                reset_scan_run_id(_scan_tok)

    async def _run_screener_impl(self, request: ScreenerRequest, progress_callback=None) -> ScreenerResponse:
        if progress_callback:
            progress_callback({"stage": "Authenticating & Waking Agents...", "progress": 15, "heartbeat": True})
        self.logger.info(
            "[SCAN] Starting screener flow | top_n=%s | mode=%s | lookback=%s | custom_symbol_count=%s",
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
            return await self._run_screener_stage(
                request=request,
                stage_name="Custom symbols",
                source_universe=request.symbols,
                duplicate_symbols_skipped=0,
                progress_callback=progress_callback,
            )

        seen_symbols: set[str] = set()
        duplicate_symbols_skipped = 0
        scan_stages: list[ScreenerStageSummary] = []
        final_response: ScreenerResponse | None = None
        stopped_at_stage: str | None = None

        if progress_callback:
            progress_callback({"stage": "Loading Market Universe...", "progress": 20, "heartbeat": True})
        self.logger.info("[SCAN] Loading universe...")
        universes = await self._prioritized_universes()
        self.logger.info(
            "[SCAN] Universe loaded | stages=%s | stage_list=%s",
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

            stage_response = await self._run_screener_stage(
                request=request,
                stage_name=stage_name,
                source_universe=unique_symbols,
                duplicate_symbols_skipped=skipped,
                progress_callback=progress_callback,
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

    async def _run_screener_stage(
        self,
        request: ScreenerRequest,
        stage_name: str,
        source_universe: list[str],
        duplicate_symbols_skipped: int,
        progress_callback=None,
    ) -> ScreenerResponse:
        if progress_callback:
            progress_callback({"stage": "Downloading candles...", "progress": 35, "heartbeat": True})
        self.logger.info(
            "[SCAN] Downloading candles | stage=%s | symbols=%s",
            stage_name,
            len(source_universe),
        )
        screener_results = await self.screener_service.screen_symbols_swing(
            source_universe,
            lookback_window=request.timeframe.lookback_window,
            stage_name=stage_name,
            progress_callback=progress_callback,
        )
        self.logger.info(
            "[SCAN] Candle/screener stage complete | stage=%s | results=%s",
            stage_name,
            len(screener_results),
        )
        data_valid_symbols = [
            item.symbol
            for item in screener_results
            if not item.conditions.get("data_source_failed", False) and not item.conditions.get("data_quality_failed", False)
        ]
        eligible_results = [item for item in screener_results if item.conditions.get("broad_trend_eligibility", False)]
        matched_results = [item for item in screener_results if item.matched]
        matched_results.sort(key=lambda item: (-item.screener_score, item.symbol))
        self._log_determinism_debug(
            {
                "event": "matched_results_sorted",
                "stage": stage_name,
                "items": [
                    {
                        "symbol": item.symbol,
                        "screener_score": item.screener_score,
                        "sort_tuple": [-item.screener_score, item.symbol],
                    }
                    for item in matched_results
                ],
            }
        )
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
            # Reuse OHLCV data from screener phase (avoids duplicate FYERS fetch).
            # May be partial — run_full fills any shortlisted symbol still missing.
            prefetched_candles: dict[str, dict[AnalysisMode, list[OHLCVPoint]]] = {}
            screener_frames = getattr(self.screener_service, "last_fetched_frames", {}) or {}
            # Build canonical→frame key index so RAIN-EQ finds RAIN / NSE:RAIN-EQ frames
            frame_by_canonical: dict[str, str] = {}
            for frame_key in screener_frames.keys():
                frame_by_canonical[self._canonical_symbol(frame_key)] = frame_key

            from ..schemas import AnalysisMode as AM
            for sym in shortlisted_symbols:
                df = screener_frames.get(sym)
                if df is None:
                    alt_key = frame_by_canonical.get(self._canonical_symbol(sym))
                    if alt_key is not None:
                        df = screener_frames.get(alt_key)
                        if df is not None:
                            self.logger.info(
                                "PREFETCH_SYMBOL_KEY_MAP | shortlist=%s | frame_key=%s",
                                sym,
                                alt_key,
                            )
                if df is not None and not getattr(df, "empty", True):
                    points = []
                    for ts, row in df.iterrows():
                        dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
                        if getattr(dt, "tzinfo", None) is not None:
                            dt = dt.replace(tzinfo=None)
                        points.append(OHLCVPoint(
                            timestamp=dt,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=safe_int(row["volume"], symbol=sym, field="volume"),
                        ))
                    if len(points) >= 220:
                        # When ACS is enabled, keep timezone-aware UTC timestamps so L1
                        # range checks do not mix naive/aware datetimes.
                        if settings.is_authoritative_candle_store_enabled():
                            from datetime import timezone as _tz

                            utc_points = []
                            for p in points:
                                ts = p.timestamp
                                if getattr(ts, "tzinfo", None) is None:
                                    ts = ts.replace(tzinfo=_tz.utc)
                                elif ts.tzinfo != _tz.utc:
                                    ts = ts.astimezone(_tz.utc)
                                utc_points.append(p.model_copy(update={"timestamp": ts}))
                            points = utc_points
                        prefetched_candles[sym] = {AM.swing: points}
                        try:
                            resolution = self._resolution_for_mode(AM.swing, analysis_request)
                            self.fyers_service._store_ohlcv_cache(
                                (
                                    self.fyers_service._cache_symbol(sym),
                                    AM.swing.value,
                                    str(resolution).lower(),
                                ),
                                analysis_request.timeframe.lookback_window,
                                points,
                                "CANDLE_CACHE_DB",
                            )
                        except Exception as cache_exc:
                            self.logger.debug(
                                "prefetch source register failed | symbol=%s | error=%s",
                                sym,
                                cache_exc,
                            )
                        if settings.is_authoritative_candle_store_enabled():
                            try:
                                from ..services.authoritative_candle_store import authoritative_candle_store
                                from ..services.candle_validation_engine import validate_candle_series

                                authoritative_candle_store.cache.set(
                                    sym, str(resolution), validate_candle_series(points)
                                )
                            except Exception:
                                pass
            missing_prefetch = [s for s in shortlisted_symbols if s not in prefetched_candles]
            self.logger.info(
                "PREFETCH_FROM_SCREENER | shortlisted=%s | prefetched=%s | missing=%s | missing_symbols=%s",
                len(shortlisted_symbols),
                len(prefetched_candles),
                len(missing_prefetch),
                ",".join(missing_prefetch) if missing_prefetch else "none",
            )
            # Release frames from memory after extracting prefetched candles
            if hasattr(screener_frames, "clear"):
                screener_frames.clear()
            self.screener_service.last_fetched_frames = {}
            shortlist_analysis = await self.run_full(
                analysis_request,
                progress_callback,
                prefetched_candles=prefetched_candles,
            )
            buy_items = [item for item in shortlist_analysis.items if item.recommendation.action == "BUY"]
            watch_items = [item for item in shortlist_analysis.items if item.recommendation.action == "WATCH"]
            reject_items = [item for item in shortlist_analysis.items if item.recommendation.action == "REJECT"]
            buy_candidate_symbols = [item.symbol for item in buy_items]
            watch_candidate_symbols = [item.symbol for item in watch_items]
            self.logger.info(
                "STEP 7/8 | RecommendationAgent finished | stage=%s | buy=%s | watch=%s | reject=%s",
                stage_name,
                len(buy_items),
                len(watch_items),
                len(reject_items),
            )
            # Keep REJECT results in the payload so the UI still receives the real
            # composite score, confidence, trade plan, and equity curve.
            # (Previously only BUY+WATCH were returned, so REJECT rows fell back to
            # screener_score — often ~100 — with empty entry/SL/TP/confidence.)
            analysis_items = buy_items + watch_items + reject_items
            analysis = FullAnalysisResponse(
                items=analysis_items,
                rankings=self.ranking_agent.run(buy_items + watch_items),
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

    async def _prioritized_universes(self) -> list[tuple[str, list[str]]]:
        from ..services.universe_service import UniverseService
        stages = []
        for u in ["NIFTY500", "NIFTY100", "FNO", "CUSTOM"]:
            symbols = await UniverseService.get_active_symbols(u)
            if symbols:
                stages.append((u, symbols))
        return stages

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

    def _log_determinism_debug(self, payload: dict[str, object]) -> None:
        if os.getenv("SCANNER_DETERMINISM_DEBUG", "").strip().lower() not in {"1", "true", "yes", "on"}:
            return
        self.logger.info("SCANNER_DETERMINISM %s", json.dumps(payload, sort_keys=True, default=str))

    def _build_feat004_config(self) -> dict[str, Any]:
        """Build the nested feat004_config dict from flat settings fields.

        The overlay module reads nested keys (score_deltas, buy_downgrade_thresholds),
        so we construct the dict here to avoid duplicating the defaults.
        """
        feat004_enabled = getattr(settings, "feat004_enabled", False)
        feat004_stage = getattr(settings, "feat004_stage", "SHADOW")
        feat004_score_delta_fav = getattr(settings, "feat004_score_delta_fav", 2.0)
        feat004_score_delta_neu = getattr(settings, "feat004_score_delta_neu", 0.0)
        feat004_score_delta_cau = getattr(settings, "feat004_score_delta_cau", -3.0)
        feat004_score_delta_def = getattr(settings, "feat004_score_delta_def", -5.0)
        feat004_score_delta_abs = getattr(settings, "feat004_score_delta_abs", 0.0)
        feat004_buy_downgrade_threshold_cau = getattr(settings, "feat004_buy_downgrade_threshold_cau", 74.0)
        feat004_buy_downgrade_threshold_def = getattr(settings, "feat004_buy_downgrade_threshold_def", 77.0)
        feat004_buy_threshold = getattr(settings, "feat004_buy_threshold", 72.0)
        feat004_favorable_cap_below_buy = getattr(settings, "feat004_favorable_cap_below_buy", True)
        feat004_sector_mapping_enabled = getattr(settings, "feat004_sector_mapping_enabled", True)
        feat004_sector_min_candles = getattr(settings, "feat004_sector_min_candles", 50)
        return {
            "enabled": feat004_enabled,
            "stage": feat004_stage,
            "score_deltas": {
                "FAV": feat004_score_delta_fav,
                "NEU": feat004_score_delta_neu,
                "CAU": feat004_score_delta_cau,
                "DEF": feat004_score_delta_def,
                "ABS": feat004_score_delta_abs,
            },
            "buy_downgrade_thresholds": {
                "CAU": feat004_buy_downgrade_threshold_cau,
                "DEF": feat004_buy_downgrade_threshold_def,
            },
            "buy_threshold": feat004_buy_threshold,
            "favorable_cap_below_buy": feat004_favorable_cap_below_buy,
            "sector_mapping_enabled": feat004_sector_mapping_enabled,
            "sector_min_candles": feat004_sector_min_candles,
        }

    def _build_feat007_config(self) -> dict[str, Any]:
        """Build the feat007_config dict from flat settings fields.

        Per FEAT-007 v1.1 spec and ADR-003 (difference formula).
        """
        feat007_enabled = getattr(settings, "feat007_enabled", False)
        feat007_stage = getattr(settings, "feat007_stage", "SHADOW")
        feat007_score_delta_strength = getattr(settings, "feat007_score_delta_strength", 1.5)
        feat007_score_delta_weak = getattr(settings, "feat007_score_delta_weak", -3.0)
        feat007_buy_downgrade_threshold = getattr(settings, "feat007_buy_downgrade_threshold", 74.0)
        feat007_buy_threshold = getattr(settings, "feat007_buy_threshold", 72.0)
        feat007_strength_cap_enabled = getattr(settings, "feat007_strength_cap_enabled", True)
        return {
            "enabled": feat007_enabled,
            "stage": feat007_stage,
            "score_delta_strength": feat007_score_delta_strength,
            "score_delta_weak": feat007_score_delta_weak,
            "buy_downgrade_threshold": feat007_buy_downgrade_threshold,
            "buy_threshold": feat007_buy_threshold,
            "strength_cap_enabled": feat007_strength_cap_enabled,
        }

    async def _resolve_feat004_benchmark(self) -> tuple[Any, dict[str, list] | None, str | None, str | None]:
        """Fetch benchmark index OHLCV for FEAT-004 regime overlay.

        Returns (DataFrame | None, sector_ohlcv_cache | None, failure_reason | None, benchmark_symbol | None).
        The overlay expects benchmark_ohlcv as a DataFrame with a 'close'
        column indexed by timestamp.  When feat004 is disabled or fetching
        fails, returns (None, None, reason, None) — the overlay handles that safely.
        On a successful resolution, the 4th element is the resolved benchmark
        symbol (e.g. "NIFTY500" / "NIFTY50") so it can be logged as
        benchmark_symbol_used.  The failure_reason preserves the specific
        benchmark failure taxonomy for auditing (benchmark_fetch_failed,
        insufficient_benchmark_history, benchmark_data_stale).
        """
        feat004_enabled = getattr(settings, "feat004_enabled", False)
        if not feat004_enabled:
            return None, None, None, None

        import pandas as pd
        from ..schemas import AnalysisMode

        bm_symbols_raw = getattr(settings, "feat004_benchmark_symbols", "NIFTY500")
        bm_symbols = [s.strip() for s in bm_symbols_raw.split(",") if s.strip()]
        min_candles = getattr(settings, "feat004_min_benchmark_candles", 220)

        # Remember the specific reason the last candidate failed so the
        # overlay can audit it.  Initialised to the legacy default so the
        # zero-symbol edge case preserves its prior return value.
        last_failure_reason: str | None = "benchmark_fetch_failed"

        for bm_sym in bm_symbols:
            try:
                candles = await self.fyers_service.fetch_ohlcv(
                    bm_sym, AnalysisMode.swing, "1D", min_candles,
                )
            except Exception as exc:
                self.logger.warning(
                    "FEAT-004: benchmark fetch failed for %s: %s", bm_sym, exc,
                )
                last_failure_reason = "benchmark_fetch_failed"
                continue

            if not candles or len(candles) < min_candles:
                self.logger.info(
                    "FEAT-004: %s returned %d candles (need %d)",
                    bm_sym, len(candles) if candles else 0, min_candles,
                )
                last_failure_reason = "insufficient_benchmark_history"
                continue

            df = pd.DataFrame(
                [
                    {
                        "timestamp": c.timestamp,
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                    }
                    for c in candles
                ]
            )
            df = df.set_index("timestamp").sort_index()

            try:
                last_ts = df.index[-1]
                if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - last_ts).days
                staleness_limit_days = getattr(settings, "feat004_staleness_limit_days", 1)
                if age_days > staleness_limit_days:
                    self.logger.warning(
                        "FEAT-004: %s last candle is %d day(s) old (limit=%d).",
                        bm_sym,
                        age_days,
                        staleness_limit_days,
                    )
                    last_failure_reason = "benchmark_data_stale"
                    continue
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(
                    "FEAT-004: staleness check failed for %s: %s", bm_sym, exc,
                )
                last_failure_reason = "benchmark_data_stale"
                continue

            self.logger.info(
                "FEAT-004: benchmark %s resolved (%d candles)", bm_sym, len(df),
            )
            return df, None, None, bm_sym

        self.logger.warning("FEAT-004: no benchmark data available from %s", bm_symbols)
        return None, None, last_failure_reason, None

    async def _analyze_symbol_post_bulk(
        self, 
        symbol: str, 
        request: AnalysisRequest, 
        candles_by_mode: dict[AnalysisMode, list[OHLCVPoint]],
        bulk_technical_results: dict[AnalysisMode, dict[str, TechnicalAnalysisResult]],
        feat004_config: dict | None = None,
        benchmark_ohlcv: Any = None,
        benchmark_failure_reason: str | None = None,
        benchmark_symbol: str | None = None,
        feat007_config: dict | None = None,
        stock_id: int | None = None,
        market_regime: Any = None,
    ) -> StockAnalysisResult:
        import asyncio
        if stock_id is None:
            stock_id = await self._get_or_create_stock(symbol)
        modes = self._resolve_modes(request.mode)
        
        if any(not candles for candles in candles_by_mode.values()):
            self.logger.warning(
                "Skipping post-bulk analysis because live OHLCV is unavailable | symbol=%s",
                symbol,
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

        
        def safe_news_run(sym: str):
            try:
                articles, sentiment_score, sentiment_label, news_summary = self.news_agent.run(sym)
                if not articles:
                    return [], 0.5, "NEUTRAL", "No recent news found"
                return articles, sentiment_score, sentiment_label, news_summary
            except Exception as e:
                self.logger.error("News API failed for %s: %s", sym, e)
                return [], 0.5, "NEUTRAL", "No recent news found"

        # FEAT-008 — execution model and composite source are independent controls
        if not settings.feat008_enabled:
            exec_model = "LEGACY"
            use_realistic_for_composite = False
            skip_on_missing_next_bar = False
        else:
            exec_model = settings.feat008_execution_model
            use_realistic_for_composite = settings.feat008_composite_uses_realistic
            skip_on_missing_next_bar = settings.feat008_skip_on_missing_next_bar

        async def _run_agents_concurrently():
            def run_backtest():
                results = []
                for mode in modes:
                    try:
                        results.append(self.backtest_agent.run(
                            symbol, mode, candles_by_mode[mode],
                            execution_model=exec_model,
                            composite_uses_realistic=use_realistic_for_composite,
                            skip_on_missing_next_bar=skip_on_missing_next_bar,
                            feat008_enabled=settings.feat008_enabled,
                        ))
                    except Exception as e:
                        self.logger.error("Backtest agent failed for %s in %s mode: %s", symbol, mode.value, e)
                        from ..schemas.analysis import BacktestResult
                        results.append(BacktestResult(
                            mode=mode,
                            strategy_name="error_fallback",
                            total_return=0.0,
                            cagr=0.0,
                            max_drawdown=0.0,
                            win_rate=0.0,
                            profit_factor=0.0,
                            trade_count=0,
                            verdict="Failed",
                            equity_curve=[],
                            feat008_enabled=settings.feat008_enabled,
                        ))
                return results

            return await asyncio.gather(
                asyncio.to_thread(run_backtest),
                asyncio.to_thread(safe_news_run, symbol),
                asyncio.to_thread(self.fundamental_agent.run, symbol)
            )

        backtests, (articles, sentiment_score, sentiment_label, news_summary), fundamental_result = await _run_agents_concurrently()

        composite_backtests = self._resolve_composite_backtests(
            backtests, use_realistic_for_composite
        )

        # Retrieve the pre-computed vectorized technical results
        technical_results = []
        for mode in modes:
            tech_res = bulk_technical_results[mode].get(symbol)
            if not tech_res:
                 # Fallback empty result if omitted from bulk
                 from ..schemas import TechnicalAnalysisResult
                 tech_res = TechnicalAnalysisResult(mode=mode, signal="neutral", score=0.0, indicators={}, summary="No technical data")
            technical_results.append(tech_res)

        technical_score = max(result.score for result in technical_results)
        best_backtest = max(backtests, key=lambda item: item.total_return)

        # FEAT-004: use pre-resolved benchmark (fetched once in run_full, not per-symbol)
        if feat004_config is None:
            feat004_config = self._build_feat004_config()
        if benchmark_ohlcv is None:
            benchmark_ohlcv, sector_ohlcv_cache, benchmark_failure_reason, benchmark_symbol = await self._resolve_feat004_benchmark()
        else:
            sector_ohlcv_cache = None
        sector_mapping = None  # Reserved for future sector-strength integration

        # ------------------------------------------------------------------
        # SR-003: Evaluate sector relative strength BEFORE the recommendation
        # agent so that FEAT-007 can consume the difference-formula
        # sector_rs_20 value as its sector_rs_value input.
        # The same sector_overlay result is reused post-Gate for the
        # challenger downgrade — no duplicate calculation.
        # ------------------------------------------------------------------
        from ..services.sector_rs_service import SectorRelativeStrengthService
        from ..schemas import FinalRecommendation as FR, RecommendationReasoning
        sector_rs_service = SectorRelativeStrengthService()
        primary_candles = candles_by_mode.get(modes[0], [])
        scan_date = primary_candles[-1].timestamp if primary_candles else datetime.now(timezone.utc)

        sector_overlay = await sector_rs_service.evaluate_sector_overlay(
            symbol=symbol,
            scan_date=scan_date,
            original_recommendation=FR(
                action="WATCH", confidence=0.5, score=50.0,
                reasoning=RecommendationReasoning(bullets=[], risk_factors=[], invalidation_signals=[]),
                trade_plans=[], summary="placeholder",
            ),
        )

        # Extract sector_rs_value from SR-003's difference-formula output
        # for FEAT-007 consumption. None when unmapped/insufficient/failed.
        sector_rs_value = sector_overlay.sector_rs_20
        sector_index_symbol = sector_overlay.mapped_sector
        sector_roc20 = sector_overlay.sector_roc20
        benchmark_roc20 = sector_overlay.nifty50_roc20
        feat007_abstained_reason = sector_overlay.feat007_abstained_reason

        # FEAT-007: use pre-resolved config
        if feat007_config is None:
            feat007_config = self._build_feat007_config()

        # Stage 2: when market_breadth is production, compute live soft contribution.
        # Fail-open to 0.0 so scan path never aborts on breadth errors.
        market_breadth_soft_score: float | None = None
        try:
            from ..governance.rule_manager import RuleManager
            from ..services.market_breadth import calculate_market_breadth

            if RuleManager().is_active_in_production("market_breadth"):
                breadth_items = self._universe_breadth_items_from_bulk(bulk_technical_results)
                breadth_telemetry = calculate_market_breadth(breadth_items)
                market_breadth_soft_score = float(breadth_telemetry.soft_score_contribution)
                if not breadth_telemetry.is_valid:
                    shadow_logger.warning(
                        "breadth_telemetry_unreliable | symbol=%s | soft=%s | action=use_soft_anyway",
                        symbol,
                        market_breadth_soft_score,
                    )
        except Exception as breadth_live_exc:
            shadow_logger.warning(
                "governance_fail_open | symbol=%s | rule=market_breadth | error=%s | action=soft_score_0",
                symbol,
                breadth_live_exc,
            )
            market_breadth_soft_score = 0.0

        recommendation = await asyncio.to_thread(
            self.recommendation_agent.run,
            symbol=symbol,
            technical_results=technical_results,
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            fundamental_result=fundamental_result,
            backtests=composite_backtests,
            candles_by_mode=candles_by_mode,
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

        # Reuse the sector_overlay from the pre-recommendation evaluation.
        # All computed fields (sector_rs_20, downgrade_triggered, mapped_sector,
        # sector_close, etc.) are identical because they depend only on symbol
        # and scan_date — not on the recommendation. The original_action and
        # challenger_action fields are updated below after the challenger is built.
        # No second SR-003 evaluation is needed.

        # Integrate SR-004 Market Permission Engine (pre-resolved in run_full to avoid per-symbol re-evaluation)
        if market_regime is None:
            from ..services.market_permission_service import MarketPermissionService
            market_regime = await MarketPermissionService().evaluate_market_permission(scan_date=scan_date)

        # Build Challenger recommendation (combining sector overlay and market permission)
        challenger_action = recommendation.action
        challenger_score = recommendation.score
        challenger_confidence = recommendation.confidence
        challenger_reasoning = recommendation.reasoning.model_copy()
        challenger_summary = recommendation.summary

        # Apply SR-003 Sector Downgrade first
        if recommendation.action == "BUY" and sector_overlay.downgrade_triggered:
            challenger_action = "WATCH"
            challenger_score = min(challenger_score, 71.0)
            challenger_confidence = round(min(0.95, max(0.35, challenger_score / 100)), 2)

            downgrade_msg = f"Downgraded to WATCH because mapped sector {sector_overlay.mapped_sector} is weak vs NIFTY 50 (RS: {sector_overlay.sector_rs_20:.2f}%)."
            challenger_summary = f"{downgrade_msg} {challenger_summary}"
            challenger_reasoning.bullets = [downgrade_msg] + challenger_reasoning.bullets

        # Apply SR-004 Market Permission Downgrade next
        if challenger_action == "BUY" and not market_regime.new_entry_allowed:
            challenger_action = "WATCH"
            challenger_score = min(challenger_score, 71.0)
            challenger_confidence = round(min(0.95, max(0.35, challenger_score / 100)), 2)

            market_msg = f"Downgraded to WATCH because broad market regime is restrictive ({market_regime.market_state}). Reasons: {', '.join(market_regime.reasons)}"
            challenger_summary = f"{market_msg} {challenger_summary}"
            challenger_reasoning.bullets = [market_msg] + challenger_reasoning.bullets

        from ..schemas import FinalRecommendation
        challenger_recommendation = FinalRecommendation(
            action=challenger_action,
            confidence=challenger_confidence,
            score=challenger_score,
            reasoning=challenger_reasoning,
            trade_plans=recommendation.trade_plans,
            summary=challenger_summary
        )

        # Update sector_overlay actions
        sector_overlay.original_action = recommendation.action
        sector_overlay.challenger_action = challenger_recommendation.action

        analysis_history_id = await self._persist_analysis(
            stock_id=stock_id,
            mode=request.mode.value,
            technical_score=technical_score,
            sentiment_score=sentiment_score,
            backtest=best_backtest,
            recommendation=recommendation,
            sector_overlay=sector_overlay,
            market_regime=market_regime,
            symbol=symbol,
            articles=articles
        )

        # RE-001 lab engine: isolated async, fail-open; never mutates production recommendation.
        re001_decision = None
        try:
            if settings.is_re001_active():
                from ..db.session import SessionLocal
                from ..services.re001 import run_re001_isolated_async
                from ..services.re001.portfolio_loader import load_user_portfolio_dict
                from ..services.re001.scan_context import get_scan_run_id, get_user_id

                primary_candles = self._primary_candle_set(candles_by_mode)
                uid = get_user_id()
                scan_run_id = get_scan_run_id()
                user_portfolio = None
                try:
                    # Bound portfolio DB read separately from RE-001 eval timeout.
                    # timeout_s=0 avoids nested ThreadPool when already on a worker thread.
                    user_portfolio = await asyncio.wait_for(
                        asyncio.to_thread(load_user_portfolio_dict, uid, timeout_s=0),
                        timeout=2.0,
                    )
                except Exception as portfolio_exc:
                    self.logger.warning(
                        "RE-001 portfolio snapshot skipped | symbol=%s | scan_run_id=%s | err=%s",
                        symbol,
                        scan_run_id,
                        portfolio_exc,
                    )
                    user_portfolio = None
                re001_decision = await run_re001_isolated_async(
                    symbol=symbol,
                    mode=request.mode.value,
                    scan_run_id=scan_run_id,
                    candles=primary_candles,
                    technical_results=technical_results,
                    sentiment_score=sentiment_score,
                    fundamental_result=fundamental_result,
                    backtests=backtests or [],
                    production_recommendation=recommendation,
                    market_regime=market_regime,
                    sector_overlay=sector_overlay,
                    market_breadth_soft_score=None,
                    user_portfolio=user_portfolio,
                    risk_settings=None,  # FR-026: no invented system portfolio for unauthenticated scans
                    analysis_history_id=analysis_history_id,
                    db_session_factory=SessionLocal,
                )
        except Exception as re001_exc:
            try:
                from ..services.re001.scan_context import get_scan_run_id as _get_re001_scan

                _re001_scan = _get_re001_scan()
            except Exception:
                _re001_scan = None
            self.logger.warning(
                "RE-001 hook failed (production path unchanged) | symbol=%s | scan_run_id=%s | err=%s",
                symbol,
                _re001_scan,
                re001_exc,
                exc_info=True,
            )
            re001_decision = None

        # FEAT-011 Spec 1: Shadow Execution Context hook
        # Gate: master toggle AND stage != OFF (ACTIVE is reserved but still isolated).
        if settings.is_shadow_hook_enabled():
            try:
                import asyncio

                executor = getattr(self, "shadow_executor", None)
                # Avoid deep-copy overhead when no executor is registered (audit L2).
                if executor is None:
                    shadow_logger.warning(
                        "Shadow executor is enabled but no ruleset executor is registered "
                        "for ruleset %r | symbol=%s. Gracefully skipping.",
                        settings.shadow_mode_ruleset,
                        symbol,
                    )
                else:
                    candles_list = self._primary_candle_set(candles_by_mode)

                    # FR-007: deep-copy all mutable snapshot fields so experimental
                    # logic cannot mutate production recommendation / market inputs.
                    shadow_ctx = ShadowExecutionContext(
                        symbol=symbol,
                        candles=copy.deepcopy(candles_list),
                        technical_results=copy.deepcopy(technical_results),
                        sentiment_score=sentiment_score,
                        fundamental_result=copy.deepcopy(fundamental_result),
                        backtests=copy.deepcopy(backtests) if backtests else [],
                        production_recommendation=copy.deepcopy(recommendation),
                        production_challenger_recommendation=copy.deepcopy(
                            challenger_recommendation
                        ),
                        scan_date=datetime.now(timezone.utc),
                    )

                    try:
                        shadow_res = await asyncio.wait_for(
                            executor.execute_shadow(shadow_ctx),
                            timeout=_SHADOW_EXECUTOR_TIMEOUT_SECONDS,
                        )
                    except TimeoutError:
                        # Hardening M4: timeout must not fail production path.
                        shadow_logger.warning(
                            "Shadow mode hook timed out after %.1fs | symbol=%s | ruleset=%s. "
                            "Degrading gracefully.",
                            _SHADOW_EXECUTOR_TIMEOUT_SECONDS,
                            symbol,
                            settings.shadow_mode_ruleset,
                        )
                    else:
                        shadow_logger.info(
                            "Shadow execution succeeded | symbol=%s | ruleset=%s",
                            symbol,
                            shadow_res.ruleset_name,
                        )
            except Exception as shadow_exc:
                # Log full traceback for ops; never re-raise into production pipeline.
                shadow_logger.warning(
                    "Shadow mode hook failed with exception: %s | symbol=%s | ruleset=%s. "
                    "Degrading gracefully.",
                    shadow_exc,
                    symbol,
                    settings.shadow_mode_ruleset,
                    exc_info=True,
                )

            # FEAT-018 / FEAT-016: independent candidate submissions (audit H1/H3/H4).
            # Isolated from the experimental ruleset executor so a ruleset failure
            # cannot skip shadow candidate telemetry. Submitted AFTER history persist
            # so telemetry attaches to the current AnalysisHistory row.
            self._submit_shadow_candidate_features(
                symbol=symbol,
                stock_id=stock_id,
                articles=articles or [],
                bulk_technical_results=bulk_technical_results,
                sector_overlay=sector_overlay,
            )

        self.logger.info(
            "Completed symbol analysis | symbol=%s | recommendation=%s | confidence=%s | score=%s | challenger=%s | market_regime=%s",
            symbol,
            recommendation.action,
            recommendation.confidence,
            recommendation.score,
            challenger_recommendation.action,
            market_regime.market_state,
        )

        lab_engines = None
        if re001_decision is not None:
            try:
                lab_engines = {
                    "RE-001": re001_decision.model_dump(mode="json"),
                }
            except Exception:
                lab_engines = {
                    "RE-001": {
                        "engine_id": getattr(re001_decision, "engine_id", "RE-001"),
                        "recommendation_state": getattr(
                            re001_decision, "recommendation_state", None
                        ),
                        "confidence_score": getattr(
                            re001_decision, "confidence_score", None
                        ),
                        "strategy_name": getattr(re001_decision, "strategy_name", None),
                        "explanation": getattr(re001_decision, "explanation", None),
                        "production_action": getattr(
                            re001_decision, "production_action", None
                        ),
                        "reason_codes": getattr(re001_decision, "reason_codes", None),
                        "market_regime": getattr(re001_decision, "market_regime", None),
                        "recommendation_id": getattr(
                            re001_decision, "recommendation_id", None
                        ),
                        "engine_version": getattr(
                            re001_decision, "engine_version", None
                        ),
                    }
                }

        return StockAnalysisResult(
            symbol=symbol,
            ohlcv=self._primary_candle_set(candles_by_mode),
            technical=technical_results,
            news_articles=articles,
            news_summary=news_summary,
            news_sentiment_label=sentiment_label,
            news_sentiment_score=sentiment_score,
            fundamental=fundamental_result,
            backtests=backtests,
            recommendation=recommendation,
            challenger_recommendation=challenger_recommendation,
            sector_overlay=sector_overlay,
            market_regime=market_regime,
            disclaimer=advisory_payload(),
            data_source=self._data_source_label(candles_by_mode, request),
            data_quality=data_quality,
            trade_readiness=self._trade_readiness(recommendation, technical_results, data_quality),
            confidence_breakdown=self._confidence_breakdown(technical_score, sentiment_score, best_backtest, recommendation),
            lab_engines=lab_engines,
        )

    async def _persist_analysis(
        self,
        stock_id: int,
        mode: str,
        technical_score: float,
        sentiment_score: float,
        backtest: Any,
        recommendation: Any,
        sector_overlay: Any = None,
        market_regime: Any = None,
        symbol: str = None,
        articles: list[Any] = None,
    ) -> int | None:
        from ..db.session import AsyncSessionLocal
        from ..services.taxonomy_classifier import determine_situation_tags

        situation_tags = determine_situation_tags(
            symbol=symbol,
            recommendation=recommendation.action,
            sentiment_score=sentiment_score,
            articles=articles,
            market_regime=market_regime
        )

        reason_codes_value = sector_overlay.downgrade_reason if sector_overlay else None
        if reason_codes_value and len(reason_codes_value) > 450:
            reason_codes_value = reason_codes_value[:447] + "..."

        async with AsyncSessionLocal() as db:
            analysis_entry = AnalysisHistory(
                stock_id=stock_id,
                mode=mode,
                technical_score=technical_score,
                sentiment_score=sentiment_score,
                backtest_score=backtest.total_return,
                recommendation=recommendation.action,
                confidence=recommendation.confidence,
                reasoning=recommendation.summary,
                # SR-003 Audit fields
                mapped_sector=sector_overlay.mapped_sector if sector_overlay else None,
                sector_rs_20=sector_overlay.sector_rs_20 if sector_overlay else None,
                sector_close_vs_ema20=(sector_overlay.sector_close < sector_overlay.sector_ema20) if (sector_overlay and sector_overlay.sector_close is not None and sector_overlay.sector_ema20 is not None) else None,
                sector_filter_triggered=sector_overlay.downgrade_triggered if sector_overlay else None,
                original_signal=sector_overlay.original_action if sector_overlay else None,
                challenger_signal=sector_overlay.challenger_action if sector_overlay else None,
                reason_codes=reason_codes_value,
                # SR-004 Audit fields
                market_state=market_regime.market_state if market_regime else None,
                market_trend_state=market_regime.trend_state if market_regime else None,
                market_breadth_state=market_regime.breadth_state if market_regime else None,
                market_volatility_state=market_regime.volatility_state if market_regime else None,
                market_new_entry_allowed=market_regime.new_entry_allowed if market_regime else None,
                market_risk_multiplier=market_regime.risk_multiplier if market_regime else None,
                situation_tags=situation_tags,
            )
            db.add(analysis_entry)

            backtest_entry = BacktestHistory(
                stock_id=stock_id,
                mode=mode,
                strategy_name=backtest.strategy_name,
                total_return=backtest.total_return,
                cagr=backtest.cagr if backtest.cagr is not None else 0.0,
                max_drawdown=backtest.max_drawdown,
                win_rate=backtest.win_rate,
                profit_factor=backtest.profit_factor,
                trade_count=backtest.trade_count,
                verdict=backtest.verdict,
                gross_total_return=getattr(backtest, "gross_total_return", None),
                gross_cagr=getattr(backtest, "gross_cagr", None),
                gross_max_drawdown=getattr(backtest, "gross_max_drawdown", None),
                gross_win_rate=getattr(backtest, "gross_win_rate", None),
                gross_profit_factor=getattr(backtest, "gross_profit_factor", None),
                gross_sharpe_ratio=getattr(backtest, "gross_sharpe_ratio", None),
                cost_scenario=getattr(backtest, "cost_scenario", None),
                total_transaction_costs=getattr(backtest, "total_transaction_costs", None),
                total_slippage=getattr(backtest, "total_slippage", None),
                position_sizing_pct=getattr(backtest, "position_sizing_pct", None),
            )
            db.add(backtest_entry)
            await db.commit()
            await db.refresh(analysis_entry)
            return int(analysis_entry.id) if analysis_entry.id is not None else None

    async def _get_or_create_stock(self, symbol: str) -> int:
        from ..db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            existing = (await db.scalars(select(WatchedStock).where(WatchedStock.symbol == symbol))).first()
            if existing:
                return existing.id

            stock = WatchedStock(symbol=symbol, display_name=symbol.replace("-EQ", ""))
            db.add(stock)
            try:
                await db.commit()
                return stock.id
            except IntegrityError:
                await db.rollback()
                existing = (await db.scalars(select(WatchedStock).where(WatchedStock.symbol == symbol))).first()
                return existing.id

    def _resolve_modes(self, mode: AnalysisMode) -> list[AnalysisMode]:
        if mode in (AnalysisMode.both, AnalysisMode.intraday):
            return [AnalysisMode.swing]
        return [mode]

    def _resolution_for_mode(self, mode: AnalysisMode, request: AnalysisRequest) -> str:
        if mode == AnalysisMode.intraday:
            return request.timeframe.intraday
        return request.timeframe.swing

    def _primary_candle_set(self, candles_by_mode: dict[AnalysisMode, list]) -> list:
        if not candles_by_mode:
            return []
        return candles_by_mode.get(AnalysisMode.swing) or next(iter(candles_by_mode.values()), [])

    @staticmethod
    def _universe_breadth_items_from_bulk(
        bulk_technical_results: dict[AnalysisMode, dict[str, TechnicalAnalysisResult]] | None,
    ) -> list[dict[str, Any]]:
        """Build universe-level (price, sma_200) rows from bulk technical results (FR-004).

        Prefers swing-mode results when present; otherwise uses the first available mode.
        """
        if not bulk_technical_results:
            return []

        mode_map: dict[str, TechnicalAnalysisResult] | None = None
        if AnalysisMode.swing in bulk_technical_results:
            mode_map = bulk_technical_results[AnalysisMode.swing]
        else:
            mode_map = next(iter(bulk_technical_results.values()), None)

        if not mode_map:
            return []

        items: list[dict[str, Any]] = []
        for sym, tech in mode_map.items():
            inds = getattr(tech, "indicators", None) or {}
            items.append(
                {
                    "symbol": sym,
                    "current_price": inds.get("close") or inds.get("current_price"),
                    "sma_200": inds.get("sma_200") or inds.get("sma200"),
                }
            )
        return items

    def _submit_shadow_candidate_features(
        self,
        *,
        symbol: str,
        stock_id: int | None,
        articles: list[Any],
        bulk_technical_results: dict[AnalysisMode, dict[str, TechnicalAnalysisResult]] | None,
        sector_overlay: Any = None,
    ) -> None:
        """Submit FEAT-018 / FEAT-016 / FEAT-020 after AnalysisHistory persist.

        Each feature is isolated in its own try/except so one failure cannot block
        the other or the production path.
        """
        try:
            from ..services.shadow_executor import (
                ShadowThreadPool,
                execute_shadow_market_breadth,
                execute_shadow_sentiment_decay,
                execute_shadow_sector_strength,
            )
        except Exception as import_exc:
            shadow_logger.warning(
                "Shadow candidate import failed | symbol=%s | error=%s",
                symbol,
                import_exc,
            )
            return

        # FEAT-018: Sentiment Time-Decay — independent of news_dedup lifecycle (H1),
        # post-persist so history exists (H3). Empty article lists are allowed.
        try:
            ShadowThreadPool.submit_task(
                execute_shadow_sentiment_decay,
                symbol,
                list(articles or []),
                None,
                stock_id,
            )
        except Exception as sent_exc:
            shadow_logger.warning(
                "Shadow sentiment_decay submit failed | symbol=%s | error=%s",
                symbol,
                sent_exc,
            )

        # FEAT-016: Market Breadth — full bulk universe (C1), isolated from ruleset executor (H4).
        try:
            breadth_items = self._universe_breadth_items_from_bulk(bulk_technical_results)
            ShadowThreadPool.submit_task(
                execute_shadow_market_breadth,
                symbol,
                breadth_items,
                None,
                stock_id,
            )
        except Exception as breadth_exc:
            shadow_logger.warning(
                "Shadow market_breadth submit failed | symbol=%s | error=%s",
                symbol,
                breadth_exc,
            )

        # FEAT-020: Sector Strength — watch-only relative sector return calculation.
        # Build real sector/benchmark inputs from bulk technicals + sector overlay ROC.
        try:
            from ..services.sector_strength import build_sector_strength_scan_inputs

            universe_map: dict[str, TechnicalAnalysisResult] | None = None
            if bulk_technical_results:
                if AnalysisMode.swing in bulk_technical_results:
                    universe_map = bulk_technical_results[AnalysisMode.swing]
                else:
                    universe_map = next(iter(bulk_technical_results.values()), None)

            sectors, benchmark_symbol, benchmark_return_pct = build_sector_strength_scan_inputs(
                universe_technical=universe_map,
                sector_overlay=sector_overlay,
            )
            if benchmark_return_pct is None and not sectors:
                shadow_logger.warning(
                    "Shadow sector_strength missing benchmark/sector data | symbol=%s | "
                    "persisting neutral empty telemetry",
                    symbol,
                )
            ShadowThreadPool.submit_task(
                execute_shadow_sector_strength,
                symbol,
                sectors or None,
                benchmark_symbol,
                benchmark_return_pct,
                None,
                stock_id,
            )
        except Exception as sector_exc:
            shadow_logger.warning(
                "Shadow sector_strength submit failed | symbol=%s | error=%s",
                symbol,
                sector_exc,
            )

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
        if AnalysisMode.swing in candles_by_mode:
            primary_mode = AnalysisMode.swing
        elif candles_by_mode:
            primary_mode = next(iter(candles_by_mode.keys()))
        else:
            primary_mode = AnalysisMode.swing

        primary_source = (
            self.fyers_service.get_ohlcv_source(
                symbol,
                primary_mode,
                self._resolution_for_mode(primary_mode, request),
            )
            if candles_by_mode
            else "NONE"
        )
        # Prefetched shortlist candles may not have registered a source key yet.
        # When we have a full OHLC series, treat data as real (not mock).
        if primary_source in {"unknown", "NONE"} and len(primary) >= 220:
            primary_source = "CANDLE_CACHE_DB"
        latest_timestamp = primary[-1].timestamp.isoformat() if primary else "n/a"
        # Explicitly untrusted / empty sources only — do NOT treat warm-cache or
        # prefetched series as mock just because the label was missing.
        _EXPLICIT_MOCK = {"MOCK_FALLBACK", "NO_DATA", "NONE"}
        mock_warning = primary_source in _EXPLICIT_MOCK or len(primary) == 0
        return {
            "source": primary_source,
            "candles": len(primary),
            "candles_fetched": len(primary),
            "latest_timestamp": latest_timestamp,
            "mock_warning": mock_warning,
            "minimum_swing_candles_met": len(primary) >= 220,
        }

    @staticmethod
    def _resolve_composite_backtests(
        backtests: list,
        use_realistic_for_composite: bool,
    ) -> list:
        """Return the appropriate backtest list for recommendation composite.

        When use_realistic_for_composite is True the composite should consume
        the realistic (Pass 2) return, so the originals are passed through
        unchanged.

        When use_realistic_for_composite is False the composite must consume
        the legacy (Pass 1) return.  Non-destructive shadow copies are
        created where total_return is swapped to gross_total_return.
        The originals are never modified and remain available for
        persistence, gate evaluation, and all other consumers.

        Used by both the primary orchestrator path
        (_analyze_symbol_post_bulk) and the fallback path
        (_unavailable_analysis_result).
        """
        if use_realistic_for_composite:
            return backtests
        return [
            bt.model_copy(update={'total_return': bt.gross_total_return or bt.total_return})
            for bt in backtests
        ]

    def _unavailable_analysis_result(
        self,
        symbol: str,
        request: AnalysisRequest,
        candles_by_mode: dict[AnalysisMode, list],
    ) -> StockAnalysisResult:
        technical_results = []
        backtests = []
        if not settings.feat008_enabled:
            exec_model = "LEGACY"
            use_realistic_for_composite = False
            skip_on_missing_next_bar = False
        else:
            exec_model = settings.feat008_execution_model
            use_realistic_for_composite = settings.feat008_composite_uses_realistic
            skip_on_missing_next_bar = settings.feat008_skip_on_missing_next_bar
        for mode in self._resolve_modes(request.mode):
            # TechnicalAnalysisService only exposes analyze_bulk (no single-symbol analyze).
            tech_res = None
            if candles_by_mode.get(mode):
                bulk = self.technical_agent.service.analyze_bulk(
                    {symbol: candles_by_mode[mode]}, mode
                )
                tech_res = bulk.get(symbol)
            technical_results.append(tech_res or self._empty_technical_result(mode))
            backtests.append(self.backtest_agent.run(
                symbol, mode, candles_by_mode.get(mode, []),
                execution_model=exec_model,
                composite_uses_realistic=use_realistic_for_composite,
                skip_on_missing_next_bar=skip_on_missing_next_bar,
                feat008_enabled=settings.feat008_enabled,
            ))

        composite_backtests = self._resolve_composite_backtests(
            backtests, use_realistic_for_composite
        )

        data_quality = self._data_quality_payload(candles_by_mode, request, symbol)

        # FEAT-004: pass config even on the fallback path for consistent metadata
        feat004_config = self._build_feat004_config()
        # FEAT-007: pass config for consistent metadata; sector_rs_value=None (no data)
        feat007_config = self._build_feat007_config()

        recommendation = self.recommendation_agent.recommendation_service.build(
            symbol=symbol,
            technical_results=technical_results,
            sentiment_score=0.0,
            fundamental_result=None,
            backtests=composite_backtests,
            candles_by_mode=candles_by_mode,
            llm_reasoning={
                "bullets": ["Live OHLCV data was unavailable for this symbol, so the recommendation engine could not evaluate the setup."],
                "risk_factors": ["No live market data was returned from the configured providers."],
                "invalidation_signals": ["Wait for the backend to return fresh live candles before reviewing this symbol."],
                "summary": f"{symbol} could not be analyzed because no live market data was available.",
            },
            feat004_config=feat004_config,
            benchmark_ohlcv=None,
            sector_mapping=None,
            sector_ohlcv_cache=None,
            feat007_config=feat007_config,
            sector_rs_value=None,
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
            challenger_recommendation=recommendation,
            sector_overlay=None,
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
        """Final recommendation gate — runs ONLY after full analysis pipeline.

        All technical, AI, sector, backtest, and trade-plan work is already done
        by the time this method is called. This gate does NOT re-run analysis.

        Production signal policy (score-based only):
          score >= 70 → BUY
          55 <= score < 70 → WATCH
          score < 55 → REJECT

        Informational only (never override the score decision):
          Risk:Reward, conviction, AI confidence threshold, trend strength,
          market regime, breakout confirmation, feature flags, safety overrides.

        Mandatory preconditions (any failure → REJECT, reason=Analysis Failed):
          market data, valid price/OHLC, trade plan with entry/SL/target,
          score calculated, confidence calculated, analysis completed.
        """
        from ..services.recommendation_service import (
            ANALYSIS_FAILED_REASON,
            analysis_preconditions_ok,
            classify_signal_from_score,
        )

        composite_score = float(getattr(recommendation, "score", 0.0) or 0.0)
        confidence = getattr(recommendation, "confidence", None)
        primary_plan = recommendation.trade_plans[0] if recommendation.trade_plans else None
        best_technical = max(technical_results, key=lambda item: item.score) if technical_results else None
        best_backtest = max(backtests, key=lambda item: item.total_return) if backtests else None
        _ = best_backtest  # retained for diagnostics only

        try:
            self.logger.info(
                "SCORE SIGNAL POLICY | symbol=%s | score=%.2f | conf=%s | plans=%s | source=%s | mock_warning=%s | min_candles_met=%s | tech=%.2f | rr=%s",
                symbol,
                composite_score,
                confidence,
                len(recommendation.trade_plans or []),
                data_quality.get("source"),
                data_quality.get("mock_warning"),
                data_quality.get("minimum_swing_candles_met"),
                float(best_technical.score) if best_technical is not None else 0.0,
                (
                    primary_plan.risk_reward_ratio
                    if primary_plan is not None and getattr(primary_plan, "risk_reward_ratio", None) is not None
                    else None
                ),
            )
        except Exception:
            pass

        # Analysis-completed check: technical results present for the symbol path
        analysis_completed = bool(technical_results) and best_technical is not None

        ok, reason = analysis_preconditions_ok(
            score=composite_score,
            confidence=confidence,
            trade_plans=recommendation.trade_plans,
            data_quality=data_quality,
        )
        if not analysis_completed:
            ok = False
            reason = ANALYSIS_FAILED_REASON

        if not ok:
            updated_risks = list(recommendation.reasoning.risk_factors)
            if ANALYSIS_FAILED_REASON not in updated_risks:
                updated_risks.append(ANALYSIS_FAILED_REASON)
            self.logger.info(
                "SCORE SIGNAL REJECT | symbol=%s | reason=%s | prior_score=%.2f | source=%s | plans=%s",
                symbol,
                reason or ANALYSIS_FAILED_REASON,
                composite_score,
                data_quality.get("source"),
                len(recommendation.trade_plans or []),
            )
            # True analysis failure: never invent a high score. Clear score /
            # confidence / trade plans so the UI shows N/A rather than Score=100
            # or leftover fields from a partial path.
            return recommendation.model_copy(
                update={
                    "action": "REJECT",
                    "score": 0.0,
                    "confidence": 0.0,
                    "trade_plans": [],
                    "reasoning": recommendation.reasoning.model_copy(update={"risk_factors": updated_risks}),
                    "summary": (
                        f"{recommendation.summary} Signal=REJECT ({ANALYSIS_FAILED_REASON}). "
                        "Score/Entry/SL/Target are unavailable because analysis did not complete."
                    ),
                }
            )

        # Pure score classification — no R:R / tech / regime overrides.
        score_action = classify_signal_from_score(composite_score)
        if recommendation.action != score_action:
            self.logger.info(
                "SCORE SIGNAL RECLASSIFY | symbol=%s | from=%s | to=%s | score=%.2f",
                symbol,
                recommendation.action,
                score_action,
                composite_score,
            )
            return recommendation.model_copy(update={"action": score_action})

        self.logger.info(
            "SCORE SIGNAL PASS | symbol=%s | action=%s | score=%.2f",
            symbol,
            score_action,
            composite_score,
        )
        return recommendation

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
