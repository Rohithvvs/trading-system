from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

try:
    from fyers_apiv3 import fyersModel
except ImportError:  # pragma: no cover - handled via fallback
    fyersModel = None

from ..config import settings
from ..schemas import AnalysisMode, OHLCVPoint
from ..utils import get_logger
from ..utils.mock_data import generate_mock_ohlcv


class FyersService:
    def __init__(self) -> None:
        self.logger = get_logger("app.fyers")

    def fetch_ltp(self, symbol: str) -> float | None:
        if not fyersModel or not settings.fyers_app_id or not settings.fyers_access_token:
            return None

        client = self._client()
        response = client.quotes(data={"symbols": self._normalize_symbol(symbol)})
        if not isinstance(response, dict):
            self.logger.warning("FYERS quotes returned non-dict response | symbol=%s", symbol)
            return None

        quotes = response.get("d") or []
        if not quotes:
            self.logger.warning(
                "FYERS quotes returned no data | symbol=%s | response_keys=%s",
                symbol,
                list(response.keys()),
            )
            return None

        value = quotes[0].get("v", {}) if isinstance(quotes[0], dict) else {}
        ltp = value.get("lp") or value.get("ltp")
        try:
            return float(ltp) if ltp is not None else None
        except (TypeError, ValueError):
            self.logger.warning("FYERS quotes returned invalid LTP | symbol=%s | ltp=%s", symbol, ltp)
            return None

    def fetch_ohlcv(
        self,
        symbol: str,
        mode: AnalysisMode,
        resolution: str,
        lookback_window: int,
    ) -> list[OHLCVPoint]:
        points = 40 if mode == AnalysisMode.intraday else max(lookback_window, 60)

        if fyersModel and settings.fyers_app_id and settings.fyers_access_token:
            candles = self._fetch_live_candles(symbol, resolution, lookback_window)
            if candles:
                self.logger.info(
                    "Fetched live FYERS candles | symbol=%s | mode=%s | resolution=%s | candles=%s",
                    symbol,
                    mode.value,
                    resolution,
                    len(candles),
                )
                return candles

        self.logger.info(
            "Using mock candles fallback | symbol=%s | mode=%s | resolution=%s | candles=%s",
            symbol,
            mode.value,
            resolution,
            points,
        )
        return [OHLCVPoint(**item) for item in generate_mock_ohlcv(symbol, points)]

    def _fetch_live_candles(
        self,
        symbol: str,
        resolution: str,
        lookback_window: int,
    ) -> list[OHLCVPoint]:
        client = self._client()
        today = date.today()
        start_date = today - timedelta(days=max(lookback_window, 30))
        payload = {
            "symbol": self._normalize_symbol(symbol),
            "resolution": self._map_resolution(resolution),
            "date_format": "1",
            "range_from": start_date.isoformat(),
            "range_to": today.isoformat(),
            "cont_flag": "1",
        }
        response = client.history(data=payload)
        candle_rows = response.get("candles", []) if isinstance(response, dict) else []
        if not candle_rows:
            self.logger.warning(
                "FYERS history returned no candles | symbol=%s | resolution=%s | response_keys=%s",
                symbol,
                resolution,
                list(response.keys()) if isinstance(response, dict) else "n/a",
            )

        parsed: list[OHLCVPoint] = []
        for row in candle_rows:
            if len(row) < 6:
                continue
            parsed.append(
                OHLCVPoint(
                    timestamp=self._parse_timestamp(row[0]),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=int(row[5]),
                )
            )
        return parsed

    def _normalize_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if ":" in normalized:
            return normalized
        return f"NSE:{normalized}"

    def _client(self):
        return fyersModel.FyersModel(
            is_async=False,
            client_id=settings.fyers_app_id,
            token=settings.fyers_access_token,
            log_path="",
        )

    def _map_resolution(self, resolution: str) -> str:
        mapping = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "1h": "60",
            "4h": "240",
            "1d": "1D",
            "day": "1D",
        }
        return mapping.get(resolution.lower(), resolution)

    def _parse_timestamp(self, raw_value: int | float | str):
        if isinstance(raw_value, str) and raw_value.isdigit():
            raw_value = int(raw_value)
        if isinstance(raw_value, (int, float)):
            return datetime.fromtimestamp(raw_value, tz=timezone.utc)
        return datetime.fromisoformat(str(raw_value))
