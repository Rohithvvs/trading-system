from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, SMAIndicator
from ta.volume import VolumeWeightedAveragePrice

from ..schemas import AnalysisMode, OHLCVPoint, TechnicalAnalysisResult
from ..utils import get_logger
import os
import psutil

def get_rss_mb():
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)

@dataclass(slots=True)
class SupertrendPoint:
    value: float
    direction_up: bool


class TechnicalAnalysisService:
    def __init__(self) -> None:
        self.logger = get_logger("app.technical")
        
    def get_required_candle_count(self, mode: AnalysisMode) -> int:
        if mode == AnalysisMode.intraday:
            # 26 (MACD) + warmup
            return 40
        else:
            # 200 (SMA200) + warmup
            return 240

    def analyze_bulk(self, universe_candles: dict[str, list[OHLCVPoint]], mode: AnalysisMode) -> dict[str, TechnicalAnalysisResult]:
        self.logger.info("TECHNICAL | Start bulk analysis | mode=%s | symbols=%s", mode.value, len(universe_candles))
        
        if not universe_candles:
            return {}

        total_candles = sum(len(c) for c in universe_candles.values())
        print(f"MEMORY_AUDIT stage=before_analyze_bulk rss_mb={get_rss_mb():.2f} symbols={len(universe_candles)} candles={total_candles}")

        records = []
        for symbol, candles in universe_candles.items():
            for c in candles:
                records.append({
                    "timestamp": c.timestamp,
                    "symbol": symbol,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume
                })
        
        print(f"MEMORY_AUDIT stage=after_records_creation rss_mb={get_rss_mb():.2f} symbols={len(universe_candles)} candles={total_candles}")

        frame = pd.DataFrame(records)
        print(f"MEMORY_AUDIT stage=after_frame_creation rss_mb={get_rss_mb():.2f} symbols={len(universe_candles)} candles={total_candles}")

        if frame.empty:
            return {}

        frame.set_index(["timestamp", "symbol"], inplace=True)
        frame.sort_index(inplace=True)

        close_unstack = frame["close"].unstack(level="symbol")
        high_unstack = frame["high"].unstack(level="symbol")
        low_unstack = frame["low"].unstack(level="symbol")
        volume_unstack = frame["volume"].unstack(level="symbol")

        results: dict[str, TechnicalAnalysisResult] = {}

        if mode == AnalysisMode.intraday:
            ema_9_unstack = close_unstack.ewm(span=9, adjust=False).mean()
            ema_20_unstack = close_unstack.ewm(span=20, adjust=False).mean()

            delta = close_unstack.diff()
            gain = delta.where(delta > 0, 0.0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss
            rsi_14_unstack = 100.0 - (100.0 / (1.0 + rs))

            ema_12 = close_unstack.ewm(span=12, adjust=False).mean()
            ema_26 = close_unstack.ewm(span=26, adjust=False).mean()
            macd_unstack = ema_12 - ema_26
            macd_signal_unstack = macd_unstack.ewm(span=9, adjust=False).mean()

            typical_price = (high_unstack + low_unstack + close_unstack) / 3
            vwap_unstack = (typical_price * volume_unstack).rolling(window=14).sum() / volume_unstack.rolling(window=14).sum()

            avg_vol_short = volume_unstack.tail(5).mean()
            avg_vol_long = volume_unstack.tail(20).mean()

            last_close = close_unstack.iloc[-1]

            for symbol in close_unstack.columns:
                lc = float(last_close[symbol])
                ema_9 = float(ema_9_unstack[symbol].iloc[-1])
                ema_20 = float(ema_20_unstack[symbol].iloc[-1])
                rsi_14 = float(rsi_14_unstack[symbol].iloc[-1])
                macd_val = float(macd_unstack[symbol].iloc[-1])
                macd_sig = float(macd_signal_unstack[symbol].iloc[-1])
                vwap = float(vwap_unstack[symbol].iloc[-1])
                
                vol_trend = "expanding" if float(avg_vol_short[symbol]) > float(avg_vol_long[symbol]) else "stable"
                close_above_vwap = bool(lc > vwap)
                
                score = 0.0
                score += 20 if close_above_vwap else 0
                score += 20 if ema_9 > ema_20 else 0
                score += 15 if macd_val > macd_sig else 0
                score += 15 if 52 <= rsi_14 <= 72 else 8 if rsi_14 >= 45 else 0
                score += 15 if vol_trend == "expanding" else 5
                score += 15 if lc > ema_9 else 0
                score = round(min(score, 100.0), 2)
                signal = "bullish" if score >= 68 else "neutral" if score >= 48 else "bearish"

                indicators = {
                    "vwap": round(vwap, 2),
                    "ema_9": round(ema_9, 2),
                    "ema_20": round(ema_20, 2),
                    "rsi_14": round(rsi_14, 2),
                    "macd": round(macd_val, 4),
                    "macd_signal": round(macd_sig, 4),
                    "volume_trend": vol_trend,
                    "close_above_vwap": close_above_vwap,
                }
                self._log_analysis_decision(symbol, mode, indicators, score, signal)
                summary = f"{symbol} shows a {signal} {mode.value} setup with a technical score of {score}. The score blends trend, momentum, volume, and structure checks from the technical engine."
                results[symbol] = TechnicalAnalysisResult(mode=mode, signal=signal, score=score, indicators=indicators, summary=summary)

            print(f"MEMORY_AUDIT stage=after_results_generation rss_mb={get_rss_mb():.2f} symbols={len(results)} candles={total_candles}")
            return results

        # Swing Mode Vectorized - GroupBy implementation
        grouped = frame.groupby(level="symbol")
        
        def calc_rsi(x):
            delta = x.diff()
            gain = delta.where(delta > 0, 0.0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss
            return 100.0 - (100.0 / (1.0 + rs))

        def calc_macd(x):
            ema_12 = x.ewm(span=12, adjust=False).mean()
            ema_26 = x.ewm(span=26, adjust=False).mean()
            return ema_12 - ema_26

        ema_20_series = grouped["close"].transform(lambda x: x.ewm(span=20, adjust=False).mean())
        sma_20_series = grouped["close"].transform(lambda x: x.rolling(window=20).mean())
        sma_30_series = grouped["close"].transform(lambda x: x.rolling(window=30).mean())
        sma_50_series = grouped["close"].transform(lambda x: x.rolling(window=50).mean())
        sma_100_series = grouped["close"].transform(lambda x: x.rolling(window=100).mean())
        sma_200_series = grouped["close"].transform(lambda x: x.rolling(window=200).mean())

        rsi_14_series = grouped["close"].transform(calc_rsi)
        
        macd_series = grouped["close"].transform(calc_macd)
        macd_signal_series = grouped["close"].transform(lambda x: calc_macd(x).ewm(span=9, adjust=False).mean())

        support_series = grouped["low"].transform(lambda x: x.rolling(window=20).min())
        resistance_series = grouped["high"].transform(lambda x: x.rolling(window=20).max())

        final_supertrend = grouped.apply(lambda f: self._calculate_supertrend(f).iloc[-1], include_groups=False)

        df_indicators = pd.DataFrame({
            "ema_20": ema_20_series,
            "sma_20": sma_20_series,
            "sma_30": sma_30_series,
            "sma_50": sma_50_series,
            "sma_100": sma_100_series,
            "sma_200": sma_200_series,
            "rsi_14": rsi_14_series,
            "macd": macd_series,
            "macd_signal": macd_signal_series,
            "support": support_series,
            "resistance": resistance_series,
        })
        
        print(f"MEMORY_AUDIT stage=after_indicator_calculations rss_mb={get_rss_mb():.2f} symbols={len(universe_candles)} candles={total_candles}")

        last_inds = df_indicators.groupby(level="symbol").last()
        sma_20_prev_df = sma_20_series.groupby(level="symbol").nth(-20)

        for symbol in universe_candles.keys():
            if symbol not in last_inds.index:
                continue
                
            sym_candles = universe_candles[symbol]
            if len(sym_candles) < 20:
                continue

            inds = last_inds.loc[symbol]
            lc = float(sym_candles[-1].close)
            
            ema_20 = float(inds["ema_20"]) if not pd.isna(inds["ema_20"]) else 0.0
            sma_20 = float(inds["sma_20"]) if not pd.isna(inds["sma_20"]) else 0.0
            sma_30 = float(inds["sma_30"]) if not pd.isna(inds["sma_30"]) else 0.0
            sma_50 = float(inds["sma_50"]) if not pd.isna(inds["sma_50"]) else 0.0
            sma_100 = float(inds["sma_100"]) if not pd.isna(inds["sma_100"]) else 0.0
            sma_200 = float(inds["sma_200"]) if not pd.isna(inds["sma_200"]) else 0.0
            rsi_14 = float(inds["rsi_14"]) if not pd.isna(inds["rsi_14"]) else 0.0
            macd_value = float(inds["macd"]) if not pd.isna(inds["macd"]) else 0.0
            macd_signal = float(inds["macd_signal"]) if not pd.isna(inds["macd_signal"]) else 0.0
            support = float(inds["support"]) if not pd.isna(inds["support"]) else 0.0
            resistance = float(inds["resistance"]) if not pd.isna(inds["resistance"]) else 0.0
            
            supertrend_point = final_supertrend.loc[symbol] if symbol in final_supertrend.index else None
            if supertrend_point is None:
                continue

            sma_20_prev = float(sma_20_prev_df.loc[symbol]) if symbol in sma_20_prev_df.index and not pd.isna(sma_20_prev_df.loc[symbol]) else 0.0

            prev_1 = {"high": float(sym_candles[-2].high), "low": float(sym_candles[-2].low), "volume": float(sym_candles[-2].volume)}
            prev_2 = {"high": float(sym_candles[-3].high), "low": float(sym_candles[-3].low)}
            prev_3 = {"high": float(sym_candles[-4].high), "low": float(sym_candles[-4].low)}
            prev_4 = {"high": float(sym_candles[-5].high), "low": float(sym_candles[-5].low)}
            prev_5 = {"high": float(sym_candles[-6].high), "low": float(sym_candles[-6].low)}
            latest = {"high": float(sym_candles[-1].high), "low": float(sym_candles[-1].low), "volume": float(sym_candles[-1].volume), "open": float(sym_candles[-1].open), "close": lc}

            close_above_ema20 = bool(lc > ema_20)
            supertrend_positive = bool(supertrend_point.direction_up and lc >= supertrend_point.value)
            macd_positive = bool(macd_value > macd_signal)
            sma_uptrend_20d = bool(sma_20 > sma_20_prev)
            hh_hl_2d = bool(prev_1["high"] > prev_2["high"] and prev_1["low"] > prev_2["low"])
            hh_hl_3d = bool(prev_1["high"] > prev_3["high"] and prev_1["low"] > prev_3["low"])
            hh_hl_4d = bool(prev_1["high"] > prev_4["high"] and prev_1["low"] > prev_4["low"])
            latest_confirms_5d_structure = bool(latest["high"] > prev_1["high"] and prev_1["low"] > prev_5["low"])
            hammer = self._is_hammer(pd.Series(latest))
            gravestone_doji = self._is_gravestone_doji(pd.Series(latest))
            hammer_or_gravestone = bool(hammer or gravestone_doji)
            volume_above_50000 = bool(latest["volume"] > 50000)
            volume_above_previous_day = bool(latest["volume"] > prev_1["volume"])
            price_above_100 = bool(lc > 100)
            price_below_500000 = bool(lc < 500000)
            rsi_supportive = bool(rsi_14 >= 50)
            rsi_in_buy_zone = bool(55 <= rsi_14 <= 68)
            volume_supportive = bool(volume_above_50000 and price_above_100 and price_below_500000)
            core_trend_filter_pass = bool(close_above_ema20 and supertrend_positive)
            core_momentum_filter_pass = bool(macd_positive and rsi_supportive)
            basic_liquidity_filter_pass = bool(volume_supportive)
            
            structure_score = sum([hh_hl_2d, hh_hl_3d, hh_hl_4d, latest_confirms_5d_structure])
            structure_supportive = bool(structure_score >= 2)
            higher_timeframe_trend = "uptrend" if lc > sma_50 and sma_20 > sma_50 else "sideways" if lc > sma_50 else "downtrend"

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

            hard_filters_pass = bool(core_trend_filter_pass and core_momentum_filter_pass and basic_liquidity_filter_pass)
            signal = "bullish" if hard_filters_pass and score >= 72 else "neutral" if hard_filters_pass and score >= 52 else "bearish"

            indicators = {
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
            }
            self._log_analysis_decision(symbol, mode, indicators, score, signal)
            summary = f"{symbol} shows a {signal} {mode.value} setup with a technical score of {score}. The score blends trend, momentum, volume, and structure checks from the technical engine."
            results[symbol] = TechnicalAnalysisResult(mode=mode, signal=signal, score=score, indicators=indicators, summary=summary)

        print(f"MEMORY_AUDIT stage=after_results_generation rss_mb={get_rss_mb():.2f} symbols={len(results)} candles={total_candles}")
        return results

    def analyze_bulk_from_frame(self, frame: pd.DataFrame, mode: AnalysisMode) -> dict[str, TechnicalAnalysisResult]:
        """Memory-optimized bulk analysis that accepts a pre-built multi-index DataFrame.
        
        The frame must have a MultiIndex of (timestamp, symbol) and columns:
        open, high, low, close, volume.
        
        This eliminates the OHLCVPoint → records list → DataFrame conversion
        that previously caused ~280 MB of redundant memory allocation.
        """
        self.logger.info("TECHNICAL | Start bulk analysis (frame) | mode=%s | rows=%s", mode.value, len(frame))

        if frame.empty:
            return {}

        total_candles = len(frame)
        print(f"MEMORY_AUDIT stage=before_analyze_bulk rss_mb={get_rss_mb():.2f} rows={total_candles}")

        # Frame is already multi-indexed and sorted by caller
        results: dict[str, TechnicalAnalysisResult] = {}

        if mode == AnalysisMode.intraday:
            close_unstack = frame["close"].unstack(level="symbol")
            high_unstack = frame["high"].unstack(level="symbol")
            low_unstack = frame["low"].unstack(level="symbol")
            volume_unstack = frame["volume"].unstack(level="symbol")

            ema_9_unstack = close_unstack.ewm(span=9, adjust=False).mean()
            ema_20_unstack = close_unstack.ewm(span=20, adjust=False).mean()

            delta = close_unstack.diff()
            gain = delta.where(delta > 0, 0.0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss
            rsi_14_unstack = 100.0 - (100.0 / (1.0 + rs))

            ema_12 = close_unstack.ewm(span=12, adjust=False).mean()
            ema_26 = close_unstack.ewm(span=26, adjust=False).mean()
            macd_unstack = ema_12 - ema_26
            macd_signal_unstack = macd_unstack.ewm(span=9, adjust=False).mean()

            typical_price = (high_unstack + low_unstack + close_unstack) / 3
            vwap_unstack = (typical_price * volume_unstack).rolling(window=14).sum() / volume_unstack.rolling(window=14).sum()

            avg_vol_short = volume_unstack.tail(5).mean()
            avg_vol_long = volume_unstack.tail(20).mean()

            last_close = close_unstack.iloc[-1]

            for symbol in close_unstack.columns:
                lc = float(last_close[symbol])
                ema_9 = float(ema_9_unstack[symbol].iloc[-1])
                ema_20 = float(ema_20_unstack[symbol].iloc[-1])
                rsi_14 = float(rsi_14_unstack[symbol].iloc[-1])
                macd_val = float(macd_unstack[symbol].iloc[-1])
                macd_sig = float(macd_signal_unstack[symbol].iloc[-1])
                vwap = float(vwap_unstack[symbol].iloc[-1])

                vol_trend = "expanding" if float(avg_vol_short[symbol]) > float(avg_vol_long[symbol]) else "stable"
                close_above_vwap = bool(lc > vwap)

                score = 0.0
                score += 20 if close_above_vwap else 0
                score += 20 if ema_9 > ema_20 else 0
                score += 15 if macd_val > macd_sig else 0
                score += 15 if 52 <= rsi_14 <= 72 else 8 if rsi_14 >= 45 else 0
                score += 15 if vol_trend == "expanding" else 5
                score += 15 if lc > ema_9 else 0
                score = round(min(score, 100.0), 2)
                signal = "bullish" if score >= 68 else "neutral" if score >= 48 else "bearish"

                indicators = {
                    "vwap": round(vwap, 2),
                    "ema_9": round(ema_9, 2),
                    "ema_20": round(ema_20, 2),
                    "rsi_14": round(rsi_14, 2),
                    "macd": round(macd_val, 4),
                    "macd_signal": round(macd_sig, 4),
                    "volume_trend": vol_trend,
                    "close_above_vwap": close_above_vwap,
                }
                self._log_analysis_decision(symbol, mode, indicators, score, signal)
                summary = f"{symbol} shows a {signal} {mode.value} setup with a technical score of {score}. The score blends trend, momentum, volume, and structure checks from the technical engine."
                results[symbol] = TechnicalAnalysisResult(mode=mode, signal=signal, score=score, indicators=indicators, summary=summary)

            print(f"MEMORY_AUDIT stage=after_results_generation rss_mb={get_rss_mb():.2f} symbols={len(results)} candles={total_candles}")
            return results

        # Swing Mode Vectorized - GroupBy implementation
        grouped = frame.groupby(level="symbol")

        def calc_rsi(x):
            delta = x.diff()
            gain = delta.where(delta > 0, 0.0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss
            return 100.0 - (100.0 / (1.0 + rs))

        def calc_macd(x):
            ema_12 = x.ewm(span=12, adjust=False).mean()
            ema_26 = x.ewm(span=26, adjust=False).mean()
            return ema_12 - ema_26

        ema_20_series = grouped["close"].transform(lambda x: x.ewm(span=20, adjust=False).mean())
        sma_20_series = grouped["close"].transform(lambda x: x.rolling(window=20).mean())
        sma_30_series = grouped["close"].transform(lambda x: x.rolling(window=30).mean())
        sma_50_series = grouped["close"].transform(lambda x: x.rolling(window=50).mean())
        sma_100_series = grouped["close"].transform(lambda x: x.rolling(window=100).mean())
        sma_200_series = grouped["close"].transform(lambda x: x.rolling(window=200).mean())

        rsi_14_series = grouped["close"].transform(calc_rsi)

        macd_series = grouped["close"].transform(calc_macd)
        macd_signal_series = grouped["close"].transform(lambda x: calc_macd(x).ewm(span=9, adjust=False).mean())

        support_series = grouped["low"].transform(lambda x: x.rolling(window=20).min())
        resistance_series = grouped["high"].transform(lambda x: x.rolling(window=20).max())

        final_supertrend = grouped.apply(lambda f: self._calculate_supertrend(f).iloc[-1], include_groups=False)

        df_indicators = pd.DataFrame({
            "ema_20": ema_20_series,
            "sma_20": sma_20_series,
            "sma_30": sma_30_series,
            "sma_50": sma_50_series,
            "sma_100": sma_100_series,
            "sma_200": sma_200_series,
            "rsi_14": rsi_14_series,
            "macd": macd_series,
            "macd_signal": macd_signal_series,
            "support": support_series,
            "resistance": resistance_series,
        })

        print(f"MEMORY_AUDIT stage=after_indicator_calculations rss_mb={get_rss_mb():.2f} rows={total_candles}")

        last_inds = df_indicators.groupby(level="symbol").last()
        sma_20_prev_df = sma_20_series.groupby(level="symbol").nth(-20)

        # Get tail candle data directly from the frame for scoring
        for symbol in frame.index.get_level_values("symbol").unique():
            if symbol not in last_inds.index:
                continue

            sym_data = frame.loc[(slice(None), symbol), :]
            if len(sym_data) < 20:
                continue

            inds = last_inds.loc[symbol]
            lc = float(sym_data["close"].iloc[-1])

            ema_20 = float(inds["ema_20"]) if not pd.isna(inds["ema_20"]) else 0.0
            sma_20 = float(inds["sma_20"]) if not pd.isna(inds["sma_20"]) else 0.0
            sma_30 = float(inds["sma_30"]) if not pd.isna(inds["sma_30"]) else 0.0
            sma_50 = float(inds["sma_50"]) if not pd.isna(inds["sma_50"]) else 0.0
            sma_100 = float(inds["sma_100"]) if not pd.isna(inds["sma_100"]) else 0.0
            sma_200 = float(inds["sma_200"]) if not pd.isna(inds["sma_200"]) else 0.0
            rsi_14 = float(inds["rsi_14"]) if not pd.isna(inds["rsi_14"]) else 0.0
            macd_value = float(inds["macd"]) if not pd.isna(inds["macd"]) else 0.0
            macd_signal = float(inds["macd_signal"]) if not pd.isna(inds["macd_signal"]) else 0.0
            support = float(inds["support"]) if not pd.isna(inds["support"]) else 0.0
            resistance = float(inds["resistance"]) if not pd.isna(inds["resistance"]) else 0.0

            supertrend_point = final_supertrend.loc[symbol] if symbol in final_supertrend.index else None
            if supertrend_point is None:
                continue

            sma_20_prev = float(sma_20_prev_df.loc[symbol]) if symbol in sma_20_prev_df.index and not pd.isna(sma_20_prev_df.loc[symbol]) else 0.0

            # Read tail candle values directly from DataFrame columns
            prev_1 = {"high": float(sym_data["high"].iloc[-2]), "low": float(sym_data["low"].iloc[-2]), "volume": float(sym_data["volume"].iloc[-2])}
            prev_2 = {"high": float(sym_data["high"].iloc[-3]), "low": float(sym_data["low"].iloc[-3])}
            prev_3 = {"high": float(sym_data["high"].iloc[-4]), "low": float(sym_data["low"].iloc[-4])}
            prev_4 = {"high": float(sym_data["high"].iloc[-5]), "low": float(sym_data["low"].iloc[-5])}
            prev_5 = {"high": float(sym_data["high"].iloc[-6]), "low": float(sym_data["low"].iloc[-6])}
            latest = {"high": float(sym_data["high"].iloc[-1]), "low": float(sym_data["low"].iloc[-1]), "volume": float(sym_data["volume"].iloc[-1]), "open": float(sym_data["open"].iloc[-1]), "close": lc}

            close_above_ema20 = bool(lc > ema_20)
            supertrend_positive = bool(supertrend_point.direction_up and lc >= supertrend_point.value)
            macd_positive = bool(macd_value > macd_signal)
            sma_uptrend_20d = bool(sma_20 > sma_20_prev)
            hh_hl_2d = bool(prev_1["high"] > prev_2["high"] and prev_1["low"] > prev_2["low"])
            hh_hl_3d = bool(prev_1["high"] > prev_3["high"] and prev_1["low"] > prev_3["low"])
            hh_hl_4d = bool(prev_1["high"] > prev_4["high"] and prev_1["low"] > prev_4["low"])
            latest_confirms_5d_structure = bool(latest["high"] > prev_1["high"] and prev_1["low"] > prev_5["low"])
            hammer = self._is_hammer(pd.Series(latest))
            gravestone_doji = self._is_gravestone_doji(pd.Series(latest))
            hammer_or_gravestone = bool(hammer or gravestone_doji)
            volume_above_50000 = bool(latest["volume"] > 50000)
            volume_above_previous_day = bool(latest["volume"] > prev_1["volume"])
            price_above_100 = bool(lc > 100)
            price_below_500000 = bool(lc < 500000)
            rsi_supportive = bool(rsi_14 >= 50)
            rsi_in_buy_zone = bool(55 <= rsi_14 <= 68)
            volume_supportive = bool(volume_above_50000 and price_above_100 and price_below_500000)
            core_trend_filter_pass = bool(close_above_ema20 and supertrend_positive)
            core_momentum_filter_pass = bool(macd_positive and rsi_supportive)
            basic_liquidity_filter_pass = bool(volume_supportive)

            structure_score = sum([hh_hl_2d, hh_hl_3d, hh_hl_4d, latest_confirms_5d_structure])
            structure_supportive = bool(structure_score >= 2)
            higher_timeframe_trend = "uptrend" if lc > sma_50 and sma_20 > sma_50 else "sideways" if lc > sma_50 else "downtrend"

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

            hard_filters_pass = bool(core_trend_filter_pass and core_momentum_filter_pass and basic_liquidity_filter_pass)
            signal = "bullish" if hard_filters_pass and score >= 72 else "neutral" if hard_filters_pass and score >= 52 else "bearish"

            indicators = {
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
            }
            self._log_analysis_decision(symbol, mode, indicators, score, signal)
            summary = f"{symbol} shows a {signal} {mode.value} setup with a technical score of {score}. The score blends trend, momentum, volume, and structure checks from the technical engine."
            results[symbol] = TechnicalAnalysisResult(mode=mode, signal=signal, score=score, indicators=indicators, summary=summary)

        print(f"MEMORY_AUDIT stage=after_results_generation rss_mb={get_rss_mb():.2f} symbols={len(results)} candles={total_candles}")
        return results

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
