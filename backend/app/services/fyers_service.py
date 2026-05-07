from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import time

try:
    from fyers_apiv3 import fyersModel
except ImportError:  # pragma: no cover - handled via fallback
    fyersModel = None

from ..config import settings
from ..schemas import AnalysisMode, OHLCVPoint
from ..utils import get_logger
from ..core.log_manager import fyers_logger


# FYERS-specific exceptions for clearer error handling
class FyersAuthExpiredError(Exception):
    """Raised when the Fyers access token has expired."""
    pass


class FyersAuthInvalidError(Exception):
    """Raised when the Fyers access token is wrong/invalid."""
    pass


class FyersRateLimitError(Exception):
    """Raised when Fyers API rate limit is hit."""
    pass


class FyersAPIError(Exception):
    """Generic Fyers API error with message."""
    pass


def _check_fyers_response(response: dict | object, symbol: str = "") -> None:
    """
    Inspect a FYERS response dict and raise a specific exception when a known
    error condition is present. If `response` is not a dict, this is a no-op.
    """
    if not isinstance(response, dict):
        return

    # FYERS sometimes encodes the status/code under different keys
    code = response.get("code") if "code" in response else response.get("s")
    message = response.get("message", "")

    # Normalize code to int when possible
    code_int = None
    try:
        if code is not None:
            code_int = int(code)
    except Exception:
        code_int = None

    lower_msg = str(message).lower() if message is not None else ""

    # Token expired — FYERS returns code -16 or message contains 'expired'
    if code_int == -16 or "expired" in lower_msg:
        raise FyersAuthExpiredError("Fyers access token has expired. Please re-authenticate.")

    # Invalid token — FYERS returns code -15 or 'invalid token'
    if code_int == -15 or "invalid token" in lower_msg:
        raise FyersAuthInvalidError("Fyers access token is invalid. Please check your credentials.")

    # Rate limit — FYERS returns code 429
    if code_int == 429 or "too many requests" in lower_msg:
        raise FyersRateLimitError("Fyers API rate limit hit. Please wait and try again.")

    # Any other non-ok response
    if response.get("s") == "error" or (code_int is not None and code_int < 0):
        raise FyersAPIError(f"Fyers API error for symbol '{symbol}': code={code} message={message}")


