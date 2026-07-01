from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import threading
import time
from sqlalchemy import text
from ..db.session import AsyncSessionLocal

try:
    from fyers_apiv3 import fyersModel
except ImportError:  # pragma: no cover - handled via fallback
    fyersModel = None

from ..config import settings
from ..schemas import AnalysisMode, OHLCVPoint
from ..utils import get_logger
from ..core.log_manager import fyers_logger
from ..observability.scan_diagnostics import (
    get_current_scan, log_fyers_request, log_fyers_response,
    log_fyers_failure, log_cache_lookup, log_data_source_selection,
)

QUARANTINED_SYMBOLS: dict[str, datetime] = {}
_BLACKLIST_LOCK = threading.Lock()
_FYERS_HISTORY_SEMAPHORE = threading.BoundedSemaphore(3)
_FYERS_MAX_RETRIES = 3

import requests
_local_timeout = threading.local()
_original_session_request = requests.Session.request

def _timeout_patched_request(self, method, url, **kwargs):
    timeout = getattr(_local_timeout, "timeout", None)
    if timeout is not None:
        kwargs.setdefault("timeout", timeout)
    return _original_session_request(self, method, url, **kwargs)

requests.Session.request = _timeout_patched_request

class NetworkTimeoutContext:
    def __init__(self, timeout: float):
        self.timeout = timeout
    def __enter__(self):
        _local_timeout.timeout = self.timeout
    def __exit__(self, exc_type, exc_val, exc_tb):
        _local_timeout.timeout = None

import asyncio
import concurrent.futures

_SYNC_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=5)

def _run_sync(coro):
    from ..db import session as session_module
    import asyncio
    main_loop = getattr(session_module, "main_event_loop", None)
    
    # Fast path: If already in main loop and it's running, and we're somehow in it
    try:
        current_loop = asyncio.get_running_loop()
        if current_loop is main_loop:
            # We shouldn't block the async loop, but since this is called synchronously...
            # This is a fallback to avoid Deadlocks if called incorrectly.
            pass
    except RuntimeError:
        pass

    if main_loop and main_loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, main_loop).result()
    else:
        # Fallback for scripts and tests without a main loop
        return _SYNC_EXECUTOR.submit(asyncio.run, coro).result()


# FYERS-specific exceptions for clearer error handling
class FyersAuthExpiredError(Exception):
    """Raised when the Fyers access token has expired."""


class FyersAuthInvalidError(Exception):
    """Raised when the Fyers access token is wrong/invalid."""


class FyersRateLimitError(Exception):
    """Raised when Fyers API rate limit is hit."""


class FyersAPIError(Exception):
    """Generic Fyers API error with message."""


class FyersNetworkException(Exception):
    """Raised when FYERS API connection drops or exhausts all retries."""


class FyersInvalidSymbolError(Exception):
    """Raised when FYERS reports an invalid or delisted symbol."""


def _check_fyers_response(response: dict | object, symbol: str = "") -> None:
    """
    Inspect a FYERS response dict and raise a specific exception when a known
    error condition is present. If `response` is not a dict, this is a no-op.
    """
    from .diagnostics_service import diagnostics
    diagnostics.increment_fyers_metric("request_count")
    
    if not isinstance(response, dict):
        diagnostics.increment_fyers_metric("failed_request_count")
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
        diagnostics.increment_fyers_metric("failed_request_count")
        diagnostics.increment_fyers_metric("auth_failures")
        from . import token_service
        token_service._clear_token_cache()
        token_service.logger.error("TOKEN_AUTH_FAILURE | Fyers access token has expired")
        raise FyersAuthExpiredError("Fyers access token has expired. Please re-authenticate.")

    # Invalid token — FYERS returns code -15 or 'invalid token'
    if code_int == -15 or "invalid token" in lower_msg:
        diagnostics.increment_fyers_metric("failed_request_count")
        diagnostics.increment_fyers_metric("auth_failures")
        from . import token_service
        token_service._clear_token_cache()
        token_service.logger.error("TOKEN_AUTH_FAILURE | Fyers access token is invalid")
        raise FyersAuthInvalidError("Fyers access token is invalid. Please check your credentials.")

    # Rate limit — FYERS returns code 429
    if code_int == 429 or "too many requests" in lower_msg:
        diagnostics.increment_fyers_metric("failed_request_count")
        diagnostics.increment_fyers_metric("rate_limit_count")
        raise FyersRateLimitError("Fyers API rate limit hit. Please wait and try again.")

    if code_int == -300 or "invalid symbol" in lower_msg:
        diagnostics.increment_fyers_metric("failed_request_count")
        raise FyersInvalidSymbolError(f"FYERS invalid symbol '{symbol}': code={code} message={message}")

    # Any other non-ok response
    if response.get("s") == "error" or (code_int is not None and code_int < 0):
        diagnostics.increment_fyers_metric("failed_request_count")
        raise FyersAPIError(f"Fyers API error for symbol '{symbol}': code={code} message={message}")


