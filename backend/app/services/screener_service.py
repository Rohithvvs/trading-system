from __future__ import annotations

from statistics import mean

from ..config import settings
from ..schemas import AnalysisMode, OHLCVPoint, ScreenerConditionResult
from ..utils import get_logger
from .fyers_service import FyersService
from .technical_analysis_service import TechnicalAnalysisService


class ScreenerService:
    def __init__(self) -> None:
        self.fyers_service = FyersService()
        self.technical_service = TechnicalAnalysisService()
        self.logger = get_logger("app.screener")

    def screen_symbols_swing(self, symbols: list[str], lookback_window: int) -> list[ScreenerConditionResult]:
        results: list[ScreenerConditionResult] = []
        self.logger.info(
            "STEP 1/8 | Fetch real OHLCV for configured swing universe | symbols=%s | lookback=%s",
            len(symbols),
            lookback_window,
        )

        for symbol in symbols:
            candles = self.fyers_service.fetch_ohlcv(
                symbol=symbol,
                mode=AnalysisMode.swing,
                resolution="1d",
                lookback_window=max(lookback_window, 260),
            )

            self.logger.info("STEP 2/8 | Validate data quality | symbol=%s", symbol)
            if not self._passes_data_quality(candles):
                self.logger.info("STEP 2/8 | Data quality failed | symbol=%s", symbol)
                continue

            technical = self.technical_service.analyze(symbol, candles, AnalysisMode.swing)
            indicators = technical.indicators
            latest = candles[-1]
            previous = candles[-2]

            self.logger.info("STEP 3/8 | Apply broad trend eligibility | symbol=%s", symbol)
            broad_eligibility = self._passes_broad_trend(candles, technical)

            self.logger.info("STEP 4/8 | Compute weighted screener score | symbol=%s", symbol)
            conditions = self._build_conditions(indicators, latest, previous, broad_eligibility, technical)
            screener_score = self._weighted_score(candles, technical, conditions)
            matched = broad_eligibility and screener_score >= 60

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
                conditions=conditions,
                matched=matched,
            )
            results.append(result)

            failed_conditions = [name for name, passed in conditions.items() if not passed]
            if matched:
                self.logger.info(
                    "STEP 4/8 | Symbol eligible for shortlist pool | symbol=%s | screener_score=%s | technical_score=%s",
                    symbol,
                    screener_score,
                    technical.score,
                )
            else:
                self.logger.info(
                    "STEP 4/8 | Symbol below threshold | symbol=%s | screener_score=%s | failed_conditions=%s",
                    symbol,
                    screener_score,
                    ",".join(failed_conditions),
                )

        self.logger.info(
            "STEP 4/8 | Weighted scoring completed | evaluated=%s | eligible=%s",
            len(results),
            len([item for item in results if item.matched]),
        )
        return results

    def _passes_data_quality(self, candles: list[OHLCVPoint]) -> bool:
        if len(candles) < 220:
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
            and technical.score >= 52
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