class FyersService:
    def __init__(self) -> None:
        self.logger = get_logger("app.fyers")
        self._ltp_cache: dict[str, float | None] = {}
        self._ltp_source_cache: dict[str, str] = {}
        self._ohlcv_cache: dict[tuple[str, str, str], tuple[int, list[OHLCVPoint]]] = {}
        self._ohlcv_source_cache: dict[tuple[str, str, str], str] = {}

    def fetch_ltp(self, symbol: str) -> float | None:
        cache_key = self._cache_symbol(symbol)
        if cache_key in self._ltp_cache:
            # Memory cache hit - record to fyers_api log
            try:
                fyers_logger.info("QUOTES CACHE_HIT | symbol=%s | ltp=%s | source=MEMORY_CACHE", symbol, self._ltp_cache[cache_key])
            except Exception:
                pass
            return self._ltp_cache[cache_key]

        if self._is_fyers_configured():
            ltp = self._fetch_fyers_ltp(symbol)
            if ltp is not None:
                # Record structured FYERS quote event
                try:
                    fyers_logger.info("QUOTES | symbol=%s | ltp=%s | source=FYERS_PRIMARY", symbol, ltp)
                except Exception:
                    pass
                self.logger.info("Fetched live quote from FYERS | symbol=%s", symbol)
                self._ltp_cache[cache_key] = ltp
                self._ltp_source_cache[cache_key] = "FYERS_PRIMARY"
                return ltp

        self._ltp_cache[cache_key] = None
        self._ltp_source_cache[cache_key] = "NO_DATA"
        return None

    def fetch_ohlcv(
        self,
        symbol: str,
        mode: AnalysisMode,
        resolution: str,
        lookback_window: int,
        allow_mock: bool = False,
    ) -> list[OHLCVPoint]:
        points = 40 if mode == AnalysisMode.intraday else max(lookback_window, 260)
        cache_key = (self._cache_symbol(symbol), mode.value, resolution.lower())
        cached = self._ohlcv_cache.get(cache_key)
        if cached and cached[0] >= lookback_window and len(cached[1]) >= points:
            cached_source = self._ohlcv_source_cache.get(cache_key, "unknown")
            self.logger.info(
                "OHLCV SOURCE = MEMORY_CACHE | symbol=%s | mode=%s | resolution=%s | candles=%s",
                symbol,
                mode.value,
                resolution,
                len(cached[1][-points:]),
            )
            self.logger.info(
                "FETCH_OHLCV CACHE HIT | symbol=%s | mode=%s | resolution=%s | lookback=%s | candles=%s | source=%s",
                symbol,
                mode.value,
                resolution,
                lookback_window,
                len(cached[1][-points:]),
                cached_source,
            )
            try:
                fyers_logger.info(
                    "OHLCV CACHE_HIT | symbol=%s | mode=%s | resolution=%s | candles=%s | source=%s",
                    symbol,
                    mode.value,
                    resolution,
                    len(cached[1][-points:]),
                    cached_source,
                )
            except Exception:
                pass
            return cached[1][-points:]

        self.logger.info(
            "FETCH_OHLCV | symbol=%s | mode=%s | resolution=%s | lookback=%s | allow_mock=%s | fyers_configured=%s",
            symbol,
            mode.value,
            resolution,
            lookback_window,
            allow_mock,
            self._is_fyers_configured(),
        )

        if self._is_fyers_configured():
            candles = self._fetch_fyers_candles(symbol, resolution, lookback_window, points)
            if candles:
                try:
                    fyers_logger.info(
                        "OHLCV | symbol=%s | mode=%s | resolution=%s | candles=%s | source=FYERS_PRIMARY",
                        symbol,
                        mode.value,
                        resolution,
                        len(candles),
                    )
                except Exception:
                    pass
                self.logger.info(
                    "Fetched live FYERS candles | symbol=%s | mode=%s | resolution=%s | candles=%s",
                    symbol,
                    mode.value,
                    resolution,
                    len(candles),
                )
                self._store_ohlcv_cache(cache_key, lookback_window, candles, "FYERS_PRIMARY")
                return candles
            self.logger.warning(
                "FYERS API returned no candles | symbol=%s | mode=%s | resolution=%s",
                symbol,
                mode.value,
                resolution,
            )

        self.logger.warning(
            "FYERS live data unavailable | symbol=%s | mode=%s | resolution=%s | returning empty | allow_mock=%s",
            symbol,
            mode.value,
            resolution,
            allow_mock,
        )
        self._store_ohlcv_cache(cache_key, lookback_window, [], "NO_DATA")
        return []

    def get_ltp_source(self, symbol: str) -> str:
        return self._ltp_source_cache.get(self._cache_symbol(symbol), "unknown")

    def get_ohlcv_source(
        self,
        symbol: str,
        mode: AnalysisMode,
        resolution: str,
    ) -> str:
        cache_key = (self._cache_symbol(symbol), mode.value, resolution.lower())
        return self._ohlcv_source_cache.get(cache_key, "unknown")

    def _is_fyers_configured(self) -> bool:
        # Consider FYERS configured only when the SDK is available, app id is set,
        # and a manually-saved access token exists in the DB.
        if not fyersModel:
            return False
        if not (settings.fyers_app_id and settings.fyers_app_id.strip()):
            return False
        try:
            from ..db.session import SessionLocal
            from ..models import FyersToken

            db = SessionLocal()
            try:
                row = db.query(FyersToken).filter(FyersToken.id == 1).one_or_none()
                return bool(row and row.access_token)
            finally:
                db.close()
        except Exception:
            return False

    def is_fyers_sdk_available(self) -> bool:
        return fyersModel is not None

    def has_fyers_credentials(self) -> bool:
        try:
            from ..db.session import SessionLocal
            from ..models import FyersToken

            if not (settings.fyers_app_id and settings.fyers_app_id.strip()):
                return False
            db = SessionLocal()
            try:
                row = db.query(FyersToken).filter(FyersToken.id == 1).one_or_none()
                return bool(row and row.access_token)
            finally:
                db.close()
        except Exception:
            return False

    def _fetch_fyers_ltp(self, symbol: str) -> float | None:
        try:
            client = self._client()
            start = time.time()
            client = self._client()
            response = client.quotes(data={"symbols": self._normalize_symbol(symbol)})
            response_ms = int((time.time() - start) * 1000)
            _check_fyers_response(response, symbol)
        except Exception as exc:  # pragma: no cover - network/provider failure
            # If we raised a Fyers*Error above it will be caught by callers
            self.logger.warning("FYERS quotes request failed | symbol=%s | error=%s", symbol, exc)
            try:
                fyers_logger.warning("QUOTES_REQUEST_FAILED | symbol=%s | error=%s", symbol, exc)
            except Exception:
                pass
            return None

        if not isinstance(response, dict):
            self.logger.warning("FYERS quotes returned non-dict response | symbol=%s", symbol)
            try:
                fyers_logger.warning("QUOTES_NON_DICT | symbol=%s | response_type=%s", symbol, type(response))
            except Exception:
                pass
            return None

        quotes = response.get("d") or []
        if not quotes:
            self.logger.warning(
                "FYERS quotes returned no data | symbol=%s | response_keys=%s",
                symbol,
                list(response.keys()),
            )
            try:
                fyers_logger.warning("QUOTES_EMPTY | symbol=%s | response_keys=%s", symbol, list(response.keys()))
            except Exception:
                pass
            return None

        value = quotes[0].get("v", {}) if isinstance(quotes[0], dict) else {}
        ltp = value.get("lp") or value.get("ltp")
        try:
            numeric = float(ltp) if ltp is not None else None
            try:
                fyers_logger.info("QUOTES_RESPONSE | symbol=%s | ltp=%s | response_ms=%s | status=OK", symbol, numeric, response_ms)
            except Exception:
                pass
            return numeric
        except (TypeError, ValueError):
            self.logger.warning("FYERS quotes returned invalid LTP | symbol=%s | ltp=%s", symbol, ltp)
            try:
                fyers_logger.warning("QUOTES_INVALID_LTP | symbol=%s | ltp=%s", symbol, ltp)
            except Exception:
                pass
            return None

    def _fetch_fyers_candles(
        self,
        symbol: str,
        resolution: str,
        lookback_window: int,
        points: int,
    ) -> list[OHLCVPoint]:
        from .ohlcv_store import (
            get_candle_count,
            get_last_stored_date,
            init_db,
            load_candles,
            save_candles,
        )

        def request_history(range_from: str, range_to: str) -> list[list[object]]:
            payload = {
                "symbol": self._normalize_symbol(symbol),
                "resolution": self._map_resolution(resolution),
                "date_format": "1",
                "range_from": range_from,
                "range_to": range_to,
                "cont_flag": "1",
            }
            self.logger.info(
                "OHLCV SOURCE = FYERS_API | symbol=%s | resolution=%s | range_from=%s | range_to=%s",
                symbol,
                resolution,
                range_from,
                range_to,
            )
            self.logger.info(
                "FYERS history request | symbol=%s | resolution=%s | range_from=%s | range_to=%s | payload_resolution=%s",
                symbol,
                resolution,
                range_from,
                range_to,
                payload["resolution"],
            )
            response = client.history(data=payload)
            # Check for structured FYERS errors and raise if found
            _check_fyers_response(response, symbol)
            candle_rows = response.get("candles", []) if isinstance(response, dict) else []
            if not candle_rows:
                self.logger.warning(
                    "FYERS history returned no candles | symbol=%s | resolution=%s | response_keys=%s",
                    symbol,
                    resolution,
                    list(response.keys()) if isinstance(response, dict) else "n/a",
                )
            return candle_rows

        try:
            client = self._client()
            today = date.today()
            mapped_resolution = self._map_resolution(resolution)
            if mapped_resolution != "1D":
                start_date = today - timedelta(days=max(lookback_window, 260))
                candle_rows = request_history(start_date.isoformat(), today.isoformat())
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
                return parsed[-points:]

            init_db()
            clean_symbol = self._cache_symbol(symbol)
            db_count = get_candle_count(clean_symbol)
            last_date = get_last_stored_date(clean_symbol)

            if db_count >= 220 and last_date is not None:
                candle_rows = request_history(last_date, today.isoformat())
                new_rows: list[dict[str, object]] = []
                for row in candle_rows:
                    if len(row) < 6:
                        continue
                    candle_date = self._parse_timestamp(row[0]).date().isoformat()
                    new_rows.append(
                        {
                            "date": candle_date,
                            "open": float(row[1]),
                            "high": float(row[2]),
                            "low": float(row[3]),
                            "close": float(row[4]),
                            "volume": int(row[5]),
                        }
                    )
                if new_rows:
                    save_candles(clean_symbol, new_rows)
                    self.logger.info(
                        "OHLCV DB SAVE | symbol=%s | saved=%s",
                        symbol,
                        len(new_rows),
                    )
            else:
                range_1_from = (today - timedelta(days=730)).isoformat()
                range_1_to = (today - timedelta(days=365)).isoformat()
                range_2_from = (today - timedelta(days=365)).isoformat()
                range_2_to = today.isoformat()
                candle_rows = request_history(range_1_from, range_1_to) + request_history(range_2_from, range_2_to)

                deduped_rows: dict[str, dict[str, object]] = {}
                for row in candle_rows:
                    if len(row) < 6:
                        continue
                    candle_date = self._parse_timestamp(row[0]).date().isoformat()
                    deduped_rows[candle_date] = {
                        "date": candle_date,
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": int(row[5]),
                    }
                if deduped_rows:
                    all_rows = [deduped_rows[key] for key in sorted(deduped_rows)]
                    save_candles(clean_symbol, all_rows)
                    self.logger.info(
                        "OHLCV DB SAVE | symbol=%s | saved=%s",
                        symbol,
                        len(all_rows),
                    )
        except Exception as exc:  # pragma: no cover - network/provider failure
            self.logger.warning("FYERS history request failed | symbol=%s | resolution=%s | error=%s", symbol, resolution, exc)
            return []

        two_years_ago = (today - timedelta(days=730)).isoformat()
        db_rows = load_candles(clean_symbol, two_years_ago)
        self.logger.info(
            "OHLCV SOURCE = SQLITE_DB | symbol=%s | resolution=%s | candles=%s | db_count=%s | last_date=%s",
            symbol,
            resolution,
            len(db_rows),
            db_count,
            last_date,
        )

        parsed: list[OHLCVPoint] = []
        for row in db_rows:
            parsed.append(
                OHLCVPoint(
                    timestamp=self._parse_timestamp(row["date"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                )
            )
        return parsed[-points:]

    def get_candles_cached(
        self,
        symbol: str,
        mode: AnalysisMode,
        resolution: str,
        lookback_window: int,
        allow_mock: bool = False,
    ) -> list[OHLCVPoint]:
        """
        Returns candles using a local SQLite cache. Reads from cache when fresh,
        otherwise fetches from FYERS and stores into the cache.
        """
        points = 40 if mode == AnalysisMode.intraday else max(lookback_window, 260)
        mapped_resolution = self._map_resolution(resolution)

        # Only cache daily candles in this simple strategy
        if mapped_resolution == "1D":
            try:
                from app.services import candle_store
            except Exception:
                # If the cache module is not available, fall back to live fetch
                self.logger.warning("CANDLE STORE not available, falling back to live fetch | symbol=%s", symbol)
                return self.fetch_ohlcv(symbol, mode, resolution, lookback_window, allow_mock)

            candle_store.init_db()
            clean_symbol = self._cache_symbol(symbol)

            if candle_store.is_cache_fresh(clean_symbol, max_age_minutes=30):
                df = candle_store.load_candles(clean_symbol)
                parsed: list[OHLCVPoint] = []
                for _, row in df.iterrows():
                    parsed.append(
                        OHLCVPoint(
                            timestamp=self._parse_timestamp(row["date"]),
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=int(row["volume"]),
                        )
                    )
                self.logger.info("CACHE HIT | symbol=%s | source=DB | candles=%s", symbol, len(parsed))
                return parsed[-points:]

            last_stored = candle_store.get_last_stored_date(clean_symbol)
            self.logger.info(
                "CACHE MISS | symbol=%s | last_stored=%s | source=FYERS fetching now",
                symbol,
                last_stored,
            )

            # Fetch from FYERS using existing logic (this may also populate the app-level ohlcv store)
            fetched = self._fetch_fyers_candles(symbol, resolution, lookback_window, points)

            if fetched:
                try:
                    import pandas as pd

                    rows = [
                        {
                            "date": p.timestamp.date().isoformat(),
                            "open": float(p.open),
                            "high": float(p.high),
                            "low": float(p.low),
                            "close": float(p.close),
                            "volume": int(p.volume),
                        }
                        for p in fetched
                    ]
                    df = pd.DataFrame(rows)
                    candle_store.store_candles(clean_symbol, df)
                    self.logger.info("CACHE STORED | symbol=%s | rows=%s", symbol, len(df))
                except Exception as exc:  # pragma: no cover - best-effort cache write
                    self.logger.warning("Failed to persist candles to cache | symbol=%s | error=%s", symbol, exc)

            return fetched

        # Non-daily resolutions: fall back to existing fetch behaviour
        return self.fetch_ohlcv(symbol, mode, resolution, lookback_window, allow_mock)

    def _normalize_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if ":" in normalized:
            return normalized
        return f"NSE:{normalized}"

    def _cache_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if ":" in normalized:
            _, normalized = normalized.split(":", 1)
        return normalized.replace("-EQ", "")

    def _store_ohlcv_cache(
        self,
        cache_key: tuple[str, str, str],
        lookback_window: int,
        candles: list[OHLCVPoint],
        source: str,
    ) -> None:
        cached = self._ohlcv_cache.get(cache_key)
        if not cached or lookback_window >= cached[0]:
            self._ohlcv_cache[cache_key] = (lookback_window, candles)
            self._ohlcv_source_cache[cache_key] = source

    def _client(self):
        # Normalize client_id and token to avoid common mistakes where
        # the token is stored or passed with surrounding quotes or prefixed
        # with the app id (e.g. "APPID:ACCESS_TOKEN"). FyersModel expects
        # the raw access token only.
        client_id = (settings.fyers_app_id or "").strip().strip('"').strip("'")

        # Read token from DB (manual access token). Do NOT fall back to env.
        token = None
        from ..db.session import SessionLocal
        from ..models import FyersToken

        db = SessionLocal()
        try:
            row = db.query(FyersToken).filter(FyersToken.id == 1).one_or_none()
            if row and row.access_token:
                token = str(row.access_token).strip().strip('"').strip("'")
        finally:
            db.close()

        if not token:
            # Clear, explicit error to callers so they can inform the user.
            raise FyersAuthInvalidError("No FYERS access token configured. Please add one in the UI.")

        # If the token was accidentally stored as "APPID:ACCESS_TOKEN", drop the prefix
        if client_id and token and token.startswith(f"{client_id}:"):
            token = token.split(":", 1)[1]

        return fyersModel.FyersModel(
            is_async=False,
            client_id=client_id,
            token=token,
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
