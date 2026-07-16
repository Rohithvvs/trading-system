from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any
import time

from ..utils import get_logger

try:
    from fyers_apiv3.FyersWebsocket import data_ws
except ImportError:
    data_ws = None


class FyersMarketDataFeed:
    """Thin WebSocket adapter. Trading decisions stay outside this class."""

    def __init__(
        self,
        on_tick: Callable[[str, float], None],
        on_error: Callable[[str], None],
        on_connection_change: Callable[[bool], None],
    ) -> None:
        self.on_tick = on_tick
        self.on_error = on_error
        self.on_connection_change = on_connection_change
        self.logger = get_logger("app.market_data_feed")
        self._socket: Any | None = None
        self._thread: Thread | None = None
        self._symbols: set[str] = set()
        self._lock = Lock()
        self.connected = False
        self._last_tick_at: float = 0.0
        self._started_at: float = 0.0

    def start(self, token: str) -> None:
        if data_ws is None:
            self.on_error("FYERS websocket SDK unavailable.")
            return
        if not token:
            self.on_error("No FYERS token configured.")
            return

        with self._lock:
            if self._thread and self._thread.is_alive():
                self.logger.info("WebSocket thread already alive, skipping start")
                return

            self._socket = None
            self._thread = None
            self.connected = False

        def on_message(message: dict[str, Any]) -> None:
            if isinstance(message, dict) and message.get("s") == "ok" and len(message) == 1:
                return
            payload = {}
            if "symbol" in message:
                payload["s"] = message["symbol"]
            elif "s" in message:
                payload["s"] = message["s"]
            if "ltp" in message:
                payload["lp"] = message["ltp"]
            elif "lp" in message:
                payload["lp"] = message["lp"]
            if payload.get("lp") is not None:
                self._last_tick_at = time.time()

            from ..schemas.paper_trading import FyersTickPayload
            from pydantic import ValidationError
            try:
                tick = FyersTickPayload(**payload)
            except ValidationError as e:
                self.logger.warning("Invalid FYERS tick payload dropped: %s | error: %s", payload, e.errors()[0]['msg'])
                return
            if tick.symbol:
                self.on_tick(tick.symbol, tick.ltp)

        def on_error(message: Any) -> None:
            self.logger.warning("FYERS websocket error | message=%s", message)
            self.connected = False
            self.on_connection_change(False)
            self.on_error(str(message))

        def on_connect() -> None:
            self.connected = True
            self._started_at = time.time()
            self.on_connection_change(True)
            with self._lock:
                symbols = sorted(self._symbols)
            if symbols and self._socket is not None:
                normalized = [self._normalize_symbol(s) for s in symbols]
                self.logger.info("WEB_SOCKET_SUBSCRIBE | symbols=%s", normalized)
                self._socket.subscribe(symbols=normalized, data_type="SymbolUpdate")
                self._socket.keep_running()

        def on_close(message: Any) -> None:
            self.logger.info("FYERS websocket closed | message=%s", message)
            self.connected = False
            self.on_connection_change(False)

        with self._lock:
            self._socket = data_ws.FyersDataSocket(
                access_token=token,
                write_to_file=False,
                log_path="",
                litemode=True,
                reconnect=True,
                on_message=on_message,
                on_error=on_error,
                on_connect=on_connect,
                on_close=on_close,
            )
            self._thread = Thread(target=self._socket.connect, name="fyers-data-feed", daemon=True)
            self._thread.start()
            self.logger.info("WEB_SOCKET_STARTED | thread=%s", self._thread.name)

    def stop(self, notify: bool = True) -> None:
        socket = self._socket
        if socket is not None:
            try:
                socket.close_connection()
            except Exception:
                self.logger.exception("Failed to close FYERS websocket cleanly")
        self._socket = None
        self._thread = None
        self.connected = False
        self._last_tick_at = 0.0
        if notify:
            self.on_connection_change(False)

    def restart(self, token: str) -> None:
        self.stop(notify=False)
        self.start(token)

    def sync_symbols(self, symbols: set[str]) -> None:
        with self._lock:
            previous = set(self._symbols)
            self._symbols = set(symbols)
        if not self.connected or self._socket is None:
            return
        to_add = sorted(symbols - previous)
        to_remove = sorted(previous - symbols)
        if to_add:
            normalized = [self._normalize_symbol(s) for s in to_add]
            self.logger.info("WEB_SOCKET_SUBSCRIBE_DELTA | add=%s", normalized)
            self._socket.subscribe(symbols=normalized, data_type="SymbolUpdate")
        if to_remove:
            normalized = [self._normalize_symbol(s) for s in to_remove]
            self.logger.info("WEB_SOCKET_UNSUBSCRIBE | remove=%s", normalized)
            self._socket.unsubscribe(symbols=normalized, data_type="SymbolUpdate")

    @property
    def is_stale(self) -> bool:
        if not self.connected:
            return True
        if self._last_tick_at == 0:
            return time.time() - self._started_at > 30
        return time.time() - self._last_tick_at > 60

    def health(self) -> dict:
        return {
            "connected": self.connected,
            "symbols": len(self._symbols),
            "thread_alive": self._thread is not None and self._thread.is_alive(),
            "last_tick_ago": int(time.time() - self._last_tick_at) if self._last_tick_at > 0 else None,
        }

    def _normalize_symbol(self, symbol: str) -> str:
        from ..utils.symbol import fyers_symbol, canonical_symbol
        return fyers_symbol(canonical_symbol(symbol))
