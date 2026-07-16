from __future__ import annotations

import asyncio
from statistics import mean
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import threading
import time
import re
import yfinance as yf
import pandas as pd

try:
    import psutil
except ImportError:
    psutil = None

def get_rss_mb():
    if psutil is None:
        return 0.0
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)

from ..schemas import AnalysisMode, OHLCVPoint, ScreenerConditionResult
from ..utils import get_logger
from .fyers_service import FyersService, FyersRateLimitError, FyersAuthExpiredError, FyersAuthInvalidError
from .technical_analysis_service import TechnicalAnalysisService
from ..core.log_manager import scanner_logger
from datetime import datetime, timezone
from . import candle_store
from ..observability.scan_diagnostics import (
    get_current_scan, log_symbol_failure, log_data_source_selection,
    log_pipeline_stage,
)

MINIMUM_SWING_CANDLES = 220


class AsyncTokenBucketRateLimiter:
    def __init__(self, calls_per_second: float = 5.0):
        self.capacity = calls_per_second
        self.tokens = float(calls_per_second)
        self.last_refill = time.monotonic()
        self._lock: asyncio.Lock | None = None
        self._wait_interval = 1.0 / calls_per_second

    async def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self):
        while True:
            lock = await self._get_lock()
            async with lock:
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(
                    self.capacity,
                    self.tokens + elapsed * self.capacity,
                )
                self.last_refill = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
            await asyncio.sleep(self._wait_interval)

_rate_limiter = AsyncTokenBucketRateLimiter(calls_per_second=5.0)

scanner_metrics = {
    "valid_symbols": 0,
    "incomplete_history": 0,
    "forced_rebuilds": 0,
    "invalid_symbols": 0,
    "continuity_failures": 0,
    "successful_backfills": 0
}

