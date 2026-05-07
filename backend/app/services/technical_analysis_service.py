from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, SMAIndicator
from ta.volume import VolumeWeightedAveragePrice

from ..schemas import AnalysisMode, OHLCVPoint, TechnicalAnalysisResult
from ..utils import get_logger


@dataclass(slots=True)
class SupertrendPoint:
    value: float
    direction_up: bool


class TechnicalAnalysisService:
    def __init__(self) -> None:
        self.logger = get_logger("app.technical")

    def analyze(self, symbol: str, candles: list[OHLCVPoint], mode: AnalysisMode) -> TechnicalAnalysisResult:
        self.logger.info(
            "TECHNICAL | Start analysis | symbol=%s | mode=%s | candles=%s",
            symbol,
            mode.value,
            len(candles),
        )
        if not candles:
            return TechnicalAnalysisResult(
                mode=mode,
                signal="unknown",
                score=0.0,
                indicators={},
                summary=f"{symbol} could not be analyzed because no live OHLCV candles were available.",
            )
        frame = pd.DataFrame(
            {
                "open": [candle.open for candle in candles],
                "high": [candle.high for candle in candles],
                "low": [candle.low for candle in candles],
                "close": [candle.close for candle in candles],
                "volume": [candle.volume for candle in candles],
            }
        )
        indicators, score, signal = self._build_indicator_payload(mode, frame)
        self._log_analysis_decision(symbol, mode, indicators, score, signal)
        summary = (
            f"{symbol} shows a {signal} {mode.value} setup with a technical score of {score}. "
            "The score blends trend, momentum, volume, and structure checks from the technical engine."
        )
        return TechnicalAnalysisResult(mode=mode, signal=signal, score=score, indicators=indicators, summary=summary)

    def _build_indicator_payload(
        self,
        mode: AnalysisMode,
        frame: pd.DataFrame,
    ) -> tuple[dict[str, float | str | bool], float, str]:
        last_close = float(frame["close"].iloc[-1])

        if mode == AnalysisMode.intraday:
            ema_9 = float(EMAIndicator(close=frame["close"], window=9).ema_indicator().iloc[-1])
            ema_20 = float(EMAIndicator(close=frame["close"], window=20).ema_indicator().iloc[-1])
            rsi_14 = float(RSIIndicator(close=frame["close"], window=14).rsi().iloc[-1])
            macd = MACD(close=frame["close"], window_slow=26, window_fast=12, window_sign=9)
            macd_value = float(macd.macd().iloc[-1])
            macd_signal = float(macd.macd_signal().iloc[-1])
            vwap = float(
                VolumeWeightedAveragePrice(
                    high=frame["high"],
                    low=frame["low"],
                    close=frame["close"],
                    volume=frame["volume"],
                    window=14,
                ).volume_weighted_average_price().iloc[-1]
            )
            avg_volume_short = float(frame["volume"].tail(5).mean())
            avg_volume_long = float(frame["volume"].tail(20).mean())
            volume_trend = "expanding" if avg_volume_short > avg_volume_long else "stable"
            close_above_vwap = bool(last_close > vwap)
            score = 0.0
            score += 20 if close_above_vwap else 0
            score += 20 if ema_9 > ema_20 else 0
            score += 15 if macd_value > macd_signal else 0
            score += 15 if 52 <= rsi_14 <= 72 else 8 if rsi_14 >= 45 else 0
            score += 15 if volume_trend == "expanding" else 5
            score += 15 if last_close > ema_9 else 0
            score = round(min(score, 100.0), 2)
            signal = "bullish" if score >= 68 else "neutral" if score >= 48 else "bearish"
            return {
                "vwap": round(vwap, 2),
                "ema_9": round(ema_9, 2),
                "ema_20": round(ema_20, 2),
                "rsi_14": round(rsi_14, 2),
                "macd": round(macd_value, 4),
                "macd_signal": round(macd_signal, 4),
                "volume_trend": volume_trend,
                "close_above_vwap": close_above_vwap,
            }, score, signal

        ema_20 = float(EMAIndicator(close=frame["close"], window=20).ema_indicator().iloc[-1])
        sma_20_series = SMAIndicator(close=frame["close"], window=20).sma_indicator()
        sma_20 = float(sma_20_series.iloc[-1])
        sma_30 = float(SMAIndicator(close=frame["close"], window=30).sma_indicator().iloc[-1])
        sma_50_series = SMAIndicator(close=frame["close"], window=50).sma_indicator()
        sma_50 = float(sma_50_series.iloc[-1])
        sma_100 = float(SMAIndicator(close=frame["close"], window=100).sma_indicator().iloc[-1])
        sma_200 = float(SMAIndicator(close=frame["close"], window=200).sma_indicator().iloc[-1])
        rsi_14 = float(RSIIndicator(close=frame["close"], window=14).rsi().iloc[-1])
        macd = MACD(close=frame["close"], window_slow=26, window_fast=12, window_sign=9)
        macd_value = float(macd.macd().iloc[-1])
        macd_signal = float(macd.macd_signal().iloc[-1])
        support = float(frame["low"].tail(20).min())
        resistance = float(frame["high"].tail(20).max())
        supertrend_point = self._calculate_supertrend(frame).iloc[-1]
        latest = frame.iloc[-1]
        prev_1 = frame.iloc[-2]
        prev_2 = frame.iloc[-3]
        prev_3 = frame.iloc[-4]
        prev_4 = frame.iloc[-5]
        prev_5 = frame.iloc[-6]

        close_above_ema20 = bool(last_close > ema_20)
        supertrend_positive = bool(supertrend_point.direction_up and last_close >= supertrend_point.value)
        macd_positive = bool(macd_value > macd_signal)
        sma_uptrend_20d = bool(sma_20_series.iloc[-1] > sma_20_series.iloc[-20])
        hh_hl_2d = bool(prev_1["high"] > prev_2["high"] and prev_1["low"] > prev_2["low"])
        hh_hl_3d = bool(prev_1["high"] > prev_3["high"] and prev_1["low"] > prev_3["low"])
        hh_hl_4d = bool(prev_1["high"] > prev_4["high"] and prev_1["low"] > prev_4["low"])
        latest_confirms_5d_structure = bool(latest["high"] > prev_1["high"] and prev_1["low"] > prev_5["low"])
        hammer = self._is_hammer(latest)
        gravestone_doji = self._is_gravestone_doji(latest)
        hammer_or_gravestone = bool(hammer or gravestone_doji)
        volume_above_50000 = bool(latest["volume"] > 50000)
        volume_above_previous_day = bool(latest["volume"] > prev_1["volume"])
        price_above_100 = bool(last_close > 100)
        price_below_500000 = bool(last_close < 500000)
        rsi_supportive = bool(rsi_14 >= 50)
        rsi_in_buy_zone = bool(55 <= rsi_14 <= 68)
        volume_supportive = bool(volume_above_50000 and price_above_100 and price_below_500000)
        core_trend_filter_pass = bool(close_above_ema20 and supertrend_positive)
        core_momentum_filter_pass = bool(macd_positive and rsi_supportive)
        basic_liquidity_filter_pass = bool(volume_supportive)
        structure_score = sum(
            [
                hh_hl_2d,
                hh_hl_3d,
                hh_hl_4d,
                latest_confirms_5d_structure,
            ]
        )
        structure_supportive = bool(structure_score >= 2)
        higher_timeframe_trend = (
            "uptrend" if last_close > sma_50 and sma_20 > sma_50 else "sideways" if last_close > sma_50 else "downtrend"
        )

        score = 0.0
        score += 18 if close_above_ema20 else 0
        score += 16 if supertrend_positive else 0
        score += 12 if macd_positive else 0
        score += 8 if rsi_supportive else 0
        score += 6 if rsi_in_buy_zone else 0
        score += 8 if sma_uptrend_20d else 0
        score += 10 if higher_timeframe_trend == "uptrend" else 4 if higher_timeframe_trend == "sideways" else 0
        score += 5 if volume_above_50000 else 0
        score += 4 if volume_above_previous_day else 0
        score += 4 if price_above_100 else 0
        score += 2 if price_below_500000 else 0
        score += min(structure_score * 3, 12)
        score += 4 if hammer_or_gravestone else 0
        score = round(min(score, 100.0), 2)

        hard_filters_pass = bool(
            core_trend_filter_pass
            and core_momentum_filter_pass
            and basic_liquidity_filter_pass
        )
        signal = "bullish" if hard_filters_pass and score >= 72 else "neutral" if hard_filters_pass and score >= 52 else "bearish"
        return {
            "ema_20": round(ema_20, 2),
            "sma_20": round(sma_20, 2),
            "sma_30": round(sma_30, 2),
            "sma_50": round(sma_50, 2),
            "sma_100": round(sma_100, 2),
            "sma_200": round(sma_200, 2),
            "rsi_14": round(rsi_14, 2),
            "macd": round(macd_value, 4),
            "macd_signal": round(macd_signal, 4),
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "higher_timeframe_trend": higher_timeframe_trend,
            "supertrend": round(supertrend_point.value, 2),
            "close_above_ema20": close_above_ema20,
            "supertrend_positive": supertrend_positive,
            "macd_positive": macd_positive,
            "rsi_supportive": rsi_supportive,
            "rsi_in_buy_zone": rsi_in_buy_zone,
            "sma_uptrend_20d": sma_uptrend_20d,
            "hh_hl_2d": hh_hl_2d,
            "hh_hl_3d": hh_hl_3d,
            "hh_hl_4d": hh_hl_4d,
            "latest_confirms_5d_structure": latest_confirms_5d_structure,
            "structure_score": float(structure_score),
            "structure_supportive": structure_supportive,
            "hammer": hammer,
            "gravestone_doji": gravestone_doji,
            "hammer_or_gravestone": hammer_or_gravestone,
            "volume_above_50000": volume_above_50000,
            "volume_above_previous_day": volume_above_previous_day,
            "price_above_100": price_above_100,
            "price_below_500000": price_below_500000,
            "core_trend_filter_pass": core_trend_filter_pass,
            "core_momentum_filter_pass": core_momentum_filter_pass,
            "basic_liquidity_filter_pass": basic_liquidity_filter_pass,
            "hard_filters_pass": hard_filters_pass,
        }, score, signal

    def _log_analysis_decision(
        self,
        symbol: str,
        mode: AnalysisMode,
        indicators: dict[str, float | str | bool],
        score: float,
        signal: str,
    ) -> None:
        if mode == AnalysisMode.intraday:
            self.logger.info(
                "TECHNICAL | Intraday decision | symbol=%s | signal=%s | score=%s | close_above_vwap=%s | ema_alignment=%s | macd_positive=%s | rsi=%s | volume_trend=%s",
                symbol,
                signal,
                score,
                bool(indicators.get("close_above_vwap", False)),
                bool(float(indicators.get("ema_9", 0.0)) > float(indicators.get("ema_20", 0.0))),
                bool(float(indicators.get("macd", 0.0)) > float(indicators.get("macd_signal", 0.0))),
                indicators.get("rsi_14", 0.0),
                indicators.get("volume_trend", "unknown"),
            )
            return

        failed_hard_filters = [
            name
            for name in (
                "core_trend_filter_pass",
                "core_momentum_filter_pass",
                "basic_liquidity_filter_pass",
            )
            if not bool(indicators.get(name, False))
        ]
        passed_structure_checks = [
            name
            for name in (
                "hh_hl_2d",
                "hh_hl_3d",
                "hh_hl_4d",
                "latest_confirms_5d_structure",
            )
            if bool(indicators.get(name, False))
        ]
        confirmation_checks = [
            name
            for name in (
                "hammer_or_gravestone",
                "volume_above_previous_day",
                "sma_uptrend_20d",
                "rsi_in_buy_zone",
            )
            if bool(indicators.get(name, False))
        ]
        self.logger.info(
            "TECHNICAL | Swing decision | symbol=%s | signal=%s | score=%s | hard_filters_pass=%s | failed_hard_filters=%s | trend=%s/%s | momentum=%s/%s | rsi=%s | structure_score=%s | structure_checks=%s | confirmations=%s",
            symbol,
            signal,
            score,
            bool(indicators.get("hard_filters_pass", False)),
            ",".join(failed_hard_filters) if failed_hard_filters else "none",
            bool(indicators.get("close_above_ema20", False)),
            bool(indicators.get("supertrend_positive", False)),
            bool(indicators.get("macd_positive", False)),
            bool(indicators.get("rsi_supportive", False)),
            indicators.get("rsi_14", 0.0),
            indicators.get("structure_score", 0.0),
            ",".join(passed_structure_checks) if passed_structure_checks else "none",
            ",".join(confirmation_checks) if confirmation_checks else "none",
        )

    def _calculate_supertrend(
        self,
        frame: pd.DataFrame,
        period: int = 10,
        multiplier: float = 3.0,
    ) -> pd.Series:
        high = frame["high"]
        low = frame["low"]
        close = frame["close"]

        tr = pd.concat(
            [
                high - low,
                (high - close.shift(1)).abs(),
                (low - close.shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.ewm(alpha=1 / period, adjust=False).mean()
        hl2 = (high + low) / 2
        upperband = hl2 + (multiplier * atr)
        lowerband = hl2 - (multiplier * atr)

        supertrend: list[SupertrendPoint] = []
        final_upper = upperband.copy()
        final_lower = lowerband.copy()

        for index in range(len(frame)):
            if index == 0:
                supertrend.append(SupertrendPoint(value=float(lowerband.iloc[index]), direction_up=True))
                continue

            prev_close = close.iloc[index - 1]
            prev_super = supertrend[index - 1]

            if upperband.iloc[index] < final_upper.iloc[index - 1] or prev_close > final_upper.iloc[index - 1]:
                final_upper.iloc[index] = upperband.iloc[index]
            else:
                final_upper.iloc[index] = final_upper.iloc[index - 1]

            if lowerband.iloc[index] > final_lower.iloc[index - 1] or prev_close < final_lower.iloc[index - 1]:
                final_lower.iloc[index] = lowerband.iloc[index]
            else:
                final_lower.iloc[index] = final_lower.iloc[index - 1]

            if prev_super.value == final_upper.iloc[index - 1]:
                if close.iloc[index] <= final_upper.iloc[index]:
                    supertrend.append(SupertrendPoint(value=float(final_upper.iloc[index]), direction_up=False))
                else:
                    supertrend.append(SupertrendPoint(value=float(final_lower.iloc[index]), direction_up=True))
            else:
                if close.iloc[index] >= final_lower.iloc[index]:
                    supertrend.append(SupertrendPoint(value=float(final_lower.iloc[index]), direction_up=True))
                else:
                    supertrend.append(SupertrendPoint(value=float(final_upper.iloc[index]), direction_up=False))

        return pd.Series(supertrend)

    def _is_hammer(self, candle: pd.Series) -> bool:
        body = abs(candle["close"] - candle["open"])
        range_size = candle["high"] - candle["low"]
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]
        upper_wick = candle["high"] - max(candle["open"], candle["close"])
        if range_size == 0:
            return False
        return bool(lower_wick >= body * 2 and upper_wick <= body and body / range_size < 0.4)

    def _is_gravestone_doji(self, candle: pd.Series) -> bool:
        body = abs(candle["close"] - candle["open"])
        range_size = candle["high"] - candle["low"]
        upper_wick = candle["high"] - max(candle["open"], candle["close"])
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]
        if range_size == 0:
            return False
        return bool(body / range_size < 0.1 and upper_wick > range_size * 0.6 and lower_wick < range_size * 0.15)
