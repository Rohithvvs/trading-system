from __future__ import annotations

from statistics import mean
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

from ..config import settings
from ..schemas import AnalysisMode, OHLCVPoint, ScreenerConditionResult
from ..utils import get_logger
from .fyers_service import FyersService, FyersRateLimitError
from .technical_analysis_service import TechnicalAnalysisService
from ..core.log_manager import scanner_logger
from datetime import datetime

MINIMUM_SWING_CANDLES = 220


class TokenBucketRateLimiter:
    def __init__(self, calls_per_second: float = 5.0):
        self.capacity = calls_per_second
        self.tokens = calls_per_second
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.capacity
            )
            self.last_refill = now
            if self.tokens >= 1:
                self.tokens -= 1
                return
        time.sleep(1.0 / self.capacity)
        self.acquire()


_rate_limiter = TokenBucketRateLimiter(calls_per_second=5.0)


class ScreenerService:
    def __init__(self, fyers_service: FyersService | None = None) -> None:
        self.fyers_service = fyers_service or FyersService()
        self.technical_service = TechnicalAnalysisService()
        self.logger = get_logger("app.screener")

    def _process_single_symbol(self, symbol: str, lookback_window: int, stage_name: str) -> ScreenerConditionResult:
        """Process a single symbol and return a ScreenerConditionResult.
        This contains the original symbol-level logic extracted from the
        sequential loop. Do NOT change the internal logic here when
        parallelizing the outer loop.
        """
        # Begin symbol scanning
        self.logger.info("STEP 1/8 | Begin symbol screening | stage=%s | symbol=%s", stage_name, symbol)
        candles = self.fyers_service.get_candles_cached(
            symbol=symbol,
            mode=AnalysisMode.swing,
            resolution="1d",
            lookback_window=max(lookback_window, 260),
            allow_mock=False,
        )
        candle_source = self.fyers_service.get_ohlcv_source(symbol, AnalysisMode.swing, "1d")
        minimum_swing_candles_met = len(candles) >= MINIMUM_SWING_CANDLES
        self.logger.info(
            "CANDLE CHECK | symbol=%s | candles=%s | minimum_required=%s | met=%s",
            symbol,
            len(candles),
            MINIMUM_SWING_CANDLES,
            minimum_swing_candles_met,
        )
        # mirror scan-log if available (scan runner created it once per run)
        scan_log = getattr(self, "_scan_log", None)
        if scan_log is not None:
            scan_log.info(
                "CANDLE CHECK | symbol=%s | candles=%s | minimum=%s | met=%s",
                symbol,
                len(candles),
                MINIMUM_SWING_CANDLES,
                minimum_swing_candles_met,
            )

        # Validate data quality
        self.logger.info("STEP 2/8 | Stage=%s | Validate data quality | symbol=%s", stage_name, symbol)
        if candle_source in {"MOCK_FALLBACK", "NO_DATA"}:
            self.logger.info(
                "STEP 2/8 | Rejected non-live symbol | symbol=%s | source=%s | candles=%s | allow_mock=%s",
                symbol,
                candle_source,
                len(candles),
                False,
            )
            if scan_log is not None:
                scan_log.info("SKIP datasource_failed | symbol=%s | source=%s", symbol, candle_source)
                try:
                    scan_log.info(
                        "SCAN_ENTRY | symbol=%s | score=0.0 | signal=unknown | confidence=0.0 | timestamp=%s",
                        symbol,
                        datetime.utcnow().isoformat(),
                    )
                except Exception:
                    pass
            return ScreenerConditionResult(
                symbol=symbol,
                close=0.0,
                ema_20=0.0,
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
                candles_fetched=len(candles),
                conditions={"data_source_failed": True},
                matched=False,
            )

        if not self._passes_data_quality(candles):
            latest = candles[-1] if candles else None
            self.logger.info(
                "STEP 2/8 | Data quality failed | symbol=%s | source=%s | candles=%s | latest_close=%s | latest_volume=%s",
                symbol,
                candle_source,
                len(candles),
                latest.close if latest else "n/a",
                latest.volume if latest else "n/a",
            )
            if scan_log is not None:
                scan_log.info("SKIP data_quality_failed | symbol=%s | candles=%s", symbol, len(candles))
                try:
                    scan_log.info(
                        "SCAN_ENTRY | symbol=%s | score=0.0 | signal=unknown | confidence=0.0 | timestamp=%s",
                        symbol,
                        datetime.utcnow().isoformat(),
                    )
                except Exception:
                    pass
            return ScreenerConditionResult(
                symbol=symbol,
                close=latest.close if latest else 0.0,
                ema_20=0.0,
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
                candles_fetched=len(candles),
                conditions={"data_quality_failed": True},
                matched=False,
            )

        technical = self.technical_service.analyze(symbol, candles, AnalysisMode.swing)
        indicators = technical.indicators
        latest = candles[-1]
        previous = candles[-2]

        # Apply broad trend eligibility
        self.logger.info("STEP 3/8 | Stage=%s | Apply broad trend eligibility | symbol=%s", stage_name, symbol)
        broad_eligibility = self._passes_broad_trend(candles, technical)

        # Log broad trend failures specifically to the scan log when present
        if scan_log is not None and not broad_eligibility:
            sma50 = float(indicators.get("sma_50", 0.0))
            sma200 = float(indicators.get("sma_200", 0.0))
            scan_log.info(
                "SKIP broad_trend_failed | symbol=%s | score=%.1f | sma50=%.2f | sma200=%.2f",
                symbol,
                technical.score,
                sma50,
                sma200,
            )

        # Compute weighted screener score
        self.logger.info("STEP 4/8 | Stage=%s | Compute weighted screener score | symbol=%s", stage_name, symbol)
        conditions = self._build_conditions(indicators, latest, previous, broad_eligibility, technical)
        screener_score = self._weighted_score(candles, technical, conditions)
        matched = broad_eligibility and screener_score >= 52

        result = ScreenerConditionResult(
            symbol=symbol,
            close=round(latest.close, 2),
            ema_20=float(indicators.get("ema_20", 0.0)),
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
            candles_fetched=len(candles),
            conditions=conditions,
            matched=matched,
        )

        # mirror pass/fail to scan log
        if scan_log is not None:
            if result.matched:
                scan_log.info(
                    "PASS shortlisted | symbol=%s | screener_score=%.1f | technical_score=%.1f | signal=%s",
                    symbol,
                    result.screener_score,
                    result.technical_score,
                    result.technical_signal,
                )
            else:
                failed_conditions = [name for name, passed in result.conditions.items() if not passed]
                scan_log.info(
                    "FAIL below_threshold | symbol=%s | screener_score=%.1f | broad_eligibility=%s | failed=%s",
                    symbol,
                    result.screener_score,
                    broad_eligibility,
                    ",".join(failed_conditions),
                )
            try:
                scan_log.info(
                    "SCAN_ENTRY | symbol=%s | score=%.1f | signal=%s | confidence=%.2f | timestamp=%s",
                    symbol,
                    result.screener_score,
                    result.technical_signal,
                    result.technical_score or 0.0,
                    datetime.utcnow().isoformat(),
                )
            except Exception:
                pass

        return result

    def _process_symbol_safe(self, symbol: str, lookback_window: int, stage_name: str) -> ScreenerConditionResult:
        """Wrapper that rate-limits and retries on Fyers rate-limit errors."""
        max_retries = 3
        backoff = 2.0
        for attempt in range(max_retries):
            try:
                _rate_limiter.acquire()
                return self._process_single_symbol(symbol, lookback_window, stage_name)
            except FyersRateLimitError:
                wait = backoff ** attempt
                self.logger.warning(
                    "RATE LIMIT symbol=%s attempt=%s waiting=%.1fs",
                    symbol,
                    attempt + 1,
                    wait,
                )
                time.sleep(wait)
            except Exception as e:
                self.logger.error("SYMBOL ERROR symbol=%s error=%s", symbol, e)
                # Return a minimal failed ScreenerConditionResult
                return ScreenerConditionResult(
                    symbol=symbol,
                    close=0.0,
                    ema_20=0.0,
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
                    conditions={"processing_error": True},
                    matched=False,
                )
        return ScreenerConditionResult(
            symbol=symbol,
            close=0.0,
            ema_20=0.0,
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
            conditions={"processing_failed": True},
            matched=False,
        )

    def screen_symbols_swing(
        self,
        symbols: list[str],
        lookback_window: int,
        stage_name: str = "Unknown",
    ) -> list[ScreenerConditionResult]:
        results: list[ScreenerConditionResult] = []
        total_requested = len(symbols)

        # use centralized scanner logger (rotating file handler)
        scan_log = scanner_logger
        # make scan_log available to worker threads
        self._scan_log = scan_log

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

        # Parallel execution with bounded workers and per-symbol retries
        MAX_WORKERS = 6
        futures_map = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures_map = {
                executor.submit(self._process_symbol_safe, symbol, lookback_window, stage_name): symbol
                for symbol in symbols
            }

            for future in as_completed(futures_map):
                symbol = futures_map[future]
                try:
                    result = future.result(timeout=60)
                    results.append(result)
                    self.logger.info("COMPLETED symbol=%s", symbol)
                except Exception as e:
                    self.logger.error("FUTURE ERROR symbol=%s error=%s", symbol, e)
                    # Append a minimal error result to keep lengths consistent
                    results.append(
                        ScreenerConditionResult(
                            symbol=symbol,
                            close=0.0,
                            ema_20=0.0,
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
                            conditions={"future_error": True},
                            matched=False,
                        )
                    )

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
                ", ".join(f"%s=%s" % item for item in condition_failure_counts.items()),
            )
        return results

    def _passes_data_quality(self, candles: list[OHLCVPoint]) -> bool:
        if len(candles) < MINIMUM_SWING_CANDLES:
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
        avg_volume = mean(candle.volume for candle in candles[-20:])
        return bool(
            latest_close > sma_50
            and sma_50 > sma_200
            and bool(indicators.get("hard_filters_pass", False))
            and technical.score >= 48
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
