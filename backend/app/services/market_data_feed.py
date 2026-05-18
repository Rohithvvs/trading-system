from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from threading import Lock, Thread
from typing import Any

from ..services.token_service import get_current_access_token
from ..db.session import SessionLocal
from ..utils import get_logger

try:
    from fyers_apiv3.FyersWebsocket import data_ws
except ImportError:  # pragma: no cover
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

    def start(self) -> None:
        if data_ws is None:
            self.on_error("FYERS websocket SDK unavailable.")
            return
        token = self._read_token()
        if not token:
            self.on_error("No FYERS token configured.")
            return
        if self._thread and self._thread.is_alive():
            return

        def on_message(message: dict[str, Any]) -> None:
            symbol = str(message.get("symbol") or message.get("s") or "").replace("NSE:", "")
            raw_price = message.get("ltp") or message.get("lp")
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                return
            if symbol:
                self.on_tick(symbol, price)

        def on_error(message: Any) -> None:
            self.logger.warning("FYERS websocket error | message=%s", message)
            self.connected = False
            self.on_connection_change(False)
            self.on_error(str(message))

        def on_connect() -> None:
            self.connected = True
            self.on_connection_change(True)
            with self._lock:
                symbols = sorted(self._symbols)
            if symbols and self._socket is not None:
                self._socket.subscribe(symbols=[self._normalize_symbol(s) for s in symbols], data_type="SymbolUpdate")
                self._socket.keep_running()

        def on_close(message: Any) -> None:
            self.logger.info("FYERS websocket closed | message=%s", message)
            self.connected = False
            self.on_connection_change(False)

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

    def stop(self, notify: bool = True) -> None:
        socket = self._socket
        if socket is not None:
            try:
                socket.close_connection()
            except Exception:
                self.logger.exception("Failed to close FYERS websocket cleanly")
        self.connected = False
        if notify:
            self.on_connection_change(False)

    def sync_symbols(self, symbols: set[str]) -> None:
        with self._lock:
            previous = set(self._symbols)
            self._symbols = set(symbols)
        if not self.connected or self._socket is None:
            return
        to_add = sorted(symbols - previous)
        to_remove = sorted(previous - symbols)
        if to_add:
            self._socket.subscribe(symbols=[self._normalize_symbol(s) for s in to_add], data_type="SymbolUpdate")
        if to_remove:
            self._socket.unsubscribe(symbols=[self._normalize_symbol(s) for s in to_remove], data_type="SymbolUpdate")

    def _read_token(self) -> str | None:
        with SessionLocal() as db:
            token = get_current_access_token(db)
        return str(token) if token else None

    def _normalize_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        return normalized if ":" in normalized else f"NSE:{normalized}"