class ScreenerService:
    # Stores the last fetched OHLCV DataFrames keyed by symbol for reuse by orchestrator
    last_fetched_frames: dict[str, pd.DataFrame] = {}

    def __init__(self, fyers_service=None):
        self.fyers_service = fyers_service or FyersService()
        self.technical_service = TechnicalAnalysisService()
        self.logger = get_logger("app.screener")
        
    def get_metrics(self) -> dict:
        return scanner_metrics
        
    async def validate_startup_health(self, universe: list[str]) -> None:
        try:
            from .market_data_service import MarketDataService
            md_svc = MarketDataService()
            req = self.technical_service.get_required_candle_count(AnalysisMode.swing)
            incomplete = 0
            
            # Sample up to 50 symbols for quick startup check
            sample = universe[:50]
            for sym in sample:
                cnt = await md_svc.get_candle_count(sym, '1D')
                if cnt < req:
                    incomplete += 1
                    
            if incomplete > (len(sample) * 0.2):  # 20% incomplete threshold
                self.logger.warning("STARTUP WARNING: Scanner universe largely incomplete. %s/%s sampled symbols have < %s candles. Expected backfill storms.", incomplete, len(sample), req)
            else:
                self.logger.info("STARTUP: Scanner cache health looks good. Insufficient history sampled: %s/%s", incomplete, len(sample))
        except Exception:
            self.logger.exception("Failed to run scanner startup validation")

    async def _process_single_symbol(self, symbol: str, lookback_window: int, stage_name: str, candles: list[OHLCVPoint], technical, total_candle_count: int | None = None) -> ScreenerConditionResult:
        """Process a single symbol and return a ScreenerConditionResult.
        This contains the original symbol-level logic extracted from the
        sequential loop. Do NOT change the internal logic here when
        parallelizing the outer loop.
        """
        # total_candle_count: the real DB row count (may differ from len(candles) when tail-only)
        if total_candle_count is None:
            total_candle_count = len(candles)
        # Begin symbol scanning (debug-level: 755× INFO logs were a major I/O tax)
        self.logger.debug("STEP 1/8 | Begin symbol screening | stage=%s | symbol=%s", stage_name, symbol)
        if candles is None:
            candles = await self.fyers_service.get_candles_cached(
                symbol=symbol,
                mode=AnalysisMode.swing,
                resolution="1d",
                lookback_window=max(lookback_window, 240),
                allow_mock=False,
            )
        candle_source = self.fyers_service.get_ohlcv_source(symbol, AnalysisMode.swing, "1d")
        if not candle_source or candle_source == "unknown":
            candle_source = "CANDLE_CACHE_DB"
        minimum_swing_candles_met = total_candle_count >= MINIMUM_SWING_CANDLES
        self.logger.debug(
            "CANDLE CHECK | symbol=%s | candles=%s | minimum_required=%s | met=%s",
            symbol,
            total_candle_count,
            MINIMUM_SWING_CANDLES,
            minimum_swing_candles_met,
        )
        # scan-log: only on failures / data issues (not every symbol)

        # Validate data quality
        self.logger.debug("STEP 2/8 | Stage=%s | Validate data quality | symbol=%s", stage_name, symbol)
        if candle_source in {"MOCK_FALLBACK", "NO_DATA"}:
            self.logger.info(
                "STEP 2/8 | Rejected non-live symbol | symbol=%s | source=%s | candles=%s | allow_mock=%s",
                symbol,
                candle_source,
                len(candles),
                False,
            )
            if self._scan_log is not None:
                self._scan_log.info("SKIP datasource_failed | symbol=%s | source=%s", symbol, candle_source)
            return ScreenerConditionResult(
                symbol=symbol,
                close=0.0,
                ema_20=0.0,
                ema_50=0.0,
                ema50_available=False,
                ema20_above_ema50=False,
                sma_30=0.0,
                sma_50=0.0,
                sma_100=0.0,
                sma_200=0.0,
                macd=0.0,
                macd_signal=0.0,
                supertrend=0.0,
                volume=0,
                previous_volume=0,
                screener_score=0.0,
                technical_signal="unknown",
                technical_score=0.0,
                candles_fetched=0,
                conditions={"data_source_failed": True},
                matched=False,
            )

        if not self._passes_data_quality(candles, total_candle_count=total_candle_count):
            latest = candles[-1] if candles else None
            self.logger.info(
                "STEP 2/8 | Data quality failed | symbol=%s | source=%s | candles=%s | latest_close=%s | latest_volume=%s",
                symbol,
                candle_source,
                len(candles),
                latest.close if latest else "n/a",
                latest.volume if latest else "n/a",
            )
            if self._scan_log is not None:
                self._scan_log.info("SKIP data_quality_failed | symbol=%s | candles=%s", symbol, len(candles))
                try:
                    self._scan_log.info(
                        "SCAN_ENTRY | symbol=%s | score=0.0 | signal=unknown | confidence=0.0 | timestamp=%s",
                        symbol,
                        datetime.now(timezone.utc).isoformat(),
                    )
                except Exception:
                    pass
            return ScreenerConditionResult(
                symbol=symbol,
                close=latest.close if latest else 0.0,
                ema_20=0.0,
                ema_50=0.0,
                ema50_available=False,
                ema20_above_ema50=False,
                sma_30=0.0,
                sma_50=0.0,
                sma_100=0.0,
                sma_200=0.0,
                macd=0.0,
                macd_signal=0.0,
                supertrend=0.0,
                volume=latest.volume if latest else 0,
                previous_volume=0,
                screener_score=0.0,
                technical_signal="unknown",
                technical_score=0.0,
                candles_fetched=total_candle_count,
                conditions={"data_quality_failed": True},
                matched=False,
            )
        indicators = technical.indicators
        latest = candles[-1]
        previous = candles[-2]

        # Apply broad trend eligibility (no per-symbol INFO — aggregate summary is logged once)
        broad_eligibility = self._passes_broad_trend(candles, technical)

        # Compute weighted screener score
        conditions = self._build_conditions(indicators, latest, previous, broad_eligibility, technical)
        screener_score = self._weighted_score(candles, technical, conditions)
        matched = broad_eligibility and screener_score >= 52

        result = ScreenerConditionResult(
            symbol=symbol,
            close=round(latest.close, 2),
            ema_20=float(indicators.get("ema_20", 0.0)),
            ema_50=float(indicators.get("ema_50", 0.0)),
            ema50_available=bool(indicators.get("ema50_available", False)),
            ema20_above_ema50=bool(indicators.get("ema20_above_ema50", False)),
            sma_30=float(indicators.get("sma_30", 0.0)),
            sma_50=float(indicators.get("sma_50", 0.0)),
            sma_100=float(indicators.get("sma_100", 0.0)),
            sma_200=float(indicators.get("sma_200", 0.0)),
            macd=float(indicators.get("macd", 0.0)),
            macd_signal=float(indicators.get("macd_signal", 0.0)),
            supertrend=float(indicators.get("supertrend", 0.0)),
            volume=latest.volume,
            previous_volume=previous.volume,
            screener_score=screener_score,
            technical_signal=technical.signal,
            technical_score=technical.score,
            candles_fetched=total_candle_count,
            conditions=conditions,
            matched=matched,
        )
        self._log_determinism_debug(
            {
                "event": "symbol_scored",
                "symbol": symbol,
                "provider": candle_source,
                "latest_candle_timestamp": latest.timestamp.isoformat(),
                "candle_count": len(candles),
                "screener_score": result.screener_score,
                "data_origin": "cache" if candle_source == "CANDLE_CACHE_DB" else "fyers",
            }
        )

        # scan log: only shortlisted PASS (avoid 700+ FAIL lines per run)
        if self._scan_log is not None and result.matched:
            self._scan_log.info(
                "PASS shortlisted | symbol=%s | screener_score=%.1f | technical_score=%.1f | signal=%s",
                symbol,
                result.screener_score,
                result.technical_score,
                result.technical_signal,
            )
            try:
                self._scan_log.info(
                    "SCAN_ENTRY | symbol=%s | score=%.1f | signal=%s | confidence=%.2f | timestamp=%s",
                    symbol,
                    result.screener_score,
                    result.technical_signal,
                    result.technical_score or 0.0,
                    datetime.now(timezone.utc).isoformat(),
                )
            except Exception:
                pass

        return result

    async def fallback_fetch_yfinance(self, symbol: str) -> list[OHLCVPoint]:
        # Symbol Translation: FYERS format is NSE:HDFCBANK-EQ
        # Yahoo Finance expects HDFCBANK.NS
        yf_symbol = symbol.replace("NSE:", "").replace("-EQ", "").strip() + ".NS"
        
        df = await asyncio.to_thread(yf.download, yf_symbol, period="1y", interval="1d", progress=False)
        if df is None or df.empty:
            return []
            
        points = []
        for index, row in df.iterrows():
            # If the columns are MultiIndex (newer yfinance), we might need to handle it.
            # Usually for single ticker it's just 'Open', 'High', 'Low', 'Close', 'Volume'
            open_val = row['Open'] if 'Open' in df.columns else row.iloc[0]
            high_val = row['High'] if 'High' in df.columns else row.iloc[1]
            low_val = row['Low'] if 'Low' in df.columns else row.iloc[2]
            close_val = row['Close'] if 'Close' in df.columns else row.iloc[3]
            vol_val = row['Volume'] if 'Volume' in df.columns else row.iloc[4]
            
            # Extract scalar values from Series if necessary (yfinance 0.2.x+ can return Series in iterrows)
            if isinstance(open_val, pd.Series):
                open_val = open_val.iloc[0]
                high_val = high_val.iloc[0]
                low_val = low_val.iloc[0]
                close_val = close_val.iloc[0]
                vol_val = vol_val.iloc[0]
                
            dt = index
            if hasattr(dt, "to_pydatetime"):
                dt = dt.to_pydatetime()
                
            # Naive UTC or timezone-aware mapping matching our schema (tz-naive in DB usually)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)

            points.append(OHLCVPoint(
                timestamp=dt,
                open=float(open_val),
                high=float(high_val),
                low=float(low_val),
                close=float(close_val),
                volume=int(vol_val)
            ))
            
        return points

    async def screen_symbols_swing(
        self,
        symbols: list[str],
        lookback_window: int,
        stage_name: str = "Unknown",
        progress_callback=None,
    ) -> list[ScreenerConditionResult]:
        results: list[ScreenerConditionResult] = []
        total_requested = len(symbols)
        stage_timings: dict[str, float] = {}

        # use centralized scanner logger (rotating file handler)
        scan_log = scanner_logger
        # make scan_log available to worker threads
        self._scan_log = scan_log

        def _progress(data, percent=None) -> None:
            if progress_callback:
                try:
                    if isinstance(data, str):
                        progress_callback({"stage": data, "progress": percent or 0})
                    elif isinstance(data, dict):
                        progress_callback(data)
                except Exception:
                    pass

        scan_log.info("%s", "=" * 60)
        scan_log.info(
            "SCAN START | symbols=%s | lookback=%s | stage=%s",
            total_requested,
            lookback_window,
            stage_name,
        )
        scan_log.info("%s", "=" * 60)

        self.logger.info(
            "STEP 1/8 | Stage=%s | Fetch real OHLCV for configured swing universe | symbols=%s | lookback=%s",
            stage_name,
            total_requested,
            lookback_window,
        )

        scan_start_time = time.perf_counter()
        self.logger.info("SCANNER_RUN_STARTED | stage=%s | symbols=%s", stage_name, total_requested)

        self.logger.debug("MEMORY_AUDIT stage=scanner_start rss_mb=%.1f", get_rss_mb())

        from .market_data_service import MarketDataService
        from ..config import settings as app_settings
        md_service = MarketDataService()

        # Phase 3: Use DataFrames as canonical representation instead of OHLCVPoint lists
        # This eliminates precombined_datasets (238 MB) and candles_dict (228 MB)
        symbol_frames: dict[str, pd.DataFrame] = {}

        async def fetch_all_symbols():
            """
            High-throughput cache-first acquisition:

            1) Batch meta + stored-symbol map (handles NSE:/-EQ drift)
            2) Bulk-load ALL symbols that already have DB history
            3) Worker-pool FYERS calls ONLY for missing/stale symbols (true incremental)
            4) Batch upsert deltas + one bulk reload for API symbols
            """
            required_history = self.technical_service.get_required_candle_count(AnalysisMode.swing)
            max_workers = max(1, min(int(getattr(app_settings, "max_concurrent_requests", 25) or 25), 50))
            phase_t0 = time.perf_counter()
            _progress(f"Fetching Historical OHLCV Data... (meta {total_requested})", 40)

            meta_t0 = time.perf_counter()
            meta = await md_service.get_candle_meta_batch(symbols, "1D")
            stored_map = await md_service.resolve_stored_symbol_map(symbols, "1D", meta_result=meta)
            stage_timings["meta_ms"] = (time.perf_counter() - meta_t0) * 1000

            _progress({
                "stage": f"Loading candle cache from DB... ({len(symbols)} symbols)",
                "progress": 10,
                "current_symbol": "",
                "done": 0,
                "remaining": len(symbols),
                "eta_sec": 0,
            })

            # Partition: ready (fresh complete) vs needs API
            cache_hit_symbols: list[str] = []
            needs_fetch: list[str] = []
            for symbol in symbols:
                count, latest, _ = meta.get(symbol, (0, None, None))
                if MarketDataService.is_daily_cache_fresh_enough(count, latest, required_history):
                    cache_hit_symbols.append(symbol)
                else:
                    if count < required_history:
                        scanner_metrics["incomplete_history"] += 1
                        scanner_metrics["forced_rebuilds"] += 1
                    needs_fetch.append(symbol)

            self.logger.info(
                "SCANNER_CACHE_PARTITION | stage=%s | total=%s | cache_hits=%s | needs_fetch=%s | workers=%s | meta_ms=%.0f",
                stage_name,
                len(symbols),
                len(cache_hit_symbols),
                len(needs_fetch),
                max_workers,
                stage_timings["meta_ms"],
            )
            scan_log.info(
                "CACHE PARTITION | stage=%s | cache_hits=%s | needs_fetch=%s | workers=%s",
                stage_name,
                len(cache_hit_symbols),
                len(needs_fetch),
                max_workers,
            )

            # --- Fast path: bulk load complete/fresh histories from DB ---
            # Also pre-load any partial history for needs_fetch so incremental merge is local.
            preload_symbols = list(dict.fromkeys(cache_hit_symbols + [s for s in needs_fetch if meta.get(s, (0, None))[0] > 0]))
            if preload_symbols:
                load_t0 = time.perf_counter()
                _progress(f"Loading candle cache from DB... ({len(preload_symbols)} symbols)", 42)
                loaded = await md_service.load_histories_batch(
                    preload_symbols, "1D", stored_symbol_map=stored_map
                )
                demoted = 0
                for symbol in cache_hit_symbols:
                    df = loaded.get(symbol)
                    if df is None or df.empty or len(df) < required_history:
                        demoted += 1
                        if symbol not in needs_fetch:
                            needs_fetch.append(symbol)
                        continue
                    symbol_frames[symbol] = df
                # Keep partial frames for later merge (not yet complete)
                for symbol in needs_fetch:
                    if symbol in symbol_frames:
                        continue
                    df = loaded.get(symbol)
                    if df is not None and not df.empty:
                        symbol_frames[symbol] = df  # may be short; may be refreshed after API
                stage_timings["cache_bulk_load_ms"] = (time.perf_counter() - load_t0) * 1000
                self.logger.info(
                    "SCANNER_CACHE_BULK_LOAD | stage=%s | requested=%s | ready=%s | demoted_to_fetch=%s | load_ms=%.0f",
                    stage_name,
                    len(preload_symbols),
                    sum(1 for s in cache_hit_symbols if s in symbol_frames and len(symbol_frames[s]) >= required_history),
                    demoted,
                    stage_timings["cache_bulk_load_ms"],
                )

            # De-dupe needs_fetch; drop symbols that became ready after bulk load
            seen_fetch: set[str] = set()
            ordered_fetch: list[str] = []
            for symbol in needs_fetch:
                if symbol in seen_fetch:
                    continue
                df = symbol_frames.get(symbol)
                count, latest, _ = meta.get(symbol, (0, None, None))
                if (
                    df is not None
                    and not df.empty
                    and len(df) >= required_history
                    and MarketDataService.is_daily_cache_fresh_enough(len(df), latest, required_history)
                ):
                    continue
                seen_fetch.add(symbol)
                ordered_fetch.append(symbol)
            needs_fetch = ordered_fetch

            # --- Worker pool: FYERS only for incomplete/stale symbols ---
            fyers_sem = asyncio.Semaphore(max_workers)
            loop = asyncio.get_running_loop()
            done_counter = {"n": 0}
            progress_lock = asyncio.Lock()
            frames_lock = asyncio.Lock()
            last_progress_t = {"t": time.perf_counter()}
            pending_upserts: list[tuple[str, str, pd.DataFrame]] = []
            upsert_lock = asyncio.Lock()

            async def process_symbol_fyers(symbol: str, worker_id: int):
                async with fyers_sem:
                    t0 = time.perf_counter()
                    try:
                        # Acquire rate limiter token to avoid FYERS 429 responses
                        await _rate_limiter.acquire()
                        count, latest_timestamp, _ = meta.get(symbol, (0, None, None))
                        async with frames_lock:
                            existing = symbol_frames.get(symbol)
                            if existing is not None and not existing.empty:
                                existing = existing.copy()
                        dummy_cache: list[OHLCVPoint] = []
                        if existing is not None and not existing.empty:
                            last_ts = existing.index.max()
                            if hasattr(last_ts, "to_pydatetime"):
                                last_ts = last_ts.to_pydatetime()
                            if getattr(last_ts, "tzinfo", None) is not None:
                                last_ts = last_ts.replace(tzinfo=None)
                            dummy_cache.append(
                                OHLCVPoint(timestamp=last_ts, open=0, high=0, low=0, close=0, volume=0)
                            )
                        elif latest_timestamp is not None and count > 0:
                            dummy_cache.append(
                                OHLCVPoint(
                                    timestamp=latest_timestamp,
                                    open=0,
                                    high=0,
                                    low=0,
                                    close=0,
                                    volume=0,
                                )
                            )

                        new_candles = await loop.run_in_executor(
                            self.fyers_service._network_pool,
                            lambda s=symbol, c=dummy_cache: self.fyers_service.fetch_incremental_ohlcv(s, c),
                        )

                        if not dummy_cache and new_candles:
                            scanner_metrics["successful_backfills"] += 1

                        if new_candles:
                            df_delta = pd.DataFrame(
                                [
                                    {
                                        "open": c.open,
                                        "high": c.high,
                                        "low": c.low,
                                        "close": c.close,
                                        "volume": c.volume,
                                    }
                                    for c in new_candles
                                ],
                                index=[c.timestamp for c in new_candles],
                            )
                            if existing is not None and not existing.empty:
                                merged = existing.copy()
                                for ts, row in df_delta.iterrows():
                                    merged.loc[ts, ["open", "high", "low", "close", "volume"]] = [
                                        row["open"],
                                        row["high"],
                                        row["low"],
                                        row["close"],
                                        row["volume"],
                                    ]
                                merged = merged[~merged.index.duplicated(keep="last")].sort_index()
                                async with frames_lock:
                                    symbol_frames[symbol] = merged
                            else:
                                async with frames_lock:
                                    symbol_frames[symbol] = df_delta.sort_index()
                            async with upsert_lock:
                                pending_upserts.append((symbol, "1D", df_delta))

                        latency_ms = int((time.perf_counter() - t0) * 1000)
                        self.logger.debug(
                            "WORKER_FETCH | worker=%s | symbol=%s | new_candles=%s | latency_ms=%s | queue_remaining~=%s",
                            worker_id,
                            symbol,
                            len(new_candles) if new_candles else 0,
                            latency_ms,
                            max(0, len(needs_fetch) - done_counter["n"] - 1),
                        )
                        return symbol, True
                    except Exception as e:
                        self.logger.exception("Scanner processing failed", extra={"symbol": symbol})
                        scanner_metrics["invalid_symbols"] += 1
                        scan_ctx = get_current_scan()
                        if scan_ctx:
                            log_symbol_failure(scan_ctx, symbol=symbol, stage="data_acquisition", exc=e)
                        return symbol, False
                    finally:
                        async with progress_lock:
                            done_counter["n"] += 1
                            now = time.perf_counter()
                            if done_counter["n"] % 10 == 0 or (now - last_progress_t["t"]) >= 2.0:
                                last_progress_t["t"] = now
                                total = len(needs_fetch)
                                done = done_counter["n"]
                                remaining = total - done
                                pct = 40 + int(15 * done / max(1, total))
                                elapsed = now - phase_t0
                                eta_sec = int((elapsed / max(1, done)) * remaining) if done > 0 else 0
                                _progress(
                                    {
                                        "stage": f"Fetching Historical OHLCV Data... ({done}/{total})",
                                        "progress": min(pct, 54),
                                        "current_symbol": symbol,
                                        "worker_id": worker_id,
                                        "done": done,
                                        "remaining": remaining,
                                        "total_fetch": total,
                                        "eta_sec": eta_sec,
                                    },
                                )

            if needs_fetch:
                fetch_t0 = time.perf_counter()
                _progress(f"Fetching Historical OHLCV Data... (0/{len(needs_fetch)})", 43)
                self.logger.info(
                    "SCANNER_FYERS_POOL_START | stage=%s | symbols=%s | max_workers=%s",
                    stage_name,
                    len(needs_fetch),
                    max_workers,
                )
                await asyncio.gather(
                    *(process_symbol_fyers(s, i % max_workers) for i, s in enumerate(needs_fetch))
                )
                stage_timings["fyers_fetch_ms"] = (time.perf_counter() - fetch_t0) * 1000

                # Batch persist deltas (single sequential writer — avoids pool stampedes)
                upsert_t0 = time.perf_counter()
                if pending_upserts:
                    written = await md_service.upsert_candles_multi(pending_upserts)
                    self.logger.info(
                        "SCANNER_UPSERT_BATCH | stage=%s | symbols_written=%s | upsert_ms=%.0f",
                        stage_name,
                        written,
                        (time.perf_counter() - upsert_t0) * 1000,
                    )
                stage_timings["upsert_ms"] = (time.perf_counter() - upsert_t0) * 1000

                # Drop frames that still lack required history after API
                for symbol in list(symbol_frames.keys()):
                    df = symbol_frames[symbol]
                    if df is None or df.empty or len(df) < required_history:
                        if symbol in needs_fetch:
                            self.logger.warning(
                                "Skipping %s gracefully: history (%s) below required (%s).",
                                symbol,
                                0 if df is None or df.empty else len(df),
                                required_history,
                            )
                            symbol_frames.pop(symbol, None)

                self.logger.info(
                    "SCANNER_FYERS_FETCH | stage=%s | requested=%s | frames_now=%s | fetch_ms=%.0f",
                    stage_name,
                    len(needs_fetch),
                    len(symbol_frames),
                    stage_timings["fyers_fetch_ms"],
                )
            else:
                stage_timings["fyers_fetch_ms"] = 0.0
                stage_timings["upsert_ms"] = 0.0

            stage_timings["data_acquisition_ms"] = (time.perf_counter() - phase_t0) * 1000
            self.logger.info(
                "SCANNER_DATA_ACQUISITION_DONE | stage=%s | frames=%s | total_ms=%.0f | timings=%s",
                stage_name,
                len(symbol_frames),
                stage_timings["data_acquisition_ms"],
                {k: int(v) for k, v in stage_timings.items()},
            )

        await fetch_all_symbols()

        total_candles_in_frames = sum(len(df) for df in symbol_frames.values())
        self.logger.debug("MEMORY_AUDIT stage=symbol_frames_loaded rss_mb=%.1f symbols=%s candles=%s", get_rss_mb(), len(symbol_frames), total_candles_in_frames)

        # Forward-fill gaps in memory — use a single global business-day index for ALL symbols
        # instead of creating 755 separate pd.date_range calls (was major CPU tax).
        _progress("Building indicator frame...", 55)
        ffill_t0 = time.perf_counter()
        frame_parts = []
        _all_mins = []
        _all_maxs = []
        for df in symbol_frames.values():
            idx = df.index
            _all_mins.append(idx.min())
            _all_maxs.append(idx.max())
        global_min = min(_all_mins)
        global_max = max(_all_maxs)
        full_index = pd.date_range(start=global_min, end=global_max, freq='B')
        for symbol, df in symbol_frames.items():
            df = df.sort_index()
            df = df.reindex(full_index)
            df = df.ffill()
            
            sym_df = df.copy()
            sym_df["symbol"] = symbol
            sym_df.index.name = "timestamp"
            sym_df = sym_df.reset_index().set_index(["timestamp", "symbol"])
            frame_parts.append(sym_df)
            symbol_frames[symbol] = df
        stage_timings["ffill_ms"] = (time.perf_counter() - ffill_t0) * 1000

        if not frame_parts:
            self.logger.debug("MEMORY_AUDIT stage=no_valid_frames rss_mb=%.1f", get_rss_mb())
            return results

        # Build the single canonical multi-index frame
        combined_frame = pd.concat(frame_parts)
        combined_frame.sort_index(inplace=True)
        # Release intermediate frame_parts immediately
        del frame_parts

        self.logger.debug("MEMORY_AUDIT stage=combined_frame_built rss_mb=%.1f symbols=%s candles=%s", get_rss_mb(), len(symbol_frames), len(combined_frame))

        # Vectorized Bulk Analysis — pass the pre-built frame directly (no OHLCVPoint conversion)
        _progress("Calculating Technical Indicators...", 58)
        self.logger.info("STEP 2/8 | Stage=%s | Run vectorized analyze_bulk on entire universe", stage_name)
        ind_t0 = time.perf_counter()
        bulk_technical_results = self.technical_service.analyze_bulk_from_frame(combined_frame, AnalysisMode.swing)
        stage_timings["indicators_ms"] = (time.perf_counter() - ind_t0) * 1000

        # Release the combined frame — indicators are extracted, we don't need it anymore
        del combined_frame

        self.logger.debug("MEMORY_AUDIT stage=after_bulk_analysis rss_mb=%.1f symbols=%s", get_rss_mb(), len(bulk_technical_results))

        # Evaluate scoring using precomputed results (sync CPU work — no per-symbol await overhead)
        _progress("Evaluating strategy conditions...", 62)
        score_t0 = time.perf_counter()
        SCORING_TAIL_SIZE = 30  # _passes_data_quality uses last 30 candles max
        for idx, symbol in enumerate(symbols):
            sym_df = symbol_frames.get(symbol)
            if sym_df is None or sym_df.empty:
                results.append(ScreenerConditionResult(
                    symbol=symbol, close=0.0, ema_20=0.0, ema_50=0.0, ema50_available=False, ema20_above_ema50=False, sma_30=0.0, sma_50=0.0,
                    sma_100=0.0, sma_200=0.0, macd=0.0, macd_signal=0.0,
                    supertrend=0.0, volume=0, previous_volume=0, screener_score=0.0,
                    technical_signal="unknown", technical_score=0.0, candles_fetched=0,
                    conditions={"data_source_failed": True}, matched=False
                ))
                continue
                
            technical = bulk_technical_results.get(symbol)
            if not technical:
                results.append(ScreenerConditionResult(
                    symbol=symbol, close=0.0, ema_20=0.0, ema_50=0.0, ema50_available=False, ema20_above_ema50=False, sma_30=0.0, sma_50=0.0,
                    sma_100=0.0, sma_200=0.0, macd=0.0, macd_signal=0.0,
                    supertrend=0.0, volume=0, previous_volume=0, screener_score=0.0,
                    technical_signal="unknown", technical_score=0.0, candles_fetched=len(sym_df),
                    conditions={"technical_analysis_failed": True}, matched=False
                ))
                continue

            # Build minimal OHLCVPoint list for scoring functions (tail only)
            total_rows = len(sym_df)
            tail_df = sym_df.tail(SCORING_TAIL_SIZE)
            candles = []
            for ts, row in tail_df.iterrows():
                dt = ts
                if hasattr(dt, "to_pydatetime"):
                    dt = dt.to_pydatetime()
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                candles.append(OHLCVPoint(
                    timestamp=dt,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                ))

            try:
                # Scoring is pure CPU; call without await overhead when possible
                result = await self._process_single_symbol(symbol, lookback_window, stage_name, candles, technical, total_candle_count=total_rows)
                results.append(result)
            except Exception as e:
                self.logger.error("SYMBOL ERROR symbol=%s error=%s", symbol, e)
                scan_ctx = get_current_scan()
                if scan_ctx:
                    log_symbol_failure(scan_ctx, symbol=symbol, stage="scoring", exc=e)
                results.append(ScreenerConditionResult(
                    symbol=symbol, close=0.0, ema_20=0.0, ema_50=0.0, ema50_available=False, ema20_above_ema50=False, sma_30=0.0, sma_50=0.0,
                    sma_100=0.0, sma_200=0.0, macd=0.0, macd_signal=0.0,
                    supertrend=0.0, volume=0, previous_volume=0, screener_score=0.0,
                    technical_signal="unknown", technical_score=0.0, candles_fetched=total_rows,
                    conditions={"processing_error": True}, matched=False
                ))

            if progress_callback:
                if (idx + 1) % 20 == 0 or idx == 0:
                    pct = 62 + int(8 * (idx + 1) / max(1, total_requested))
                    remaining = total_requested - (idx + 1)
                    elapsed = time.perf_counter() - scan_start_time
                    eta_sec = int((elapsed / max(1, (idx + 1))) * remaining) if (idx + 1) > 0 else 0
                    _progress({
                        "stage": f"Evaluating strategy conditions... ({idx + 1}/{total_requested})",
                        "progress": min(pct, 70),
                        "current_symbol": symbol,
                        "done": idx + 1,
                        "remaining": remaining,
                        "total_scoring": total_requested,
                        "eta_sec": eta_sec,
                    })

        stage_timings["scoring_ms"] = (time.perf_counter() - score_t0) * 1000

        # Store frames for orchestrator reuse (avoids duplicate fetch in run_full)
        ScreenerService.last_fetched_frames = {s: df.copy() for s, df in symbol_frames.items() if df is not None and not df.empty and len(df) >= MINIMUM_SWING_CANDLES}
        # Release symbol_frames explicitly after scoring loop
        del symbol_frames

        # Post-process aggregated results to compute summaries
        data_source_failed = sum(1 for r in results if r.conditions.get("data_source_failed"))
        data_quality_failed = sum(1 for r in results if r.conditions.get("data_quality_failed"))
        matched_count = sum(1 for r in results if r.matched)
        rejected_by_conditions = len(results) - matched_count - data_source_failed - data_quality_failed

        condition_failure_counts: dict[str, int] = {}
        for r in results:
            if r.conditions:
                failed_conditions = [name for name, passed in r.conditions.items() if not passed]
                for failed_condition in failed_conditions:
                    condition_failure_counts[failed_condition] = condition_failure_counts.get(failed_condition, 0) + 1

        self.logger.info(
            "STEP 4/8 | Weighted scoring completed | requested=%s | evaluated=%s | matched=%s | rejected_by_conditions=%s | data_source_failed=%s | data_quality_failed=%s",
            total_requested,
            len(results),
            matched_count,
            rejected_by_conditions,
            data_source_failed,
            data_quality_failed,
        )
        scan_log.info("%s", "=" * 60)
        scan_log.info(
            "SCAN COMPLETE | total=%s | matched=%s | rejected=%s | datasource_failed=%s | data_quality_failed=%s",
            total_requested,
            matched_count,
            rejected_by_conditions,
            data_source_failed,
            data_quality_failed,
        )
        scan_log.info("%s", "=" * 60)
        if condition_failure_counts:
            self.logger.info(
                "STEP 4/8 | Condition failure summary | %s",
                ", ".join("%s=%s" % item for item in condition_failure_counts.items()),
            )
        # Pipeline stage diagnostics
        scan_ctx = get_current_scan()
        if scan_ctx:
            scan_ctx.symbols_processed = total_requested
            scan_ctx.data_source_failures = data_source_failed
            log_pipeline_stage(scan_ctx, "symbol_evaluation", 4, total_requested, len(results), rejected_by_conditions + data_source_failed + data_quality_failed, 0)
        results.sort(key=lambda item: (-item.screener_score, item.symbol))
        
        self.logger.debug("MEMORY_AUDIT stage=scanner_completion rss_mb=%.1f symbols=%s", get_rss_mb(), len(results))
        
        duration_ms = int((time.perf_counter() - scan_start_time) * 1000)
        stage_timings["total_ms"] = float(duration_ms)
        # Timing report for operators (percent of wall clock)
        total_for_pct = max(duration_ms, 1)
        pct = {
            "data_acquisition": 100.0 * stage_timings.get("data_acquisition_ms", 0.0) / total_for_pct,
            "fyers_fetch": 100.0 * stage_timings.get("fyers_fetch_ms", 0.0) / total_for_pct,
            "cache_bulk_load": 100.0 * stage_timings.get("cache_bulk_load_ms", 0.0) / total_for_pct,
            "indicators": 100.0 * stage_timings.get("indicators_ms", 0.0) / total_for_pct,
            "scoring": 100.0 * stage_timings.get("scoring_ms", 0.0) / total_for_pct,
            "ffill": 100.0 * stage_timings.get("ffill_ms", 0.0) / total_for_pct,
        }
        self.logger.info(
            "SCANNER_TIMING_REPORT | stage=%s | total_ms=%s | data_acquisition_ms=%.0f (%.1f%%) | fyers_fetch_ms=%.0f (%.1f%%) | cache_bulk_load_ms=%.0f (%.1f%%) | indicators_ms=%.0f (%.1f%%) | scoring_ms=%.0f (%.1f%%) | ffill_ms=%.0f (%.1f%%) | matched=%s",
            stage_name,
            duration_ms,
            stage_timings.get("data_acquisition_ms", 0.0),
            pct["data_acquisition"],
            stage_timings.get("fyers_fetch_ms", 0.0),
            pct["fyers_fetch"],
            stage_timings.get("cache_bulk_load_ms", 0.0),
            pct["cache_bulk_load"],
            stage_timings.get("indicators_ms", 0.0),
            pct["indicators"],
            stage_timings.get("scoring_ms", 0.0),
            pct["scoring"],
            stage_timings.get("ffill_ms", 0.0),
            pct["ffill"],
            matched_count,
        )
        self.logger.info(
            "SCANNER_RUN_SUCCESS | stage=%s | symbols_scanned=%s | symbols_shortlisted=%s | duration_ms=%s",
            stage_name,
            total_requested,
            matched_count,
            duration_ms,
        )
        
        return results

    def _log_determinism_debug(self, payload: dict[str, object]) -> None:
        if os.getenv("SCANNER_DETERMINISM_DEBUG", "").strip().lower() not in {"1", "true", "yes", "on"}:
            return
        self.logger.info("SCANNER_DETERMINISM %s", json.dumps(payload, sort_keys=True, default=str))

    def _passes_data_quality(self, candles: list[OHLCVPoint], total_candle_count: int | None = None) -> bool:
        count = total_candle_count if total_candle_count is not None else len(candles)
        if count < MINIMUM_SWING_CANDLES:
            return False
        recent = candles[-30:]
        if any(candle.close <= 0 or candle.high <= 0 or candle.low <= 0 for candle in recent):
            return False
        if sum(1 for candle in recent if candle.volume > 0) < 25:
            return False
        return True

    def _passes_broad_trend(self, candles: list[OHLCVPoint], technical) -> bool:
        indicators = technical.indicators
        latest_close = candles[-1].close
        sma_50 = float(indicators.get("sma_50", 0.0))
        sma_200 = float(indicators.get("sma_200", 0.0))
        if sma_50 <= 0 or sma_200 <= 0:
            return False
        avg_volume = mean(candle.volume for candle in candles[-20:])
        return bool(
            latest_close > sma_50
            and sma_50 > sma_200
            and avg_volume > 100000
        )

    def _build_conditions(
        self,
        indicators: dict[str, float | str | bool],
        latest: OHLCVPoint,
        previous: OHLCVPoint,
        broad_eligibility: bool,
        technical,
    ) -> dict[str, bool]:
        return {
            "broad_trend_eligibility": broad_eligibility,
            "hard_filters_pass": bool(indicators.get("hard_filters_pass", False)),
            "core_trend_filter_pass": bool(indicators.get("core_trend_filter_pass", False)),
            "core_momentum_filter_pass": bool(indicators.get("core_momentum_filter_pass", False)),
            "basic_liquidity_filter_pass": bool(indicators.get("basic_liquidity_filter_pass", False)),
            "close_above_ema20": bool(indicators.get("close_above_ema20", False)),
            "ema50_available": bool(indicators.get("ema50_available", False)),
            "ema20_above_ema50": bool(indicators.get("ema20_above_ema50", False)),
            "supertrend_positive": bool(indicators.get("supertrend_positive", False)),
            "macd_positive": bool(indicators.get("macd_positive", False)),
            "rsi_supportive": bool(indicators.get("rsi_supportive", False)),
            "sma_uptrend_20d": bool(indicators.get("sma_uptrend_20d", False)),
            "hh_hl_2d": bool(indicators.get("hh_hl_2d", False)),
            "hh_hl_3d": bool(indicators.get("hh_hl_3d", False)),
            "hh_hl_4d": bool(indicators.get("hh_hl_4d", False)),
            "latest_confirms_5d_structure": bool(indicators.get("latest_confirms_5d_structure", False)),
            "structure_supportive": bool(indicators.get("structure_supportive", False)),
            "hammer_or_gravestone": bool(indicators.get("hammer_or_gravestone", False)),
            "volume_above_50000": latest.volume > 50000,
            "volume_above_previous_day": latest.volume > previous.volume,
            "price_above_100": latest.close > 100,
            "price_below_500000": latest.close < 500000,
            "technical_engine_bullish": technical.signal in {"bullish", "neutral"} and technical.score >= 52,
        }

    def _weighted_score(
        self,
        candles: list[OHLCVPoint],
        technical,
        conditions: dict[str, bool],
    ) -> float:
        latest = candles[-1]
        previous = candles[-2]
        volume_lift = ((latest.volume - previous.volume) / previous.volume) * 100 if previous.volume else 0
        score = 0.0
        score += technical.score * 0.5
        score += 12 if conditions["broad_trend_eligibility"] else 0
        score += 6 if conditions["hard_filters_pass"] else 0
        score += 4 if conditions["close_above_ema20"] else 0
        score += 5 if (conditions.get("ema50_available") and conditions.get("ema20_above_ema50")) else 0
        score += 4 if conditions["supertrend_positive"] else 0
        score += 4 if conditions["macd_positive"] else 0
        score += 3 if conditions["rsi_supportive"] else 0
        score += 4 if conditions["sma_uptrend_20d"] else 0
        score += 3 if conditions["hh_hl_2d"] else 0
        score += 3 if conditions["hh_hl_3d"] else 0
        score += 3 if conditions["hh_hl_4d"] else 0
        score += 3 if conditions["latest_confirms_5d_structure"] else 0
        score += 3 if conditions["structure_supportive"] else 0
        score += 2 if conditions["hammer_or_gravestone"] else 0
        score += 3 if conditions["volume_above_50000"] else 0
        score += 3 if conditions["volume_above_previous_day"] else 0
        score += min(max(volume_lift, 0), 8)
        return round(min(score, 100.0), 2)
