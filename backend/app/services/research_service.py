"""Swing Trading Research engine.

Builds a single research payload from existing OHLCV, technicals, backtests,
fundamentals, and news — without inventing missing institutional data.
"""
from __future__ import annotations

import math
from statistics import mean, median
from typing import Any

import pandas as pd

from ..utils import get_logger
from .llm_service import LLMService
from .research_cache import research_cache

logger = get_logger("app.research")

NA = "Data not available."


def _safe_float(value: Any, digits: int | None = 4) -> float | None:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        num = float(value)
        if digits is None:
            return num
        return round(num, digits)
    except Exception:
        return None


def _pct(part: float | None, whole: float | None) -> float | None:
    if part is None or whole is None or whole == 0:
        return None
    return round((part / whole) * 100.0, 2)


class ResearchService:
    """Compute institutional-style swing research from existing market data."""

    def __init__(self) -> None:
        self.llm = LLMService()

    def build(
        self,
        symbol: str,
        item: Any,
        ohlcv: list,
        company_info: dict | None = None,
        tech_extra: dict | None = None,
        backtest_extra: dict | None = None,
    ) -> dict[str, Any]:
        symbol = symbol.strip().upper()
        company_info = company_info or {}
        tech_extra = tech_extra or {}
        backtest_extra = backtest_extra or {}

        last_ts = None
        last_close = None
        if ohlcv:
            last = ohlcv[-1]
            last_ts = str(getattr(last, "timestamp", None) or (last.get("timestamp") if isinstance(last, dict) else None))
            last_close = float(getattr(last, "close", None) or (last.get("close") if isinstance(last, dict) else 0) or 0)

        fp = research_cache.fingerprint(symbol, last_ts, len(ohlcv or []), last_close)
        cache_key = f"research:{symbol}:{fp}"
        cached = research_cache.get(cache_key)
        if cached is not None:
            logger.info("RESEARCH_CACHE_HIT | symbol=%s | key=%s", symbol, cache_key)
            return cached

        df = self._to_frame(ohlcv)
        indicators = self._compute_indicators(df)
        trend = self._trend_analysis(df, indicators)
        supply_demand = self._supply_demand(df)
        momentum = self._momentum_analysis(df, indicators)
        volume = self._volume_analysis(df, indicators)
        volatility = self._volatility_analysis(df, indicators, tech_extra)
        price_action = self._price_action(df)
        patterns = self._pattern_detection(df)
        multi_tf = self._multi_timeframe(df, item, tech_extra)
        risk = self._risk_analysis(item, indicators, df)
        holding = self._holding_period(risk, backtest_extra, indicators)
        backtesting = self._backtest_windows(backtest_extra, item)
        similar = self._similar_setups(backtest_extra, item)
        swing_score = self._swing_score(trend, momentum, volume, volatility, risk, item, indicators)
        checklist = self._checklist(trend, momentum, volume, patterns, risk, swing_score, item)
        fundamentals = self._fundamentals(item, company_info)
        institutional = self._institutional(fundamentals)
        news = self._news_analysis(item)
        sentiment = self._sentiment_analysis(item, news)
        ai_block = self._ai_research_and_confidence(
            symbol=symbol,
            company_info=company_info,
            trend=trend,
            momentum=momentum,
            volume=volume,
            swing_score=swing_score,
            risk=risk,
            item=item,
            fundamentals=fundamentals,
            fingerprint=fp,
        )

        payload = {
            "symbol": symbol,
            "data_fingerprint": fp,
            "generated_from_cache": False,
            "ai_research_summary": ai_block["summary"],
            "swing_score": swing_score,
            "trend_analysis": trend,
            "supply_demand": supply_demand,
            "momentum_analysis": momentum,
            "volume_analysis": volume,
            "volatility": volatility,
            "price_action": price_action,
            "pattern_detection": patterns,
            "multi_timeframe": multi_tf,
            "risk_analysis": risk,
            "holding_period": holding,
            "backtesting": backtesting,
            "historical_similar_setups": similar,
            "ai_confidence": ai_block["confidence"],
            "news_analysis": news,
            "sentiment_analysis": sentiment,
            "fundamental_analysis": fundamentals,
            "institutional_activity": institutional,
            "checklist": checklist,
            "llm_insights": ai_block["insights"],
            "disclaimer": (
                "Advisory research only. Metrics are derived from available market data. "
                "Missing fields are reported as 'Data not available.' Numbers are never invented."
            ),
        }
        research_cache.set(cache_key, payload)
        return payload

    # ------------------------------------------------------------------ frame
    def _to_frame(self, ohlcv: list) -> pd.DataFrame:
        if not ohlcv:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        rows = []
        for p in ohlcv:
            if hasattr(p, "close"):
                rows.append(
                    {
                        "timestamp": pd.to_datetime(p.timestamp),
                        "open": float(p.open),
                        "high": float(p.high),
                        "low": float(p.low),
                        "close": float(p.close),
                        "volume": int(p.volume or 0),
                    }
                )
            elif isinstance(p, dict):
                rows.append(
                    {
                        "timestamp": pd.to_datetime(p.get("timestamp")),
                        "open": float(p.get("open", 0)),
                        "high": float(p.get("high", 0)),
                        "low": float(p.get("low", 0)),
                        "close": float(p.get("close", 0)),
                        "volume": int(p.get("volume") or 0),
                    }
                )
        df = pd.DataFrame(rows).dropna(subset=["close"])
        if not df.empty:
            df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def _compute_indicators(self, df: pd.DataFrame) -> dict[str, Any]:
        empty: dict[str, Any] = {}
        if df.empty or len(df) < 5:
            return empty
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        def ema(span: int) -> float | None:
            if len(close) < span:
                return None
            return _safe_float(close.ewm(span=span, adjust=False).mean().iloc[-1])

        ema20 = ema(20)
        ema50 = ema(50)
        ema100 = ema(100)
        ema200 = ema(200)

        # RSI 14
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi_series = (100 - (100 / (1 + rs))).astype(float)
        rsi = _safe_float(rsi_series.iloc[-1], 2)

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - macd_signal
        macd = _safe_float(macd_line.iloc[-1])
        macd_sig = _safe_float(macd_signal.iloc[-1])
        macd_h = _safe_float(macd_hist.iloc[-1])

        # Stochastic RSI
        stoch_rsi = None
        if rsi is not None and len(close) >= 28:
            rsi_min = rsi_series.rolling(14).min()
            rsi_max = rsi_series.rolling(14).max()
            denom = (rsi_max - rsi_min).replace(0, float("nan"))
            stoch_rsi = _safe_float(((rsi_series - rsi_min) / denom).iloc[-1] * 100, 2)

        # CCI 20
        cci = None
        if len(df) >= 20:
            tp = (high + low + close) / 3
            sma_tp = tp.rolling(20).mean()
            mad = tp.rolling(20).apply(lambda x: float(abs(x - x.mean()).mean()), raw=True)
            cci_series = (tp - sma_tp) / (0.015 * mad.replace(0, float("nan")))
            cci = _safe_float(cci_series.iloc[-1], 2)

        # ROC 12
        roc = None
        if len(close) > 12:
            roc = _safe_float(((close.iloc[-1] / close.iloc[-13]) - 1) * 100, 2)

        # Momentum 10
        mom = None
        if len(close) > 10:
            mom = _safe_float(close.iloc[-1] - close.iloc[-11], 2)

        # ATR 14
        atr = None
        atr_pct = None
        if len(df) >= 15:
            prev_close = close.shift(1)
            tr = pd.concat(
                [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
                axis=1,
            ).max(axis=1)
            atr = _safe_float(tr.rolling(14).mean().iloc[-1])
            if atr and close.iloc[-1]:
                atr_pct = _safe_float((atr / float(close.iloc[-1])) * 100, 3)

        # Bollinger
        bb_upper = bb_mid = bb_lower = bb_width = None
        if len(close) >= 20:
            mid = close.rolling(20).mean()
            std = close.rolling(20).std()
            upper = mid + 2 * std
            lower = mid - 2 * std
            bb_mid = _safe_float(mid.iloc[-1])
            bb_upper = _safe_float(upper.iloc[-1])
            bb_lower = _safe_float(lower.iloc[-1])
            if bb_mid and bb_mid != 0 and bb_upper is not None and bb_lower is not None:
                bb_width = _safe_float(((bb_upper - bb_lower) / bb_mid) * 100, 3)

        # ADX 14 (simplified)
        adx = None
        if len(df) >= 30:
            up_move = high.diff()
            down_move = -low.diff()
            plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
            minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
            prev_c = close.shift(1)
            tr = pd.concat([(high - low), (high - prev_c).abs(), (low - prev_c).abs()], axis=1).max(axis=1)
            atr14 = tr.ewm(alpha=1 / 14, adjust=False).mean()
            plus_di = 100 * (plus_dm.ewm(alpha=1 / 14, adjust=False).mean() / atr14.replace(0, float("nan")))
            minus_di = 100 * (minus_dm.ewm(alpha=1 / 14, adjust=False).mean() / atr14.replace(0, float("nan")))
            dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))) * 100
            adx = _safe_float(dx.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1], 2)

        # OBV
        obv = None
        obv_trend = NA
        if len(df) >= 5:
            direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
            obv_series = (direction * volume).fillna(0).cumsum()
            obv = _safe_float(obv_series.iloc[-1], 0)
            if len(obv_series) >= 10:
                obv_trend = "rising" if obv_series.iloc[-1] > obv_series.iloc[-10] else "falling"

        avg_vol_20 = _safe_float(volume.tail(20).mean(), 0) if len(volume) else None
        cur_vol = int(volume.iloc[-1]) if len(volume) else None
        vol_ratio = None
        if cur_vol is not None and avg_vol_20:
            vol_ratio = _safe_float(cur_vol / avg_vol_20, 2)

        # Golden / death cross (50/200)
        golden = death = False
        if ema50 is not None and ema200 is not None and len(close) >= 201:
            ema50_s = close.ewm(span=50, adjust=False).mean()
            ema200_s = close.ewm(span=200, adjust=False).mean()
            prev_spread = float(ema50_s.iloc[-2] - ema200_s.iloc[-2])
            cur_spread = float(ema50_s.iloc[-1] - ema200_s.iloc[-1])
            golden = prev_spread <= 0 < cur_spread
            death = prev_spread >= 0 > cur_spread

        return {
            "close": _safe_float(close.iloc[-1]),
            "ema_20": ema20,
            "ema_50": ema50,
            "ema_100": ema100,
            "ema_200": ema200,
            "rsi": rsi,
            "macd": macd,
            "macd_signal": macd_sig,
            "macd_histogram": macd_h,
            "stochastic_rsi": stoch_rsi,
            "cci": cci,
            "roc": roc,
            "momentum": mom,
            "atr": atr,
            "atr_pct": atr_pct,
            "bb_upper": bb_upper,
            "bb_mid": bb_mid,
            "bb_lower": bb_lower,
            "bb_width": bb_width,
            "adx": adx,
            "obv": obv,
            "obv_trend": obv_trend,
            "current_volume": cur_vol,
            "average_volume": avg_vol_20,
            "volume_ratio": vol_ratio,
            "golden_cross": golden,
            "death_cross": death,
        }

    # --------------------------------------------------------------- sections
    def _trend_analysis(self, df: pd.DataFrame, ind: dict) -> dict[str, Any]:
        close = ind.get("close")
        e20, e50, e100, e200 = ind.get("ema_20"), ind.get("ema_50"), ind.get("ema_100"), ind.get("ema_200")
        adx = ind.get("adx")

        alignment = "mixed"
        if all(v is not None for v in (close, e20, e50)):
            if close > e20 > e50 and (e100 is None or e50 > e100) and (e200 is None or (e100 or e50) > e200):
                alignment = "bullish_stack"
            elif close < e20 < e50 and (e100 is None or e50 < e100):
                alignment = "bearish_stack"
            elif close > e20:
                alignment = "short_term_bullish"
            elif close < e20:
                alignment = "short_term_bearish"

        label = "Sideways"
        if alignment == "bullish_stack" and (adx or 0) >= 25:
            label = "Strong Bullish"
        elif alignment in ("bullish_stack", "short_term_bullish") and close and e20 and close > e20:
            label = "Bullish"
        elif alignment == "bearish_stack" and (adx or 0) >= 25:
            label = "Strong Bearish"
        elif alignment in ("bearish_stack", "short_term_bearish"):
            label = "Bearish"

        strength = "weak"
        if adx is not None:
            if adx >= 40:
                strength = "very_strong"
            elif adx >= 25:
                strength = "strong"
            elif adx >= 15:
                strength = "moderate"

        quality = "high" if alignment == "bullish_stack" and strength in ("strong", "very_strong") else (
            "medium" if label in ("Bullish", "Bearish") else "low"
        )

        return {
            "current_trend": label,
            "ema_20": e20,
            "ema_50": e50,
            "ema_100": e100 if e100 is not None else NA,
            "ema_200": e200 if e200 is not None else NA,
            "ema_alignment": alignment,
            "golden_cross": bool(ind.get("golden_cross")),
            "death_cross": bool(ind.get("death_cross")),
            "trend_strength": strength,
            "adx": adx if adx is not None else NA,
            "trend_quality": quality,
        }

    def _supply_demand(self, df: pd.DataFrame) -> dict[str, Any]:
        if df.empty or len(df) < 20:
            return {
                "demand_zones": [],
                "supply_zones": [],
                "support": NA,
                "resistance": NA,
                "breakout_areas": [],
                "breakdown_areas": [],
                "retest_levels": [],
                "liquidity_zones": [],
            }

        window = df.tail(60)
        recent = df.tail(20)
        support = _safe_float(recent["low"].min())
        resistance = _safe_float(recent["high"].max())
        swing_low = _safe_float(window["low"].nsmallest(3).mean())
        swing_high = _safe_float(window["high"].nlargest(3).mean())
        close = float(df["close"].iloc[-1])

        demand = []
        supply = []
        if swing_low is not None:
            demand.append({"zone_low": round(swing_low * 0.995, 2), "zone_high": round(swing_low * 1.005, 2), "label": "swing_demand"})
        if support is not None:
            demand.append({"zone_low": round(support * 0.998, 2), "zone_high": round(support * 1.002, 2), "label": "recent_support"})
        if swing_high is not None:
            supply.append({"zone_low": round(swing_high * 0.995, 2), "zone_high": round(swing_high * 1.005, 2), "label": "swing_supply"})
        if resistance is not None:
            supply.append({"zone_low": round(resistance * 0.998, 2), "zone_high": round(resistance * 1.002, 2), "label": "recent_resistance"})

        breakout = []
        breakdown = []
        if resistance and close > resistance:
            breakout.append({"level": resistance, "status": "broken_above"})
        if support and close < support:
            breakdown.append({"level": support, "status": "broken_below"})

        retest = []
        if resistance:
            retest.append(resistance)
        if support:
            retest.append(support)

        liquidity = []
        if support:
            liquidity.append({"level": support, "type": "buy_side_liquidity"})
        if resistance:
            liquidity.append({"level": resistance, "type": "sell_side_liquidity"})

        return {
            "demand_zones": demand,
            "supply_zones": supply,
            "support": support if support is not None else NA,
            "resistance": resistance if resistance is not None else NA,
            "breakout_areas": breakout,
            "breakdown_areas": breakdown,
            "retest_levels": retest,
            "liquidity_zones": liquidity,
        }

    def _momentum_analysis(self, df: pd.DataFrame, ind: dict) -> dict[str, Any]:
        rsi = ind.get("rsi")
        macd_h = ind.get("macd_histogram")
        roc = ind.get("roc")
        direction = "neutral"
        if macd_h is not None and macd_h > 0 and (rsi is None or rsi >= 50):
            direction = "bullish"
        elif macd_h is not None and macd_h < 0 and (rsi is None or rsi < 50):
            direction = "bearish"

        strength = "weak"
        if rsi is not None:
            if 55 <= rsi <= 70 and direction == "bullish":
                strength = "strong"
            elif 45 <= rsi < 55:
                strength = "moderate"
            elif rsi > 70 or rsi < 30:
                strength = "extreme"
            elif direction != "neutral":
                strength = "moderate"

        return {
            "rsi": rsi if rsi is not None else NA,
            "macd": ind.get("macd") if ind.get("macd") is not None else NA,
            "macd_signal": ind.get("macd_signal") if ind.get("macd_signal") is not None else NA,
            "macd_histogram": macd_h if macd_h is not None else NA,
            "stochastic_rsi": ind.get("stochastic_rsi") if ind.get("stochastic_rsi") is not None else NA,
            "cci": ind.get("cci") if ind.get("cci") is not None else NA,
            "momentum": ind.get("momentum") if ind.get("momentum") is not None else NA,
            "roc": roc if roc is not None else NA,
            "momentum_direction": direction,
            "momentum_strength": strength,
        }

    def _volume_analysis(self, df: pd.DataFrame, ind: dict) -> dict[str, Any]:
        ratio = ind.get("volume_ratio")
        breakout = bool(ratio is not None and ratio >= 1.5)
        accum = "neutral"
        if ind.get("obv_trend") == "rising" and (ratio or 0) >= 1.0:
            accum = "accumulation"
        elif ind.get("obv_trend") == "falling":
            accum = "distribution"

        vol_trend = "flat"
        if ratio is not None:
            if ratio >= 1.2:
                vol_trend = "expanding"
            elif ratio <= 0.8:
                vol_trend = "contracting"

        return {
            "current_volume": ind.get("current_volume") if ind.get("current_volume") is not None else NA,
            "average_volume": ind.get("average_volume") if ind.get("average_volume") is not None else NA,
            "volume_ratio": ratio if ratio is not None else NA,
            "delivery_pct": NA,  # NSE delivery % requires separate feed
            "volume_breakout": breakout,
            "obv": ind.get("obv") if ind.get("obv") is not None else NA,
            "volume_trend": vol_trend,
            "accumulation": accum == "accumulation",
            "distribution": accum == "distribution",
            "flow_label": accum,
        }

    def _volatility_analysis(self, df: pd.DataFrame, ind: dict, tech_extra: dict) -> dict[str, Any]:
        atr = ind.get("atr") or tech_extra.get("atr")
        atr_pct = ind.get("atr_pct") or tech_extra.get("atr_pct")
        bb_width = ind.get("bb_width")
        close = ind.get("close")

        vol_score = 50
        if atr_pct is not None:
            if atr_pct < 1:
                vol_score = 25
            elif atr_pct < 2:
                vol_score = 50
            elif atr_pct < 3.5:
                vol_score = 75
            else:
                vol_score = 90

        expected_range = None
        if atr is not None and close is not None:
            expected_range = {
                "low": round(close - atr, 2),
                "high": round(close + atr, 2),
                "atr": atr,
            }

        return {
            "atr": atr if atr is not None else NA,
            "atr_pct": atr_pct if atr_pct is not None else NA,
            "bollinger_bands": {
                "upper": ind.get("bb_upper") if ind.get("bb_upper") is not None else NA,
                "mid": ind.get("bb_mid") if ind.get("bb_mid") is not None else NA,
                "lower": ind.get("bb_lower") if ind.get("bb_lower") is not None else NA,
            },
            "band_width": bb_width if bb_width is not None else NA,
            "volatility_score": vol_score,
            "expected_swing_range": expected_range if expected_range else NA,
            "atr_class": tech_extra.get("atr_class") or (
                "low" if (atr_pct or 0) < 1 else "medium" if (atr_pct or 0) < 2 else "high"
            ),
        }

    def _price_action(self, df: pd.DataFrame) -> dict[str, Any]:
        flags = {
            "higher_high": False,
            "higher_low": False,
            "lower_high": False,
            "lower_low": False,
            "inside_candle": False,
            "outside_candle": False,
            "bullish_engulfing": False,
            "bearish_engulfing": False,
            "doji": False,
            "hammer": False,
            "morning_star": False,
            "evening_star": False,
            "gap_up": False,
            "gap_down": False,
        }
        if len(df) < 3:
            return flags

        c0, c1, c2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
        o, h, l, c = float(c0["open"]), float(c0["high"]), float(c0["low"]), float(c0["close"])
        po, ph, pl, pc = float(c1["open"]), float(c1["high"]), float(c1["low"]), float(c1["close"])
        body = abs(c - o)
        range_ = max(h - l, 1e-9)
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)

        flags["higher_high"] = h > ph and float(c2["high"]) < ph
        flags["higher_low"] = l > pl and float(c2["low"]) < pl
        flags["lower_high"] = h < ph and float(c2["high"]) > ph
        flags["lower_low"] = l < pl and float(c2["low"]) > pl
        flags["inside_candle"] = h <= ph and l >= pl
        flags["outside_candle"] = h >= ph and l <= pl
        flags["bullish_engulfing"] = c > o and pc < po and c >= po and o <= pc
        flags["bearish_engulfing"] = c < o and pc > po and c <= po and o >= pc
        flags["doji"] = body / range_ < 0.1
        flags["hammer"] = lower_wick >= body * 2 and upper_wick <= body * 0.5 and c >= o
        # Morning / evening star simplified 3-candle
        mid_body = abs(float(c1["close"]) - float(c1["open"]))
        flags["morning_star"] = (
            float(c2["close"]) < float(c2["open"])
            and mid_body / max(float(c1["high"]) - float(c1["low"]), 1e-9) < 0.3
            and c > o
            and c > (float(c2["open"]) + float(c2["close"])) / 2
        )
        flags["evening_star"] = (
            float(c2["close"]) > float(c2["open"])
            and mid_body / max(float(c1["high"]) - float(c1["low"]), 1e-9) < 0.3
            and c < o
            and c < (float(c2["open"]) + float(c2["close"])) / 2
        )
        flags["gap_up"] = l > ph
        flags["gap_down"] = h < pl
        return flags

    def _pattern_detection(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Heuristic pattern tags from price structure — confidence is indicative only."""
        results: list[dict[str, Any]] = []
        if len(df) < 40:
            return results

        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values
        n = len(df)
        last = float(closes[-1])
        support = float(min(lows[-20:]))
        resistance = float(max(highs[-20:]))
        mid = (support + resistance) / 2

        def add(name: str, conf: int, target: float | None, invalid: float | None) -> None:
            results.append(
                {
                    "pattern": name,
                    "confidence_pct": conf,
                    "target": round(target, 2) if target is not None else NA,
                    "invalidation": round(invalid, 2) if invalid is not None else NA,
                }
            )

        # Double bottom: two lows near each other with bounce
        left = float(min(lows[-40:-20]))
        right = float(min(lows[-20:]))
        if abs(left - right) / max(left, 1) < 0.02 and last > mid:
            add("Double Bottom", 62, resistance + (resistance - support) * 0.5, min(left, right) * 0.98)

        # Double top
        left_h = float(max(highs[-40:-20]))
        right_h = float(max(highs[-20:]))
        if abs(left_h - right_h) / max(left_h, 1) < 0.02 and last < mid:
            add("Double Top", 60, support - (resistance - support) * 0.5, max(left_h, right_h) * 1.02)

        # Ascending triangle: flat highs, rising lows
        recent_highs = highs[-15:]
        recent_lows = lows[-15:]
        if max(recent_highs) - min(recent_highs[-5:]) < (resistance - support) * 0.15:
            if recent_lows[-1] > recent_lows[0]:
                add("Ascending Triangle", 58, resistance * 1.03, support)

        # Descending triangle
        if max(recent_lows) - min(recent_lows[-5:]) < (resistance - support) * 0.15:
            if recent_highs[-1] < recent_highs[0]:
                add("Descending Triangle", 55, support * 0.97, resistance)

        # Rectangle / range
        if (resistance - support) / max(last, 1) < 0.08:
            add("Rectangle", 50, resistance, support)

        # Flag: strong move then consolidation
        move = (closes[-20] - closes[-40]) / max(closes[-40], 1) if n >= 40 else 0
        cons = (max(highs[-10:]) - min(lows[-10:])) / max(last, 1)
        if move > 0.08 and cons < 0.04:
            add("Flag", 57, last * (1 + move * 0.5), min(lows[-10:]))
        if move < -0.08 and cons < 0.04:
            add("Pennant", 52, last * (1 + move * 0.5), max(highs[-10:]))

        # Channel (rough slope consistency)
        x = list(range(20))
        y = list(closes[-20:])
        if len(y) == 20:
            x_mean = sum(x) / 20
            y_mean = sum(y) / 20
            num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
            den = sum((xi - x_mean) ** 2 for xi in x) or 1
            slope = num / den
            if abs(slope) > 0 and cons < 0.1:
                add("Channel", 48, last + slope * 10, support if slope > 0 else resistance)

        # Cup and handle / H&S / wedges / broadening — only if structure fits loosely
        left_min_i = int(lows[-50:-25].argmin()) if n >= 50 else 0
        right_min_i = int(lows[-25:].argmin()) if n >= 25 else 0
        if n >= 50 and abs(float(lows[-50:-25][left_min_i]) - float(lows[-25:][right_min_i])) / max(last, 1) < 0.03:
            if float(max(highs[-40:-10])) > last * 0.98:
                add("Cup and Handle", 45, resistance * 1.05, support)

        if not results:
            add("No clear classic pattern", 0, None, None)
        return results

    def _multi_timeframe(self, df: pd.DataFrame, item: Any, tech_extra: dict) -> dict[str, Any]:
        daily_signal = None
        try:
            techs = getattr(item, "technical", None) or []
            swing = next((t for t in techs if getattr(getattr(t, "mode", None), "value", None) == "swing"), None)
            daily_signal = getattr(swing or (techs[0] if techs else None), "signal", None)
        except Exception:
            daily_signal = None
        mtf = tech_extra.get("multi_timeframe") or {}
        weekly = mtf.get("weekly")

        monthly = None
        support_d = resistance_d = None
        if not df.empty:
            support_d = _safe_float(df["low"].tail(20).min())
            resistance_d = _safe_float(df["high"].tail(20).max())
            try:
                indexed = df.set_index("timestamp")
                try:
                    monthly_df = indexed.resample("ME").agg(
                        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
                    ).dropna()
                except ValueError:
                    monthly_df = indexed.resample("M").agg(
                        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
                    ).dropna()
                if len(monthly_df) >= 3:
                    monthly = "bullish" if float(monthly_df["close"].iloc[-1]) >= float(monthly_df["close"].iloc[-3]) else "bearish"
            except Exception:
                monthly = None

        def row(trend: Any, momentum: str, volume: str, support: Any, resistance: Any, signal: Any) -> dict:
            return {
                "trend": trend if trend is not None else NA,
                "momentum": momentum,
                "volume": volume,
                "support": support if support is not None else NA,
                "resistance": resistance if resistance is not None else NA,
                "signal": signal if signal is not None else NA,
            }

        vol_label = "expanding" if (not df.empty and len(df) > 5 and df["volume"].iloc[-1] > df["volume"].tail(20).mean()) else "mixed"
        return {
            "daily": row(daily_signal or mtf.get("daily"), "from_daily_indicators", vol_label, support_d, resistance_d, daily_signal),
            "weekly": row(weekly, NA if weekly is None else "aligned_with_price_vs_sma", NA, NA, NA, weekly),
            "monthly": row(monthly, NA, NA, NA, NA, monthly),
        }

    def _risk_analysis(self, item: Any, ind: dict, df: pd.DataFrame) -> dict[str, Any]:
        plan = None
        try:
            rec = getattr(item, "recommendation", None)
            plans = getattr(rec, "trade_plans", None) or []
            plan = next((p for p in plans if getattr(getattr(p, "mode", None), "value", None) == "swing"), None) or (plans[0] if plans else None)
        except Exception:
            plan = None

        close = ind.get("close")
        atr = ind.get("atr")
        if plan:
            entry = (float(plan.entry_low) + float(plan.entry_high)) / 2
            stop = float(plan.stop_loss)
            t1, t2 = float(plan.target_1), float(plan.target_2)
            t3 = float(plan.target_3) if getattr(plan, "target_3", None) is not None else (t2 + (t2 - t1) if t2 and t1 else None)
            rr = float(plan.risk_reward_ratio or 0)
        else:
            if close is None:
                return {
                    "suggested_entry": NA,
                    "stop_loss": NA,
                    "target_1": NA,
                    "target_2": NA,
                    "target_3": NA,
                    "risk_pct": NA,
                    "reward_pct": NA,
                    "risk_reward_ratio": NA,
                    "position_size": NA,
                    "capital_required": NA,
                }
            entry = close
            stop = close - (atr or close * 0.02)
            t1 = close + (atr or close * 0.02) * 1.5
            t2 = close + (atr or close * 0.02) * 2.5
            t3 = close + (atr or close * 0.02) * 3.5
            risk = abs(entry - stop)
            reward = abs(t1 - entry)
            rr = round(reward / risk, 2) if risk else 0

        risk_pct = _pct(abs(entry - stop), entry)
        reward_pct = _pct(abs(t1 - entry), entry)
        risk_amount = 5000.0
        risk_per_share = abs(entry - stop)
        position_size = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
        capital = round(position_size * entry, 2) if position_size else 0

        return {
            "suggested_entry": round(entry, 2),
            "stop_loss": round(stop, 2),
            "target_1": round(t1, 2),
            "target_2": round(t2, 2),
            "target_3": round(t3, 2) if t3 is not None else NA,
            "risk_pct": risk_pct if risk_pct is not None else NA,
            "reward_pct": reward_pct if reward_pct is not None else NA,
            "risk_reward_ratio": round(rr, 2) if rr is not None else NA,
            "position_size": position_size if position_size else NA,
            "capital_required": capital if capital else NA,
            "risk_amount_assumed": risk_amount,
        }

    def _holding_period(self, risk: dict, backtest_extra: dict, ind: dict) -> dict[str, Any]:
        atr_pct = ind.get("atr_pct") or 0
        rr = risk.get("risk_reward_ratio")
        # Heuristic expected holds for swing
        if isinstance(atr_pct, (int, float)) and atr_pct >= 2.5:
            expected = 5
        elif isinstance(atr_pct, (int, float)) and atr_pct >= 1.5:
            expected = 10
        else:
            expected = 20

        win = backtest_extra.get("win_rate")
        base_prob = float(win) if isinstance(win, (int, float)) else 50.0
        # Scale target probability by R:R quality
        if isinstance(rr, (int, float)) and rr >= 2:
            base_prob = min(85.0, base_prob + 5)
        elif isinstance(rr, (int, float)) and rr < 1.2:
            base_prob = max(20.0, base_prob - 10)

        return {
            "expected_holding_days": expected,
            "options": [
                {"days": 2, "probability_of_target": round(max(10, base_prob - 25), 1)},
                {"days": 5, "probability_of_target": round(max(15, base_prob - 10), 1)},
                {"days": 10, "probability_of_target": round(base_prob, 1)},
                {"days": 20, "probability_of_target": round(min(90, base_prob + 5), 1)},
            ],
            "note": "Probabilities are heuristic estimates from backtest win-rate and volatility — not guarantees.",
        }

    def _trade_stats(self, trades: list[dict], last_n: int | None = None) -> dict[str, Any]:
        if not trades:
            return {
                "signals": 0,
                "success_rate": NA,
                "average_return": NA,
                "average_loss": NA,
                "average_holding_days": NA,
                "maximum_drawdown": NA,
                "sharpe_ratio": NA,
                "profit_factor": NA,
            }
        subset = trades[-last_n:] if last_n else trades
        pnls = [float(t.get("pnl_percent", 0)) for t in subset]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        success = round(len(wins) / len(pnls) * 100, 2) if pnls else 0
        avg_ret = round(mean(pnls), 2) if pnls else 0
        avg_loss = round(mean(losses), 2) if losses else 0
        # holding days
        holds = []
        for t in subset:
            try:
                entry = pd.to_datetime(t.get("entry_date"))
                exit_ = pd.to_datetime(t.get("exit_date"))
                holds.append(max(0, (exit_ - entry).days))
            except Exception:
                pass
        avg_hold = round(mean(holds), 1) if holds else NA
        # equity path drawdown
        equity = 100.0
        peak = 100.0
        max_dd = 0.0
        for p in pnls:
            equity *= 1 + p / 100
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100 if peak else 0)
        sharpe = 0.0
        if len(pnls) > 1:
            try:
                import statistics

                m = statistics.mean(pnls)
                s = statistics.stdev(pnls)
                if s > 0:
                    sharpe = round((m / s) * math.sqrt(len(pnls)), 3)
            except Exception:
                pass
        pf = round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else (round(sum(wins), 2) if wins else 0)
        return {
            "signals": len(subset),
            "success_rate": success,
            "average_return": avg_ret,
            "average_loss": avg_loss,
            "average_holding_days": avg_hold,
            "maximum_drawdown": round(max_dd, 2),
            "sharpe_ratio": sharpe,
            "profit_factor": pf,
        }

    def _backtest_windows(self, backtest_extra: dict, item: Any) -> dict[str, Any]:
        trades = backtest_extra.get("trades") or []
        if not trades:
            try:
                bts = getattr(item, "backtests", None) or []
                bt = next((b for b in bts if getattr(getattr(b, "mode", None), "value", None) == "swing"), None) or (bts[0] if bts else None)
                trades = list(getattr(bt, "trades", None) or []) if bt else []
                if bt and not backtest_extra:
                    backtest_extra = {
                        "win_rate": bt.win_rate,
                        "max_drawdown": bt.max_drawdown,
                        "sharpe_ratio": getattr(bt, "sharpe_ratio", 0),
                        "profit_factor": bt.profit_factor,
                        "total_return": bt.total_return,
                        "trade_count": bt.trade_count,
                        "verdict": bt.verdict,
                    }
            except Exception:
                trades = []

        return {
            "past_50": self._trade_stats(trades, 50),
            "past_100": self._trade_stats(trades, 100),
            "past_250": self._trade_stats(trades, 250),
            "overall": {
                "success_rate": backtest_extra.get("win_rate", NA),
                "average_return": backtest_extra.get("avg_return") or backtest_extra.get("total_return", NA),
                "maximum_drawdown": backtest_extra.get("max_drawdown", NA),
                "sharpe_ratio": backtest_extra.get("sharpe_ratio") or backtest_extra.get("sharpe", NA),
                "profit_factor": backtest_extra.get("profit_factor", NA),
                "trade_count": backtest_extra.get("trade_count") or backtest_extra.get("total_trades", NA),
                "verdict": backtest_extra.get("verdict", NA),
            },
            "strategy_name": backtest_extra.get("strategy_name", "sma_rsi_macd"),
        }

    def _similar_setups(self, backtest_extra: dict, item: Any) -> dict[str, Any]:
        trades = backtest_extra.get("trades") or []
        if not trades:
            try:
                bts = getattr(item, "backtests", None) or []
                bt = next((b for b in bts if getattr(getattr(b, "mode", None), "value", None) == "swing"), None) or (bts[0] if bts else None)
                trades = list(getattr(bt, "trades", None) or []) if bt else []
            except Exception:
                trades = []

        if not trades:
            return {
                "number_of_similar_setups": 0,
                "win_rate": NA,
                "failure_rate": NA,
                "average_return": NA,
                "median_return": NA,
                "best_return": NA,
                "worst_return": NA,
                "maximum_drawdown": NA,
                "historical_success_note": "No historical strategy signals available for this symbol.",
            }

        pnls = [float(t.get("pnl_percent", 0)) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        stats = self._trade_stats(trades)
        return {
            "number_of_similar_setups": len(trades),
            "win_rate": round(len(wins) / len(pnls) * 100, 2),
            "failure_rate": round(len(losses) / len(pnls) * 100, 2),
            "average_return": round(mean(pnls), 2),
            "median_return": round(median(pnls), 2),
            "best_return": round(max(pnls), 2),
            "worst_return": round(min(pnls), 2),
            "maximum_drawdown": stats["maximum_drawdown"],
            "historical_success_note": (
                f"Same swing strategy produced {len(trades)} historical signals; "
                f"won {len(wins)} ({round(len(wins)/len(pnls)*100,1)}%)."
            ),
        }

    def _swing_score(
        self,
        trend: dict,
        momentum: dict,
        volume: dict,
        volatility: dict,
        risk: dict,
        item: Any,
        ind: dict,
    ) -> dict[str, Any]:
        # Category scores 0-100
        trend_map = {"Strong Bullish": 95, "Bullish": 78, "Sideways": 50, "Bearish": 25, "Strong Bearish": 10}
        trend_s = trend_map.get(trend.get("current_trend", "Sideways"), 50)

        mom_s = 50
        if momentum.get("momentum_direction") == "bullish":
            mom_s = 80 if momentum.get("momentum_strength") == "strong" else 65
        elif momentum.get("momentum_direction") == "bearish":
            mom_s = 25

        vol_s = 70 if volume.get("volume_breakout") else (60 if volume.get("volume_trend") == "expanding" else 45)
        if volume.get("accumulation"):
            vol_s = min(100, vol_s + 10)

        risk_s = 50
        rr = risk.get("risk_reward_ratio")
        if isinstance(rr, (int, float)):
            if rr >= 2.5:
                risk_s = 90
            elif rr >= 2:
                risk_s = 80
            elif rr >= 1.5:
                risk_s = 65
            elif rr >= 1:
                risk_s = 50
            else:
                risk_s = 30

        fund_s = 50
        try:
            fund = getattr(item, "fundamental", None)
            if fund and getattr(fund, "fundamental_score", None) is not None:
                fund_s = int(max(0, min(100, 50 + float(fund.fundamental_score) * 50)))
        except Exception:
            pass

        # Relative strength vs own 20d mean
        rs_s = 50
        close = ind.get("close")
        if close and not isinstance(ind.get("ema_20"), str) and ind.get("ema_20"):
            rs_s = 75 if close > ind["ema_20"] else 35

        v_score = volatility.get("volatility_score", 50)
        # Prefer moderate vol for swing
        if 40 <= v_score <= 70:
            vola_s = 75
        elif v_score < 40:
            vola_s = 55
        else:
            vola_s = 40

        try:
            conf = float(getattr(getattr(item, "recommendation", None), "confidence", 0.5) or 0.5)
        except Exception:
            conf = 0.5
        ai_s = int(conf * 100)

        weights = {
            "trend": 0.18,
            "momentum": 0.15,
            "volume": 0.12,
            "risk": 0.12,
            "fundamentals": 0.12,
            "relative_strength": 0.10,
            "volatility": 0.08,
            "ai_confidence": 0.13,
        }
        parts = {
            "trend": trend_s,
            "momentum": mom_s,
            "volume": vol_s,
            "risk": risk_s,
            "fundamentals": fund_s,
            "relative_strength": rs_s,
            "volatility": vola_s,
            "ai_confidence": ai_s,
        }
        total = round(sum(parts[k] * weights[k] for k in weights), 1)
        return {
            "score": total,
            "max": 100,
            "breakdown": parts,
            "weights": {k: int(v * 100) for k, v in weights.items()},
        }

    def _checklist(
        self,
        trend: dict,
        momentum: dict,
        volume: dict,
        patterns: list,
        risk: dict,
        swing_score: dict,
        item: Any,
    ) -> dict[str, Any]:
        trend_good = trend.get("current_trend") in ("Bullish", "Strong Bullish")
        volume_good = bool(volume.get("volume_breakout") or volume.get("volume_trend") == "expanding" or volume.get("accumulation"))
        momentum_good = momentum.get("momentum_direction") == "bullish"
        pattern_valid = any(
            isinstance(p.get("confidence_pct"), (int, float)) and p.get("confidence_pct", 0) >= 50 and p.get("pattern") != "No clear classic pattern"
            for p in patterns
        )
        fund_good = False
        try:
            fund = getattr(item, "fundamental", None)
            fund_good = bool(fund and (fund.fundamental_score or 0) >= 0.1)
        except Exception:
            fund_good = False
        rr = risk.get("risk_reward_ratio")
        risk_ok = isinstance(rr, (int, float)) and rr >= 1.5
        reward_ok = isinstance(rr, (int, float)) and rr >= 2.0
        ai_high = (swing_score.get("breakdown") or {}).get("ai_confidence", 0) >= 70

        items = [
            {"key": "trend", "label": "Trend Good", "passed": trend_good},
            {"key": "volume", "label": "Volume Good", "passed": volume_good},
            {"key": "momentum", "label": "Momentum Good", "passed": momentum_good},
            {"key": "pattern", "label": "Pattern Valid", "passed": pattern_valid},
            {"key": "fundamentals", "label": "Fundamentals Good", "passed": fund_good},
            {"key": "risk", "label": "Risk Acceptable", "passed": risk_ok},
            {"key": "reward", "label": "Reward Good", "passed": reward_ok},
            {"key": "ai", "label": "AI Confidence High", "passed": ai_high},
        ]
        passed = sum(1 for i in items if i["passed"])
        action = getattr(getattr(item, "recommendation", None), "action", None)
        overall = "Trade Ready" if passed >= 6 or (action == "BUY" and passed >= 5) else "Avoid"
        return {"items": items, "passed": passed, "total": len(items), "overall": overall}

    def _fundamentals(self, item: Any, company_info: dict) -> dict[str, Any]:
        fund = getattr(item, "fundamental", None)
        pe = getattr(fund, "pe_ratio", None) if fund else None
        de = getattr(fund, "debt_to_equity", None) if fund else None
        rev = getattr(fund, "revenue_growth_pct", None) if fund else None
        margin = getattr(fund, "profit_margin_pct", None) if fund else None
        score = getattr(fund, "fundamental_score", None) if fund else None
        summary = getattr(fund, "summary", None) if fund else None

        # Optional yfinance enrichment (best effort, never invent)
        extra = self._fetch_extended_fundamentals(getattr(item, "symbol", "") or company_info.get("symbol") or "")

        market_cap = company_info.get("market_cap")
        if market_cap is None:
            market_cap = extra.get("market_cap")

        return {
            "market_cap": market_cap if market_cap is not None else NA,
            "pe": pe if pe is not None else extra.get("pe", NA),
            "pb": extra.get("pb", NA),
            "roe": extra.get("roe", NA),
            "roce": extra.get("roce", NA),
            "debt": extra.get("debt", NA),
            "debt_equity": de if de is not None else extra.get("debt_equity", NA),
            "eps": extra.get("eps", NA),
            "revenue_growth": rev if rev is not None else extra.get("revenue_growth", NA),
            "profit_growth": extra.get("profit_growth", NA),
            "cash_flow": extra.get("cash_flow", NA),
            "promoter_holding": extra.get("promoter_holding", NA),
            "institution_holding": extra.get("institution_holding", NA),
            "fii": extra.get("fii", NA),
            "dii": extra.get("dii", NA),
            "dividend_yield": extra.get("dividend_yield", NA),
            "intrinsic_value": extra.get("intrinsic_value", NA),
            "profit_margin_pct": margin if margin is not None else NA,
            "fundamental_score": score if score is not None else NA,
            "summary": summary or NA,
        }

    def _fetch_extended_fundamentals(self, symbol: str) -> dict[str, Any]:
        if not symbol:
            return {}
        cache_key = f"fund_ext:{symbol.upper()}"
        hit = research_cache.get(cache_key)
        if hit is not None:
            return hit
        out: dict[str, Any] = {}
        try:
            import yfinance as yf

            yf_symbol = symbol if str(symbol).endswith(".NS") else f"{str(symbol).upper()}.NS"
            info = yf.Ticker(yf_symbol).info or {}
            mapping = {
                "market_cap": info.get("marketCap"),
                "pe": info.get("trailingPE"),
                "pb": info.get("priceToBook"),
                "roe": _safe_float((info.get("returnOnEquity") or 0) * 100, 2) if info.get("returnOnEquity") is not None else None,
                "eps": info.get("trailingEps"),
                "debt": info.get("totalDebt"),
                "debt_equity": info.get("debtToEquity"),
                "revenue_growth": _safe_float((info.get("revenueGrowth") or 0) * 100, 2) if info.get("revenueGrowth") is not None else None,
                "profit_growth": _safe_float((info.get("earningsGrowth") or 0) * 100, 2) if info.get("earningsGrowth") is not None else None,
                "cash_flow": info.get("operatingCashflow") or info.get("freeCashflow"),
                "dividend_yield": _safe_float((info.get("dividendYield") or 0) * 100, 2) if info.get("dividendYield") is not None else None,
                "institution_holding": _safe_float((info.get("heldPercentInstitutions") or 0) * 100, 2) if info.get("heldPercentInstitutions") is not None else None,
            }
            # ROCE / promoter / FII / DII / intrinsic often unavailable on free feeds
            mapping["roce"] = None
            mapping["promoter_holding"] = None
            mapping["fii"] = None
            mapping["dii"] = None
            # Simple residual income proxy is intentionally not invented
            mapping["intrinsic_value"] = None
            out = {k: (v if v is not None else NA) for k, v in mapping.items()}
            # store NAs as NA string for consistency when serializing — keep None as NA later
            clean = {k: v for k, v in mapping.items()}
            research_cache.set(cache_key, clean)
            return clean
        except Exception as exc:
            logger.warning("extended fundamentals failed symbol=%s err=%s", symbol, exc)
            research_cache.set(cache_key, {})
            return {}

    def _institutional(self, fundamentals: dict) -> dict[str, Any]:
        # Without a dedicated holdings feed we cannot claim buy/sell flows
        return {
            "fii_buying": NA,
            "fii_selling": NA,
            "dii_buying": NA,
            "dii_selling": NA,
            "mutual_funds": NA,
            "promoter_buying": NA,
            "promoter_selling": NA,
            "fii_holding_pct": fundamentals.get("fii", NA),
            "dii_holding_pct": fundamentals.get("dii", NA),
            "institution_holding_pct": fundamentals.get("institution_holding", NA),
            "promoter_holding_pct": fundamentals.get("promoter_holding", NA),
            "note": "Transaction-level institutional activity requires a dedicated data feed. Holdings shown only when available.",
        }

    def _news_analysis(self, item: Any) -> dict[str, Any]:
        articles = list(getattr(item, "news_articles", None) or [])
        label = getattr(item, "news_sentiment_label", None) or "neutral"
        score = getattr(item, "news_sentiment_score", None)
        summary = getattr(item, "news_summary", None) or NA

        categorized = []
        for a in articles[:8]:
            s = float(getattr(a, "sentiment_score", 0) or 0)
            if s >= 0.2:
                cat = "Positive"
            elif s <= -0.2:
                cat = "Negative"
            else:
                cat = "Neutral"
            impact = "High" if abs(s) >= 0.6 else "Medium" if abs(s) >= 0.3 else "Low"
            categorized.append(
                {
                    "title": getattr(a, "title", ""),
                    "source": getattr(a, "source", ""),
                    "url": getattr(a, "url", ""),
                    "published_at": str(getattr(a, "published_at", "")),
                    "category": cat,
                    "impact": impact,
                    "sentiment_score": s,
                    "why_it_matters": (
                        f"Headline classified {cat.lower()} with {impact.lower()} impact based on model score {s:.2f}. "
                        "Price reaction depends on whether the market already priced this information."
                    ),
                }
            )

        return {
            "overall_label": str(label).capitalize() if label else "Neutral",
            "overall_score": score if score is not None else NA,
            "summary": summary,
            "articles": categorized,
        }

    def _sentiment_analysis(self, item: Any, news: dict) -> dict[str, Any]:
        news_score = news.get("overall_score")
        if not isinstance(news_score, (int, float)):
            news_score = 0.0
        social = getattr(item, "social_sentiment_score", None)
        # social currently may mirror news — mark unavailable if identical pipeline not dedicated
        social_available = social is not None and social != getattr(item, "news_sentiment_score", None)
        components = {
            "news": round(float(news_score), 2),
            "social_media": round(float(social), 2) if social_available else NA,
            "market_mood": NA,
            "analyst_ratings": NA,
        }
        overall = round(float(news_score), 2)
        label = "Positive" if overall >= 0.2 else "Negative" if overall <= -0.2 else "Neutral"
        return {
            "components": components,
            "overall_sentiment_score": overall,
            "overall_label": label,
            "note": "Social, market mood, and analyst ratings show 'Data not available.' until dedicated feeds are configured.",
        }

    def _ai_research_and_confidence(
        self,
        symbol: str,
        company_info: dict,
        trend: dict,
        momentum: dict,
        volume: dict,
        swing_score: dict,
        risk: dict,
        item: Any,
        fundamentals: dict,
        fingerprint: str,
    ) -> dict[str, Any]:
        facts = {
            "symbol": symbol,
            "company_name": company_info.get("company_name") or NA,
            "sector": company_info.get("sector") or NA,
            "industry": company_info.get("industry") or NA,
            "company_description": company_info.get("company_description") or NA,
            "market_cap": company_info.get("market_cap") if company_info.get("market_cap") is not None else NA,
            "current_trend": trend.get("current_trend"),
            "ema_alignment": trend.get("ema_alignment"),
            "adx": trend.get("adx"),
            "momentum_direction": momentum.get("momentum_direction"),
            "momentum_strength": momentum.get("momentum_strength"),
            "rsi": momentum.get("rsi"),
            "macd_histogram": momentum.get("macd_histogram"),
            "volume_breakout": volume.get("volume_breakout"),
            "volume_trend": volume.get("volume_trend"),
            "flow_label": volume.get("flow_label"),
            "swing_score": swing_score.get("score"),
            "score_breakdown": swing_score.get("breakdown"),
            "risk_reward": risk.get("risk_reward_ratio"),
            "entry": risk.get("suggested_entry"),
            "stop": risk.get("stop_loss"),
            "target_1": risk.get("target_1"),
            "recommendation_action": getattr(getattr(item, "recommendation", None), "action", None),
            "recommendation_summary": getattr(getattr(item, "recommendation", None), "summary", None),
            "fundamental_score": fundamentals.get("fundamental_score"),
            "pe": fundamentals.get("pe"),
            "news_label": getattr(item, "news_sentiment_label", None),
            "news_score": getattr(item, "news_sentiment_score", None),
        }

        conf_num = (swing_score.get("breakdown") or {}).get("ai_confidence", 50)
        conf_label = "High" if conf_num >= 70 else "Medium" if conf_num >= 50 else "Low"

        llm_key = research_cache.llm_key(symbol, "research_v1", {"fp": fingerprint, "facts": facts})
        cached_llm = research_cache.get(llm_key)
        if cached_llm is not None:
            summary = cached_llm.get("summary")
            explanation = cached_llm.get("explanation")
            insights = cached_llm.get("insights")
        else:
            summary = self.llm.build_research_summary(symbol, facts)
            explanation = self.llm.build_ai_confidence_explanation(symbol, facts, conf_label)
            insights = self.llm.build_research_insights(symbol, facts)
            research_cache.set(
                llm_key,
                {"summary": summary, "explanation": explanation, "insights": insights},
            )

        return {
            "summary": summary,
            "confidence": {
                "label": conf_label,
                "score": conf_num,
                "explanation": explanation,
                "stance": summary.get("stance") if isinstance(summary, dict) else "Neutral",
            },
            "insights": insights,
        }
