"""Chart OHLCV data with technical indicators and layout persistence."""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.retail import ChartLayout
from ..schemas import AnalysisMode
from ..schemas.retail import (
    ChartCandle,
    ChartDataResponse,
    ChartLayoutCreate,
    ChartLayoutResponse,
    ChartLayoutUpdate,
    IndicatorPoint,
    MacdPoint,
)
from .fyers_service import FyersService

TIMEFRAME_MAP = {
    "1m": ("intraday", "1"),
    "5m": ("intraday", "5"),
    "15m": ("intraday", "15"),
    "30m": ("intraday", "30"),
    "1H": ("intraday", "60"),
    "4H": ("intraday", "240"),
    "1D": ("swing", "1d"),
    "1W": ("swing", "1W"),
    "1M": ("swing", "1M"),
    "1d": ("swing", "1d"),
    "1w": ("swing", "1W"),
}


class ChartService:
    def __init__(self, db: Session, user_id: uuid.UUID | None = None) -> None:
        self.db = db
        self.user_id = user_id
        self.fyers = FyersService()

    def get_chart_data(
        self,
        symbol: str,
        timeframe: str = "1D",
        indicators: list[str] | None = None,
        lookback: int = 300,
    ) -> ChartDataResponse:
        symbol = symbol.strip().upper().replace("NSE:", "").replace("-EQ", "")
        tf_key = timeframe if timeframe in TIMEFRAME_MAP else timeframe.upper()
        mode_str, fyers_tf = TIMEFRAME_MAP.get(tf_key, TIMEFRAME_MAP.get(timeframe, ("swing", "1d")))
        mode = AnalysisMode.intraday if mode_str == "intraday" else AnalysisMode.swing

        candles_raw = []
        source = "NO_DATA"
        try:
            import asyncio
            from ..db.session import main_event_loop

            async def _fetch():
                return await self.fyers.fetch_ohlcv(symbol, mode, fyers_tf, lookback)

            if main_event_loop and main_event_loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(_fetch(), main_event_loop)
                candles_raw = fut.result(timeout=15) or []
            else:
                from .fyers_service import _run_sync

                candles_raw = _run_sync(self.fyers.fetch_ohlcv(symbol, mode, fyers_tf, lookback)) or []
            source = "FYERS" if candles_raw else "NO_DATA"
        except Exception:
            candles_raw = []

        candles: list[ChartCandle] = []
        for c in candles_raw:
            ts = c.timestamp
            if isinstance(ts, datetime):
                t = int(ts.timestamp())
            elif isinstance(ts, str):
                try:
                    t = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
                except Exception:
                    continue
            else:
                t = int(ts)
            candles.append(
                ChartCandle(
                    time=t,
                    open=float(c.open),
                    high=float(c.high),
                    low=float(c.low),
                    close=float(c.close),
                    volume=float(getattr(c, "volume", 0) or 0),
                )
            )
        candles.sort(key=lambda x: x.time)

        ind_names = indicators or ["EMA", "SMA", "VWAP", "RSI", "MACD", "ATR", "Supertrend", "Bollinger"]
        computed = self._compute_indicators(candles, ind_names)

        return ChartDataResponse(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            indicators=computed,
            source=source,
            updated_at=datetime.now(timezone.utc),
        )

    def list_layouts(self) -> list[ChartLayoutResponse]:
        if not self.user_id:
            return []
        rows = self.db.scalars(
            select(ChartLayout).where(ChartLayout.user_id == self.user_id).order_by(ChartLayout.updated_at.desc())
        ).all()
        return [self._layout_resp(r) for r in rows]

    def save_layout(self, payload: ChartLayoutCreate) -> ChartLayoutResponse:
        if not self.user_id:
            raise ValueError("Authentication required")
        existing = self.db.scalar(
            select(ChartLayout).where(ChartLayout.user_id == self.user_id, ChartLayout.name == payload.name)
        )
        row = existing or ChartLayout(user_id=self.user_id, name=payload.name)
        row.symbol = payload.symbol.upper()
        row.timeframe = payload.timeframe
        row.chart_type = payload.chart_type
        row.theme = payload.theme
        row.indicators_json = json.dumps(payload.indicators)
        row.drawings_json = json.dumps(payload.drawings)
        row.is_default = payload.is_default
        row.updated_at = datetime.now(timezone.utc)
        if payload.is_default:
            for other in self.db.scalars(
                select(ChartLayout).where(ChartLayout.user_id == self.user_id, ChartLayout.id != getattr(row, "id", -1))
            ).all():
                other.is_default = False
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._layout_resp(row)

    def update_layout(self, layout_id: int, payload: ChartLayoutUpdate) -> ChartLayoutResponse:
        row = self.db.scalar(
            select(ChartLayout).where(ChartLayout.id == layout_id, ChartLayout.user_id == self.user_id)
        )
        if not row:
            raise ValueError("Layout not found")
        if payload.name is not None:
            row.name = payload.name
        if payload.symbol is not None:
            row.symbol = payload.symbol.upper()
        if payload.timeframe is not None:
            row.timeframe = payload.timeframe
        if payload.chart_type is not None:
            row.chart_type = payload.chart_type
        if payload.theme is not None:
            row.theme = payload.theme
        if payload.indicators is not None:
            row.indicators_json = json.dumps(payload.indicators)
        if payload.drawings is not None:
            row.drawings_json = json.dumps(payload.drawings)
        if payload.is_default is not None:
            row.is_default = payload.is_default
        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(row)
        return self._layout_resp(row)

    def delete_layout(self, layout_id: int) -> None:
        row = self.db.scalar(
            select(ChartLayout).where(ChartLayout.id == layout_id, ChartLayout.user_id == self.user_id)
        )
        if row:
            self.db.delete(row)
            self.db.commit()

    def _layout_resp(self, row: ChartLayout) -> ChartLayoutResponse:
        try:
            indicators = json.loads(row.indicators_json or "[]")
        except Exception:
            indicators = []
        try:
            drawings = json.loads(row.drawings_json or "[]")
        except Exception:
            drawings = []
        return ChartLayoutResponse(
            id=row.id,
            name=row.name,
            symbol=row.symbol,
            timeframe=row.timeframe,
            chart_type=row.chart_type,
            theme=row.theme,
            indicators=indicators,
            drawings=drawings,
            is_default=row.is_default,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _compute_indicators(self, candles: list[ChartCandle], names: list[str]) -> dict[str, Any]:
        if not candles:
            return {}
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.volume for c in candles]
        times = [c.time for c in candles]
        out: dict[str, Any] = {}

        wanted = {n.upper() for n in names}

        if "EMA" in wanted or "EMA20" in wanted:
            out["ema20"] = self._to_points(times, self._ema(closes, 20))
            out["ema50"] = self._to_points(times, self._ema(closes, 50))
        if "SMA" in wanted or "SMA20" in wanted:
            out["sma20"] = self._to_points(times, self._sma(closes, 20))
            out["sma50"] = self._to_points(times, self._sma(closes, 50))
        if "VWAP" in wanted:
            out["vwap"] = self._to_points(times, self._vwap(highs, lows, closes, volumes))
        if "RSI" in wanted:
            out["rsi"] = self._to_points(times, self._rsi(closes, 14))
        if "MACD" in wanted:
            out["macd"] = self._macd(times, closes)
        if "ATR" in wanted:
            out["atr"] = self._to_points(times, self._atr(highs, lows, closes, 14))
        if "SUPERTREND" in wanted:
            out["supertrend"] = self._to_points(times, self._supertrend(highs, lows, closes, 10, 3.0))
        if "BOLLINGER" in wanted or "BOLLINGER BANDS" in wanted or "BB" in wanted:
            mid, upper, lower = self._bollinger(closes, 20, 2.0)
            out["bb_mid"] = self._to_points(times, mid)
            out["bb_upper"] = self._to_points(times, upper)
            out["bb_lower"] = self._to_points(times, lower)

        return out

    @staticmethod
    def _to_points(times: list[int], values: list[float | None]) -> list[dict[str, float | int]]:
        return [{"time": t, "value": v} for t, v in zip(times, values) if v is not None and not math.isnan(v)]

    @staticmethod
    def _sma(data: list[float], period: int) -> list[float | None]:
        out: list[float | None] = [None] * len(data)
        for i in range(period - 1, len(data)):
            out[i] = sum(data[i - period + 1 : i + 1]) / period
        return out

    @staticmethod
    def _ema(data: list[float], period: int) -> list[float | None]:
        out: list[float | None] = [None] * len(data)
        if len(data) < period:
            return out
        k = 2 / (period + 1)
        ema = sum(data[:period]) / period
        out[period - 1] = ema
        for i in range(period, len(data)):
            ema = data[i] * k + ema * (1 - k)
            out[i] = ema
        return out

    @staticmethod
    def _vwap(h: list[float], l: list[float], c: list[float], v: list[float]) -> list[float | None]:
        out: list[float | None] = []
        cum_tp_v = 0.0
        cum_v = 0.0
        for i in range(len(c)):
            tp = (h[i] + l[i] + c[i]) / 3
            vol = v[i] or 0
            cum_tp_v += tp * vol
            cum_v += vol
            out.append(cum_tp_v / cum_v if cum_v else None)
        return out

    @staticmethod
    def _rsi(closes: list[float], period: int = 14) -> list[float | None]:
        out: list[float | None] = [None] * len(closes)
        if len(closes) < period + 1:
            return out
        gains = []
        losses = []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0))
            losses.append(max(-d, 0))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        out[period] = 100 - (100 / (1 + (avg_gain / avg_loss if avg_loss else 1e9)))
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rs = avg_gain / avg_loss if avg_loss else 1e9
            out[i + 1] = 100 - (100 / (1 + rs))
        return out

    def _macd(self, times: list[int], closes: list[float]) -> list[dict[str, float | int]]:
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        macd_line: list[float | None] = []
        for a, b in zip(ema12, ema26):
            if a is None or b is None:
                macd_line.append(None)
            else:
                macd_line.append(a - b)
        # signal on non-null macd
        macd_vals = [m if m is not None else 0.0 for m in macd_line]
        signal = self._ema(macd_vals, 9)
        out = []
        for i, t in enumerate(times):
            if macd_line[i] is None or signal[i] is None:
                continue
            m = macd_line[i]
            s = signal[i]
            out.append({"time": t, "macd": m, "signal": s, "histogram": m - s})
        return out

    @staticmethod
    def _atr(h: list[float], l: list[float], c: list[float], period: int = 14) -> list[float | None]:
        trs = [h[0] - l[0]]
        for i in range(1, len(c)):
            tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
            trs.append(tr)
        out: list[float | None] = [None] * len(c)
        if len(trs) < period:
            return out
        atr = sum(trs[:period]) / period
        out[period - 1] = atr
        for i in range(period, len(trs)):
            atr = (atr * (period - 1) + trs[i]) / period
            out[i] = atr
        return out

    def _supertrend(
        self, h: list[float], l: list[float], c: list[float], period: int = 10, mult: float = 3.0
    ) -> list[float | None]:
        atr = self._atr(h, l, c, period)
        out: list[float | None] = [None] * len(c)
        direction = 1
        st = None
        for i in range(len(c)):
            if atr[i] is None:
                continue
            mid = (h[i] + l[i]) / 2
            upper = mid + mult * atr[i]
            lower = mid - mult * atr[i]
            if st is None:
                st = lower
                direction = 1
            elif direction == 1:
                st = max(lower, st)
                if c[i] < st:
                    direction = -1
                    st = upper
            else:
                st = min(upper, st)
                if c[i] > st:
                    direction = 1
                    st = lower
            out[i] = st
        return out

    @staticmethod
    def _bollinger(
        closes: list[float], period: int = 20, std_mult: float = 2.0
    ) -> tuple[list[float | None], list[float | None], list[float | None]]:
        mid = ChartService._sma(closes, period)
        upper: list[float | None] = [None] * len(closes)
        lower: list[float | None] = [None] * len(closes)
        for i in range(period - 1, len(closes)):
            window = closes[i - period + 1 : i + 1]
            mean = mid[i]
            if mean is None:
                continue
            var = sum((x - mean) ** 2 for x in window) / period
            sd = math.sqrt(var)
            upper[i] = mean + std_mult * sd
            lower[i] = mean - std_mult * sd
        return mid, upper, lower