class FyersService:
    _ohlcv_cache: dict[tuple, tuple[int, list[OHLCVPoint], float]] = {}
    _ohlcv_source_cache: dict[tuple, str] = {}
    _ohlcv_thread_locks = {}
    _ohlcv_thread_lock = threading.Lock()
    _ltp_source_cache: dict[str, str] = {}
    _ltp_locks: dict[str, "asyncio.Lock"] = {}
    _network_pool = __import__("concurrent.futures").futures.ThreadPoolExecutor(max_workers=20, thread_name_prefix="fyers_net")

    def __init__(self) -> None:
        self.logger = get_logger("app.fyers")

    def validate_token_sync(self, token: str) -> None:
        """Validates a token synchronously against the FYERS API."""
        client_id = (settings.fyers_app_id or "").strip()
        client = fyersModel.FyersModel(
            is_async=False,
            client_id=client_id,
            token=token.strip(),
            log_path="",
        )
        self.logger.info("FYERS_REQUEST_STARTED | symbol=VALIDATE_TOKEN | endpoint=get_profile")
        request_start = time.time()
        try:
            with NetworkTimeoutContext(5.0):
                response = client.get_profile()
            duration_ms = int((time.time() - request_start) * 1000)
            self.logger.info("FYERS_REQUEST_COMPLETED | symbol=VALIDATE_TOKEN | endpoint=get_profile | duration_ms=%s | attempt=1", duration_ms)
        except Exception as exc:
            if isinstance(exc, (requests.exceptions.Timeout, TimeoutError)) or "timeout" in str(exc).lower():
                self.logger.warning("FYERS_REQUEST_TIMEOUT | symbol=VALIDATE_TOKEN | endpoint=get_profile | attempt=1 | timeout_sec=5.0")
            self.logger.error("FYERS_REQUEST_FAILED | symbol=VALIDATE_TOKEN | endpoint=get_profile | error_type=%s", type(exc).__name__)
            raise

        _check_fyers_response(response, "VALIDATE_TOKEN")

    async def fetch_ltp(self, symbol: str) -> float | None:
        cache_key = self._cache_symbol(symbol)
        
        # Helper to check DB cache
        async def _check_db():
            async with AsyncSessionLocal() as db:
                res = await db.execute(
                    text("SELECT ltp, updated_at FROM market_data.ltp_cache WHERE symbol = :s"),
                    {"s": cache_key}
                )
                row = res.mappings().first()
                if row:
                    cached_ltp = float(row["ltp"]) if row["ltp"] is not None else None
                    # Check TTL (15s)
                    updated_val = row["updated_at"]
                    if isinstance(updated_val, str):
                        from dateutil.parser import parse
                        updated_at = parse(updated_val).timestamp()
                    else:
                        updated_at = updated_val.timestamp()
                    if time.time() - updated_at < 15.0:
                        try:
                            fyers_logger.info("QUOTES CACHE_HIT | symbol=%s | ltp=%s | source=PG_CACHE", symbol, cached_ltp)
                        except Exception:
                            pass
                        FyersService._ltp_source_cache[cache_key] = "PG_CACHE"
                        return cached_ltp
            return False

        # 1. Fast path: check DB cache without lock
        cached = await _check_db()
        if cached is not False:
            return cached

        # 2. Acquire lock to prevent stampede
        import asyncio
        if cache_key not in FyersService._ltp_locks:
            FyersService._ltp_locks[cache_key] = asyncio.Lock()
            
        async with FyersService._ltp_locks[cache_key]:
            # 3. Double-check cache inside lock
            cached2 = await _check_db()
            if cached2 is not False:
                return cached2

            # 4. Fetch from FYERS API
            if self._is_fyers_configured():
                ltp = await self._fetch_fyers_ltp(symbol)
                if ltp is not None:
                    try:
                        fyers_logger.info("QUOTES | symbol=%s | ltp=%s | source=FYERS_PRIMARY", symbol, ltp)
                    except Exception:
                        pass
                    self.logger.info("Fetched live quote from FYERS | symbol=%s", symbol)
                    
                    # Update PostgreSQL Cache
                    async with AsyncSessionLocal() as db:
                        await db.execute(
                            text(f"""
                                INSERT INTO market_data.ltp_cache (symbol, ltp, updated_at)
                                VALUES (:s, :ltp, CURRENT_TIMESTAMP)
                                ON CONFLICT (symbol) DO UPDATE SET ltp = EXCLUDED.ltp, updated_at = EXCLUDED.updated_at
                            """),
                            {"s": cache_key, "ltp": float(ltp)}
                        )
                        await db.commit()
                    FyersService._ltp_source_cache[cache_key] = "FYERS_PRIMARY"
                    return ltp

            # 5. Store NULL / None in DB to prevent repeated API calls
            async with AsyncSessionLocal() as db:
                await db.execute(text(f"""
                    INSERT INTO market_data.ltp_cache (symbol, ltp, updated_at)
                    VALUES (:s, NULL, CURRENT_TIMESTAMP)
                    ON CONFLICT (symbol) DO UPDATE SET ltp = EXCLUDED.ltp, updated_at = EXCLUDED.updated_at
                """),
                {"s": cache_key}
                )
                await db.commit()
            FyersService._ltp_source_cache[cache_key] = "NO_DATA"
            return None

    def fetch_quote_profile(self, symbol: str) -> dict[str, object]:
        """Return best-effort symbol metadata from the FYERS quotes response.

        FYERS quotes are not a full fundamentals feed, so sector and market-cap may
        be absent. We still normalize any available name, description, and
        provider-specific 52-week or market-cap fields so the detail endpoint has
        one stable payload shape.
        """
        if not self._is_fyers_configured():
            return {}
        try:
            client = self._client()
            self.logger.info("FYERS_REQUEST_STARTED | symbol=%s | endpoint=quotes", symbol)
            request_start = time.time()
            with NetworkTimeoutContext(3.0):
                response = client.quotes(data={"symbols": self._normalize_symbol(symbol)})
            duration_ms = int((time.time() - request_start) * 1000)
            self.logger.info("FYERS_REQUEST_COMPLETED | symbol=%s | endpoint=quotes | duration_ms=%s | attempt=1", symbol, duration_ms)
            _check_fyers_response(response, symbol)
        except Exception as exc:  # pragma: no cover - provider/network failure
            if isinstance(exc, (requests.exceptions.Timeout, TimeoutError)) or "timeout" in str(exc).lower():
                self.logger.warning("FYERS_REQUEST_TIMEOUT | symbol=%s | endpoint=quotes | attempt=1 | timeout_sec=3.0", symbol)
            self.logger.error("FYERS_REQUEST_FAILED | symbol=%s | endpoint=quotes | error_type=%s", symbol, type(exc).__name__)
            return {}

        if not isinstance(response, dict):
            return {}
        quotes = response.get("d") or []
        if not quotes or not isinstance(quotes[0], dict):
            return {}

        value = quotes[0].get("v", {}) if isinstance(quotes[0].get("v", {}), dict) else {}
        raw = {**quotes[0], **value}

        def pick(*keys: str):
            for key in keys:
                if raw.get(key) not in (None, ""):
                    return raw.get(key)
            return None

        return {
            "company_name": pick("company_name", "companyName", "short_name", "shortName", "name", "symbol"),
            "company_description": pick("company_description", "description", "original_name", "originalName", "short_name"),
            "sector": pick("sector", "industry_sector"),
            "industry": pick("industry", "industry_group"),
            "market_cap": self._to_float(pick("market_cap", "marketCap", "marketCapitalization", "mcap")),
            "year52_high": self._to_float(pick("year52_high", "year52High", "52_week_high", "fiftyTwoWeekHigh")),
            "year52_low": self._to_float(pick("year52_low", "year52Low", "52_week_low", "fiftyTwoWeekLow")),
        }

    async def fetch_ohlcv(
        self,
        symbol: str,
        mode: AnalysisMode,
        resolution: str,
        lookback_window: int,
        allow_mock: bool = False,
    ) -> list[OHLCVPoint]:
        points = 40 if mode == AnalysisMode.intraday else max(lookback_window, 260)
        cache_key = (self._cache_symbol(symbol), mode.value, resolution.lower())
        
        import asyncio
        if cache_key not in FyersService._ohlcv_thread_locks:
            FyersService._ohlcv_thread_locks[cache_key] = asyncio.Lock()
                
        async with FyersService._ohlcv_thread_locks[cache_key]:
            cached = FyersService._ohlcv_cache.get(cache_key)
            now = time.time()
            # 300 second TTL for OHLCV memory cache
            if cached and cached[0] >= lookback_window and len(cached[1]) >= points and now < cached[2]:
                    cached_source = FyersService._ohlcv_source_cache.get(cache_key, "unknown")
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
                candles = await self._fetch_fyers_candles(symbol, resolution, lookback_window, points)
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
        return FyersService._ltp_source_cache.get(self._cache_symbol(symbol), "unknown")

    def get_ohlcv_source(
        self,
        symbol: str,
        mode: AnalysisMode,
        resolution: str,
    ) -> str:
        cache_key = (self._cache_symbol(symbol), mode.value, resolution.lower())
        return FyersService._ohlcv_source_cache.get(cache_key, "unknown")

    def _is_fyers_configured(self) -> bool:
        # Consider FYERS configured only when the SDK is available, app id is set,
        # and a manually-saved access token exists in the DB.
        if not fyersModel:
            self.logger.warning("FYERS_CONFIGURATION_CHECK | sdk_available=False")
            return False
        if not (settings.fyers_app_id and settings.fyers_app_id.strip()):
            self.logger.warning("FYERS_CONFIGURATION_CHECK | app_id_set=False")
            return False
        try:
            from .token_service import get_current_access_token_sync
            token, source = get_current_access_token_sync()
            if source == "database":
                self.logger.info("TOKEN_REFRESH_FROM_DB | FYERS configuration check rehydrated token from DB")
            is_configured = bool(token)
            if not is_configured:
                self.logger.warning("FYERS_CONFIGURATION_CHECK | has_valid_token=False")
            return is_configured
        except Exception as e:
            self.logger.error("FYERS_CONFIGURATION_CHECK | error=%s", e)
            return False

    def is_fyers_sdk_available(self) -> bool:
        return fyersModel is not None

    def has_fyers_credentials(self) -> bool:
        try:
            if not (settings.fyers_app_id and settings.fyers_app_id.strip()):
                return False
            from .token_service import get_current_access_token_sync
            token, _ = get_current_access_token_sync()
            return bool(token)
        except Exception:
            return False

    async def _fetch_fyers_ltp(self, symbol: str) -> float | None:
        import asyncio
        try:
            client = self._client()
            
            def fetch_quotes_with_timeout():
                with NetworkTimeoutContext(3.0):
                    return client.quotes(data={"symbols": self._normalize_symbol(symbol)})
                    
            self.logger.info("FYERS_REQUEST_STARTED | symbol=%s | endpoint=quotes", symbol)
            request_start = time.time()
            
            response = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(
                    FyersService._network_pool,
                    fetch_quotes_with_timeout
                ),
                timeout=5.0
            )
            response_ms = int((time.time() - request_start) * 1000)
            self.logger.info("FYERS_REQUEST_COMPLETED | symbol=%s | endpoint=quotes | duration_ms=%s | attempt=1", symbol, response_ms)
            _check_fyers_response(response, symbol)
        except Exception as exc:  # pragma: no cover - network/provider failure
            if isinstance(exc, (requests.exceptions.Timeout, TimeoutError, asyncio.TimeoutError)) or "timeout" in str(exc).lower():
                self.logger.warning("FYERS_REQUEST_TIMEOUT | symbol=%s | endpoint=quotes | attempt=1 | timeout_sec=3.0", symbol)
            self.logger.error("FYERS_REQUEST_FAILED | symbol=%s | endpoint=quotes | error_type=%s", symbol, type(exc).__name__)
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

    async def _fetch_fyers_candles(
        self,
        symbol: str,
        resolution: str,
        lookback_window: int,
        points: int,
    ) -> list[OHLCVPoint]:
        clean_symbol = self._cache_symbol(symbol)
        if self._is_blacklisted(symbol):
            self.logger.info("Skipping blacklisted symbol: %s", symbol)
            return []

        from .candle_store import (
            get_candle_count,
            get_last_stored_date,
            get_last_trading_day,
            has_completed_daily_session,
            is_cache_fresh,
            load_candles,
            save_candles,
        )
        import asyncio

        async def request_history(range_from: str, range_to: str) -> list[list[object]]:
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
            response = await asyncio.to_thread(self._request_history_with_retries, client, payload, symbol)
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
            import pytz
            client = self._client()
            today = datetime.now(pytz.timezone("Asia/Kolkata")).date()
            mapped_resolution = self._map_resolution(resolution)
            if mapped_resolution != "1D":
                # FYERS allows max 100 days for intraday. We cap at 90 to be safe.
                start_date = today - timedelta(days=min(lookback_window, 90))
                candle_rows = await request_history(start_date.isoformat(), today.isoformat())
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

            db_count = await get_candle_count(clean_symbol)
            last_date = await get_last_stored_date(clean_symbol)

            if db_count >= points and last_date is not None:
                candle_rows = await request_history(last_date, today.isoformat())
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
                    await save_candles(clean_symbol, new_rows)
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
                rows_1 = await request_history(range_1_from, range_1_to)
                rows_2 = await request_history(range_2_from, range_2_to)
                candle_rows = rows_1 + rows_2

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
                    await save_candles(clean_symbol, all_rows)
                    self.logger.info(
                        "OHLCV DB SAVE | symbol=%s | saved=%s",
                        symbol,
                        len(all_rows),
                    )
        except FyersInvalidSymbolError as exc:
            self.logger.warning("FYERS invalid symbol | symbol=%s | error=%s", symbol, exc)
            self._blacklist_symbol(symbol)
            return []
        except Exception as exc:  # pragma: no cover - network/provider failure
            self.logger.warning("FYERS history request failed | symbol=%s | resolution=%s | error=%s. Triggering yfinance fallback.", symbol, resolution, exc)
            fallback = self._fetch_yfinance_candles(symbol, lookback_window, points)
            if fallback:
                return fallback
            if not self._is_rate_limit_error(exc):
                self._blacklist_symbol(symbol)
            return []

        two_years_ago = (today - timedelta(days=730)).isoformat()
        db_rows = await load_candles(clean_symbol, two_years_ago)
        if not db_rows or len(db_rows) < points:
            fallback = self._fetch_yfinance_candles(symbol, lookback_window, points)
            if fallback:
                return fallback
            if not db_rows:
                self._blacklist_symbol(symbol)
                return []
        self.logger.info(
            "OHLCV SOURCE = POSTGRES_DB | symbol=%s | resolution=%s | candles=%s | db_count=%s | last_date=%s",
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

    async def get_candles_cached(
        self,
        symbol: str,
        mode: AnalysisMode,
        resolution: str,
        lookback_window: int,
        allow_mock: bool = False,
    ) -> list[OHLCVPoint]:
        """
        Returns candles using a local cache. Reads from cache when fresh,
        otherwise fetches from FYERS and stores into the cache.
        """
        points = 40 if mode == AnalysisMode.intraday else max(lookback_window, 260)
        mapped_resolution = self._map_resolution(resolution)

        # Only cache daily candles in this simple strategy
        if mapped_resolution == "1D":
            try:
                from . import candle_store
                import asyncio
            except Exception:
                # If the cache module is not available, fall back to live fetch
                self.logger.warning("CANDLE STORE not available, falling back to live fetch | symbol=%s", symbol)
                return await self.fetch_ohlcv(symbol, mode, resolution, lookback_window, allow_mock)


            clean_symbol = self._cache_symbol(symbol)

            cache_key = (clean_symbol, mode.value, resolution.lower())
            cache_reusable = await candle_store.is_cache_fresh(
                clean_symbol, max_age_minutes=cache_ttl_minutes
            ) or await candle_store.has_completed_daily_session(clean_symbol)
            if cache_reusable:
                # Ensure cached DB has sufficient rows for the requested `points`.
                try:
                    cached_count = await candle_store.get_candle_count(clean_symbol)
                except Exception:
                    cached_count = 0

                if cached_count >= points:
                    df = await candle_store.load_candles(clean_symbol)
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
                    self._ohlcv_source_cache[cache_key] = "CANDLE_CACHE_DB"
                    self.logger.info("CACHE HIT | symbol=%s | source=DB | candles=%s", symbol, len(parsed))
                    scan_ctx = get_current_scan()
                    if scan_ctx:
                        log_cache_lookup(scan_ctx, symbol=symbol, hit=True, available_candles=cached_count, required_candles=points)
                    return parsed[-points:]

                # Cached data is incomplete for the requested horizon -> treat as a miss
                self.logger.info(
                    "CACHE INCOMPLETE | symbol=%s | cached_rows=%s | required=%s | falling back to FYERS",
                    symbol,
                    cached_count,
                    points,
                )

            last_stored = await candle_store.get_last_stored_date(clean_symbol)
            self.logger.info(
                "CACHE MISS | symbol=%s | last_stored=%s | source=FYERS fetching now",
                symbol,
                last_stored,
            )
            scan_ctx = get_current_scan()
            if scan_ctx:
                log_cache_lookup(scan_ctx, symbol=symbol, hit=False, available_candles=0, required_candles=points)

            # Fetch from FYERS using existing logic (this may also populate the app-level ohlcv store)
            fetched = self._fetch_fyers_candles(symbol, resolution, lookback_window, points)

            if fetched:
                self._ohlcv_source_cache[cache_key] = "FYERS_PRIMARY"
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
                    await candle_store.store_candles(clean_symbol, df)
                    self.logger.info("CACHE STORED | symbol=%s | rows=%s", symbol, len(df))
                except Exception as exc:  # pragma: no cover - best-effort cache write
                    self.logger.warning("Failed to persist candles to cache | symbol=%s | error=%s", symbol, exc)

            return fetched

        # Non-daily resolutions: fall back to existing fetch behaviour
        return await self.fetch_ohlcv(symbol, mode, resolution, lookback_window, allow_mock)

    def _normalize_symbol(self, symbol: str) -> str:
        from ..utils.symbol import fyers_symbol, canonical_symbol
        return fyers_symbol(canonical_symbol(symbol))

    def _cache_symbol(self, symbol: str) -> str:
        from ..utils.symbol import canonical_symbol
        return canonical_symbol(symbol)

    def _store_ohlcv_cache(
        self,
        cache_key: tuple[str, str, str],
        lookback_window: int,
        candles: list[OHLCVPoint],
        source: str,
    ) -> None:
        cached = FyersService._ohlcv_cache.get(cache_key)
        if not cached or lookback_window >= cached[0]:
            FyersService._ohlcv_cache[cache_key] = (lookback_window, candles, time.time() + 300.0)
            FyersService._ohlcv_source_cache[cache_key] = source

    def _client(self):
        # Normalize client_id and token to avoid common mistakes where
        # the token is stored or passed with surrounding quotes or prefixed
        # with the app id (e.g. "APPID:ACCESS_TOKEN"). FyersModel expects
        # the raw access token only.
        client_id = (settings.fyers_app_id or "").strip().strip('"').strip("'")

        # Read token from DB (manual access token) via token_service helper.
        from . import token_service

        token, source = token_service.get_current_access_token_sync()
        if token:
            token = str(token).strip().strip('"').strip("'")
            self.logger.info("Scanner token loaded successfully. Token source used: %s", source)
        else:
            self.logger.error("Scanner token unavailable. Token source used: %s", source)

        if not token:
            self.logger.error("PRODUCTION_ALERT | category=TOKEN_MISSING | reason=Token unavailable or expired")
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

    def _request_history_with_retries(self, client, payload: dict[str, object], symbol: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, _FYERS_MAX_RETRIES + 1):
            scan_ctx = get_current_scan()
            self.logger.info("FYERS_REQUEST_STARTED | symbol=%s | endpoint=history | attempt=%s | timeout_sec=10.0", symbol, attempt)
            request_start = time.time()
            if scan_ctx:
                log_fyers_request(
                    scan_ctx,
                    symbol=symbol,
                    endpoint="history",
                    from_date=str(payload.get("range_from", "")),
                    to_date=str(payload.get("range_to", "")),
                    attempt=attempt,
                )
            with _FYERS_HISTORY_SEMAPHORE:
                try:
                    with NetworkTimeoutContext(10.0):
                        response = client.history(data=payload)
                    _check_fyers_response(response, symbol)
                    response_ms = int((time.time() - request_start) * 1000)
                    self.logger.info("FYERS_REQUEST_COMPLETED | symbol=%s | endpoint=history | duration_ms=%s | attempt=%s", symbol, response_ms, attempt)
                    candle_count = len(response.get("candles", [])) if isinstance(response, dict) else 0
                    if scan_ctx:
                        log_fyers_response(scan_ctx, symbol=symbol, candles_returned=candle_count, response_time_ms=response_ms)
                    return response if isinstance(response, dict) else {}
                except (FyersInvalidSymbolError, FyersAuthExpiredError, FyersAuthInvalidError):
                    raise
                except Exception as exc:
                    last_error = exc
                    duration_ms = int((time.time() - request_start) * 1000)
                    is_timeout = isinstance(exc, (requests.exceptions.Timeout, TimeoutError)) or "timeout" in str(exc).lower()
                    if is_timeout:
                        self.logger.warning("FYERS_REQUEST_TIMEOUT | symbol=%s | endpoint=history | attempt=%s | timeout_sec=10.0", symbol, attempt)
                        from .diagnostics_service import diagnostics
                        diagnostics.increment_fyers_metric("timeout_count")
                    
                    self.logger.error("FYERS_REQUEST_FAILED | symbol=%s | endpoint=history | error_type=%s | attempt=%s", symbol, type(exc).__name__, attempt)
                    
                    # Retry logic: retry on rate limits, connection errors, and timeouts.
                    if not (is_timeout or isinstance(exc, (ConnectionError, requests.exceptions.ConnectionError, requests.exceptions.RequestException, FyersRateLimitError))):
                        break
                    
                    if scan_ctx:
                        log_fyers_failure(scan_ctx, symbol=symbol, exception_type=type(exc).__name__, exception_message=str(exc), retry_count=attempt)

            if attempt < _FYERS_MAX_RETRIES:
                wait_seconds = 2 ** attempt  # Exponential backoff (2, 4, 8)
                from .diagnostics_service import diagnostics
                diagnostics.increment_fyers_metric("retry_count")
                self.logger.warning("FYERS_REQUEST_RETRY | symbol=%s | endpoint=history | attempt=%s | backoff_sec=%s | error=%s", symbol, attempt, wait_seconds, type(last_error).__name__)
                time.sleep(wait_seconds)

        raise last_error or FyersNetworkException(f"FYERS history failed for {symbol}")

    def _fetch_yfinance_candles(self, symbol: str, lookback_window: int, points: int) -> list[OHLCVPoint]:
        try:
            import pandas as pd
            import yfinance as yf

            yf_symbol = symbol.replace("NSE:", "").replace("-EQ", "") + ".NS"
            self.logger.info("YFINANCE FALLBACK | Fetching %s", yf_symbol)

            period_str = "2y" if lookback_window > 250 else "1y"
            df = yf.download(yf_symbol, period=period_str, interval="1d", progress=False)

            if df is None or df.empty:
                self.logger.warning("YFINANCE returned empty data for %s", symbol)
                return []

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            parsed: list[OHLCVPoint] = []
            for index, row in df.iterrows():
                dt = index
                if hasattr(dt, "to_pydatetime"):
                    dt = dt.to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                parsed.append(
                    OHLCVPoint(
                        timestamp=dt,
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=int(row["Volume"]),
                    )
                )
            self.logger.info("YFINANCE SUCCESS | symbol=%s | candles=%s", symbol, len(parsed))
            return parsed[-points:] if points else parsed
        except Exception as exc:
            if self._is_rate_limit_error(exc):
                self.logger.error("YFINANCE 429 Rate Limit hit for %s", symbol)
            else:
                self.logger.error("YFINANCE fallback failed for %s: %s", symbol, exc)
            return []

    def _is_blacklisted(self, symbol: str) -> bool:
        normalized = self._cache_symbol(symbol)
        with _BLACKLIST_LOCK:
            if normalized in QUARANTINED_SYMBOLS:
                if datetime.now(timezone.utc) < QUARANTINED_SYMBOLS[normalized]:
                    return True
                else:
                    del QUARANTINED_SYMBOLS[normalized]
            return False

    def _blacklist_symbol(self, symbol: str) -> None:
        normalized = self._cache_symbol(symbol)
        with _BLACKLIST_LOCK:
            QUARANTINED_SYMBOLS[normalized] = datetime.now(timezone.utc) + timedelta(hours=24)
        self.logger.warning("Symbol quarantined for 24h: %s", symbol)

    def _is_rate_limit_error(self, error: object) -> bool:
        error_str = str(error).lower()
        return isinstance(error, FyersRateLimitError) or "429" in error_str or "rate limit" in error_str or "too many requests" in error_str

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

    def _to_float(self, value: object) -> float | None:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def fetch_incremental_ohlcv(self, symbol: str, cached_candles: list[OHLCVPoint]) -> list[OHLCVPoint]:
        """
        Fetch only the latest missing daily candles from FYERS API.
        If cache is empty or too stale (stale > 5 days), do a full history backfill from FYERS directly.
        """
        import time
        from datetime import date, timedelta
        
        today_dt = date.today()

        if not cached_candles:
            # Empty cache, backfill last 365 days directly from FYERS without DB interaction here
            last_cached_dt = today_dt - timedelta(days=365)
        else:
            last_cached_dt = max(p.timestamp.date() for p in cached_candles)
            if last_cached_dt >= today_dt:
                return []
                
            days_diff = (today_dt - last_cached_dt).days
            if days_diff > 5:
                # Stale cache, backfill last 365 days
                last_cached_dt = today_dt - timedelta(days=365)

        self.logger.info("INCREMENTAL FETCH | symbol=%s | last_cached=%s | fetching missing candles", symbol, last_cached_dt)
        
        for retry_count in range(3):
            try:
                client = self._client()
                range_from_str = (last_cached_dt + timedelta(days=1)).isoformat()
                today_str = today_dt.isoformat()
                self.logger.debug("Normalizing symbol")
                normalized_sym = self._normalize_symbol(symbol)
                self.logger.debug("Symbol normalized")

                payload = {
                    "symbol": normalized_sym,
                    "resolution": "1D",
                    "date_format": "1",
                    "range_from": range_from_str,
                    "range_to": today_str,
                    "cont_flag": "1",
                }
                scan_ctx = get_current_scan()
                incr_start = time.time()
                response = self._request_history_with_retries(client, payload, symbol)
                candle_rows = response.get("candles", []) if isinstance(response, dict) else []
                incr_ms = int((time.time() - incr_start) * 1000)
                if scan_ctx:
                    log_fyers_response(scan_ctx, symbol=symbol, candles_returned=len(candle_rows), response_time_ms=incr_ms)
                
                fetched: list[OHLCVPoint] = []
                for row in candle_rows:
                    if len(row) < 6:
                        continue
                    fetched.append(
                        OHLCVPoint(
                            timestamp=self._parse_timestamp(row[0]),
                            open=float(row[1]),
                            high=float(row[2]),
                            low=float(row[3]),
                            close=float(row[4]),
                            volume=int(row[5]),
                        )
                    )
                
                return fetched
            except (FyersAuthExpiredError, FyersAuthInvalidError):
                raise
            except FyersInvalidSymbolError:
                self._blacklist_symbol(symbol)
                return []
            except (ModuleNotFoundError, ImportError):
                self.logger.exception("Import failure during incremental fetch")
                raise
            except Exception as exc:
                wait_time = 2 ** retry_count
                self.logger.warning("Network drop fetching incremental candle | symbol=%s | attempt=%s | wait=%ss | error=%s", symbol, retry_count + 1, wait_time, exc)
                time.sleep(wait_time)
        
        self.logger.error("All 3 attempts failed for incremental candle | symbol=%s", symbol)
        raise FyersNetworkException(f"Incremental fetch compromised after 3 retries for symbol: {symbol}")

    def combine_candles(self, cached: list[OHLCVPoint], new_candles: list[OHLCVPoint]) -> list[OHLCVPoint]:
        """Combine and deduplicate cached and new candles by timestamp date."""
        combined_map = {c.timestamp.date(): c for c in cached}
        for c in new_candles:
            combined_map[c.timestamp.date()] = c
        sorted_dates = sorted(combined_map.keys())
        return [combined_map[d] for d in sorted_dates]

    def encrypt_token(self, token: str) -> str:
        if not token:
            return token
        key = (settings.fyers_token_encryption_key or "").strip()
        if not key:
            self.logger.warning("No FYERS_TOKEN_ENCRYPTION_KEY set. Cannot encrypt refresh token.")
            return token
        try:
            from cryptography.fernet import Fernet
            f = Fernet(key.encode('utf-8'))
            return f.encrypt(token.encode('utf-8')).decode('utf-8')
        except Exception as e:
            self.logger.error("Failed to encrypt token: %s", str(e))
            raise ValueError(f"Encryption failed: {str(e)}")

    def decrypt_token(self, encrypted_token: str) -> str:
        if not encrypted_token:
            return encrypted_token
        key = (settings.fyers_token_encryption_key or "").strip()
        if not key:
            return encrypted_token
        try:
            from cryptography.fernet import Fernet
            f = Fernet(key.encode('utf-8'))
            return f.decrypt(encrypted_token.encode('utf-8')).decode('utf-8')
        except Exception as e:
            self.logger.error("Failed to decrypt token: %s", str(e))
            raise ValueError(f"Decryption failed: {str(e)}")

    async def save_tokens(self, access_token: str | None, refresh_token: str | None, db) -> dict:
        from .token_service import _set_token_cache
        from ..models import FyersToken, FyersTokenHistory
        from datetime import datetime, timedelta
        from sqlalchemy import select, update
        from fastapi import HTTPException
        import traceback
        
        print("[FYERS SERVICE] Starting combined token save...")
        now = datetime.utcnow()
        try:
            row = (await db.scalars(select(FyersToken).filter(FyersToken.id == 1))).one_or_none()
            
            if not row:
                await db.execute(update(FyersToken).values(is_active=False, status="inactive"))
                row = FyersToken(
                    id=1,
                    access_token=access_token or "",
                    created_at=now,
                    is_active=True,
                    status="active",
                )
            else:
                row.is_active = True
                row.status = "active"
                
            print("[FYERS SERVICE] Setting both access + refresh token on single row")
            if access_token:
                row.access_token = access_token
                row.access_token_saved_at = now
                row.validated_at = now
                
            if refresh_token:
                row.refresh_token = self.encrypt_token(refresh_token)
                row.refresh_token_expires_at = now + timedelta(days=15)
                row.last_auto_renewal_status = "saved"
                
            db.add(row)
            
            history = FyersTokenHistory(
                token_id=1,
                action="save_manual",
                status="active",
                note="Manual save via UI (access/refresh token merged)",
                access_token_masked=access_token[:4] + "***" if access_token else None
            )
            db.add(history)
            
            await db.commit()
            print("[FYERS SERVICE] Single db.commit() called")
            await db.refresh(row)
            
            if access_token:
                _set_token_cache(access_token, now)
                
            if refresh_token:
                print("[FYERS SERVICE] Auto-generating access token from refresh token...")
                auto_result = await self.auto_refresh_access_token(db)
                if auto_result.get("status") != "ok":
                    return auto_result
                    
            return {"status": "ok", "saved_at": str(now), "token_id": row.id}
            
        except Exception as e:
            print(f"[FYERS SERVICE ERROR] {e}")
            traceback.print_exc()
            await db.rollback()
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(status_code=400, detail=str(e))

    async def get_token_status_with_refresh_info(self, db) -> dict:
        from .token_service import get_fyers_token_row
        from datetime import datetime
        
        row = await get_fyers_token_row(db)
        status = {
            "has_token": bool(row and row.access_token),
            "access_token_active": bool(row and row.access_token),
            "created_at": row.access_token_saved_at.isoformat() if row and row.access_token_saved_at else None,
            "access_token_saved_at": row.access_token_saved_at.isoformat() if row and row.access_token_saved_at else None,
            "validated_at": getattr(row, 'validated_at', None).isoformat() if row and getattr(row, 'validated_at', None) else None,
            "is_active": bool(row and row.is_active),
            "status": row.status if row else "no_token",
            "last_error": row.last_error if row else None,
            "has_refresh_token": bool(row and row.refresh_token),
            "refresh_token_expires_at": row.refresh_token_expires_at.isoformat() if row and row.refresh_token_expires_at else None,
            "refresh_token_days_remaining": None,
            "last_auto_renewal_at": row.last_auto_renewal_at.isoformat() if row and row.last_auto_renewal_at else None,
            "last_auto_renewal_status": row.last_auto_renewal_status if row else None,
        }
        
        if row and row.refresh_token_expires_at:
            delta = row.refresh_token_expires_at - datetime.utcnow()
            days = delta.days
            # Add partial days as full days if > 0
            if delta.total_seconds() > 0 and (delta.total_seconds() % 86400) > 0:
                days += 1
            days = max(0, days)
            status["refresh_token_days_remaining"] = days
            status["refresh_token_status"] = FyersService.compute_refresh_token_status(days)
        else:
            status["refresh_token_status"] = "expired"
            
        return status
        
    @staticmethod
    def compute_refresh_token_status(days: int) -> str:
        if days > 7:
            return "valid"
        elif days > 3:
            return "expiring_soon"
        elif days > 0:
            return "critical"
        return "expired"
    def _compute_app_id_hash(self) -> str:
        import hashlib
        app_id = (settings.fyers_app_id or "").strip()
        secret_id = (settings.fyers_secret_id or "").strip()
        if not app_id or not secret_id:
            raise ValueError("FYERS_APP_ID or FYERS_SECRET_ID is missing")
        return hashlib.sha256(f"{app_id}:{secret_id}".encode('utf-8')).hexdigest()

    async def auto_refresh_access_token(self, db) -> dict:
        from .token_service import get_fyers_token_row, _set_token_cache
        import httpx
        from datetime import datetime
        import traceback
        
        row = await get_fyers_token_row(db)
        if not row or not row.refresh_token:
            self.logger.warning("Auto-refresh skipped: No active token or refresh token found.")
            return {"status": "skipped", "message": "No refresh token available"}
            
        pin = (settings.fyers_pin or "").strip()
        if not pin or len(pin) != 4 or not pin.isdigit():
            self.logger.error("Auto-refresh failed: FYERS_PIN must be exactly 4 numeric digits.")
            await self._handle_refresh_failure("FYERS_PIN invalid or missing")
            return {"status": "error", "message": "FYERS_PIN invalid or missing"}

        try:
            app_id_hash = self._compute_app_id_hash()
        except ValueError as e:
            self.logger.error("Auto-refresh failed: %s", str(e))
            await self._handle_refresh_failure(str(e))
            return {"status": "error", "message": str(e)}

        decrypted_refresh_token = self.decrypt_token(row.refresh_token)
        
        payload = {
            "grant_type": "refresh_token",
            "appIdHash": app_id_hash,
            "refresh_token": decrypted_refresh_token,
            "pin": pin
        }
        
        url = "https://api-t1.fyers.in/api/v3/validate-refresh-token"
        self.logger.info("Attempting auto-refresh of FYERS access token...")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                print(f"[FYERS SERVICE] Fyers API response status: {response.status_code}")
                data = response.json()
                
            if response.status_code == 200 and data.get("s") == "ok":
                new_access_token = data.get("access_token")
                if not new_access_token:
                    raise ValueError("FYERS API did not return an access_token")
                
                row = await get_fyers_token_row(db)
                if row:
                    refreshed_at = datetime.utcnow()
                    row.access_token = new_access_token
                    row.access_token_saved_at = refreshed_at
                    row.last_auto_renewal_at = refreshed_at
                    row.last_auto_renewal_status = "success"
                    row.last_error = None
                    db.add(row)
                    await db.commit()
                    await db.refresh(row)
                
                _set_token_cache(new_access_token, datetime.utcnow())
                print("[FYERS SERVICE] New access token saved to DB")
                self.logger.info("Auto-refresh successful.")
                return {"status": "ok", "message": "Token refreshed successfully"}
            else:
                error_message = data.get("message", "Unknown error from FYERS API")
                self.logger.error("Auto-refresh failed from API: %s", error_message)
                
                row = await get_fyers_token_row(db)
                if row:
                    row.last_auto_renewal_at = datetime.utcnow()
                    row.last_auto_renewal_status = "error"
                    row.last_error = error_message
                    db.add(row)
                    await db.commit()
                    
                await self._handle_refresh_failure(error_message)
                return {"status": "error", "message": error_message}
                
        except Exception as e:
            print(f"[FYERS SERVICE ERROR] {e}")
            traceback.print_exc()
            self.logger.error("Network or parsing error during auto-refresh: %s", str(e))
            try:
                await db.rollback()
                row = await get_fyers_token_row(db)
                if row:
                    row.last_auto_renewal_at = datetime.utcnow()
                    row.last_auto_renewal_status = "error"
                    row.last_error = str(e)
                    db.add(row)
                    await db.commit()
            except Exception:
                await db.rollback()
                
            await self._handle_refresh_failure(str(e))
            return {"status": "error", "message": str(e)}

    async def _handle_refresh_failure(self, reason: str):
        from .market_engine_service import MarketEngineService
        from ..db.session import AsyncSessionLocal
        from sqlalchemy import text
        from datetime import datetime
        
        try:
            await MarketEngineService().request_stop()
            self.logger.warning("Market engine paused due to refresh token failure.")
        except Exception as e:
            self.logger.error("Failed to pause market engine: %s", str(e))
            
        try:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await db.execute(text("""
                        INSERT INTO paper_trading_notifications (account_id, message, level, event_type, source, created_at, is_read)
                        VALUES (1, :msg, 'error', 'TOKEN_EXPIRED', 'system', :now, false)
                    """), {"msg": f"FYERS token auto-renewal failed: {reason}. Market engine has been paused.", "now": datetime.utcnow()})
        except Exception as e:
            self.logger.error("Failed to dispatch notification: %s", str(e))
