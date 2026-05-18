from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from ..db.session import SessionLocal
from ..models.paper_trading import ExecutionEvent, MarketEngineSession, PaperOrder, PaperPosition
from ..services.fyers_service import FyersAuthExpiredError, FyersAuthInvalidError, FyersService
from ..services.market_data_feed import FyersMarketDataFeed
from ..services.paper_trading_service import PaperTradingService
from ..utils import get_logger


IST = ZoneInfo("Asia/Kolkata")
ACTIVE_ORDER_STATES = {"PENDING_ENTRY", "MARKET_CLOSED_WAITING", "ERROR_RETRYING", "TOKEN_EXPIRED_PAUSED"}
ACTIVE_POSITION_STATES = {"OPEN_POSITION", "MARKET_CLOSED_WAITING", "ERROR_RETRYING", "TOKEN_EXPIRED_PAUSED"}


class MarketEngineService:
    def __init__(self) -> None:
        self.logger = get_logger("app.market_engine")
        self.fyers = FyersService()
        self.latest_ltp: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        self._feed = FyersMarketDataFeed(self._on_tick, self._on_feed_error, self._on_connection_change)

    async def start_loop(self) -> None:
        if self._task and not self._task.done():
            self.logger.info("Market engine loop already running; start is idempotent")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="market-engine-loop")
        self.logger.info("Market engine loop started")

    async def shutdown(self) -> None:
        if not self._running and (self._task is None or self._task.done()):
            self.logger.info("Market engine loop already stopped; shutdown is idempotent")
            return
        self._running = False
        self._feed.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.logger.info("Market engine loop stopped")

    def request_start(self) -> MarketEngineSession:
        with SessionLocal() as db:
            session = self._get_or_create_session(db)
            session.status = "STARTING"
            session.requested_start_at = datetime.utcnow()
            session.paused_reason = None
            db.commit()
            db.refresh(session)
            self.logger.info("Market engine start requested | session_id=%s", session.id)
            return session

    def request_stop(self) -> MarketEngineSession:
        with SessionLocal() as db:
            session = self._get_or_create_session(db)
            session.status = "STOPPED"
            session.stopped_at = datetime.utcnow()
            session.websocket_connected = False
            db.commit()
            db.refresh(session)
            self.logger.info("Market engine stop requested | session_id=%s", session.id)
        self._feed.stop()
        return session

    def heartbeat(self) -> None:
        with SessionLocal() as db:
            session = self._get_or_create_session(db)
            session.last_heartbeat_at = datetime.utcnow()
            db.commit()
            self.logger.info("Market engine heartbeat recorded | session_id=%s", session.id)

    def status(self) -> dict:
        with SessionLocal() as db:
            session = self._get_or_create_session(db)
            symbols = sorted(self._desired_symbols(db))
            return {
                "status": session.status,
                "market_hours_active": self.is_market_hours(),
                "websocket_connected": bool(session.websocket_connected),
                "token_status": session.token_status,
                "paused_reason": session.paused_reason,
                "last_heartbeat_at": session.last_heartbeat_at,
                "last_tick_at": session.last_tick_at,
                "active_monitored_symbols_count": len(symbols),
                "active_symbols": symbols,
                "trading_date": session.trading_date,
            }

    async def _run_loop(self) -> None:
        while self._running:
            try:
                with SessionLocal() as db:
                    session = self._get_or_create_session(db)
                    if session.status in {"STARTING", "RUNNING", "PAUSED_TOKEN_EXPIRED", "WAITING_MARKET_OPEN"}:
                        self._reconcile_session(db, session)
                    db.commit()
            except Exception:
                self.logger.exception("Market engine loop failed")
            await asyncio.sleep(2)

    def _reconcile_session(self, db, session: MarketEngineSession) -> None:
        if not self.is_market_hours():
            if session.status != "WAITING_MARKET_OPEN":
                self.logger.info("Market closed; engine waiting for next session")
            session.status = "WAITING_MARKET_OPEN"
            session.websocket_connected = False
            self._set_market_closed_waiting(db)
            self._feed.stop(notify=False)
            return

        try:
            desired = self._desired_symbols(db)
            session.monitored_symbols_count = len(desired)
            self._resume_active_models(db)
            self._feed.sync_symbols(desired)
            if desired:
                self._feed.start()
            session.status = "RUNNING"
            session.token_status = "VALID"
            session.paused_reason = None
            if session.started_at is None:
                session.started_at = datetime.utcnow()
            self._poll_missing_prices(db, desired)
        except (FyersAuthExpiredError, FyersAuthInvalidError):
            self._pause_for_token(db, session)
        except Exception:
            self.logger.exception("Market engine reconcile failed")
            session.status = "ERROR_RETRYING"

    def _poll_missing_prices(self, db, symbols: set[str]) -> None:
        for symbol in symbols:
            if symbol in self.latest_ltp:
                continue
            ltp = self.fyers.fetch_ltp(symbol)
            if ltp is not None:
                self._process_symbol(db, symbol, ltp)

    def _on_tick(self, symbol: str, price: float) -> None:
        normalized = symbol.replace("NSE:", "").upper()
        self.latest_ltp[normalized] = price
        with SessionLocal() as db:
            self._process_symbol(db, normalized, price)
            session = self._get_or_create_session(db)
            session.last_tick_at = datetime.utcnow()
            db.commit()

    def _process_symbol(self, db, symbol: str, price: float) -> None:
        service = PaperTradingService(db)
        orders = list(
            db.scalars(
                select(PaperOrder).where(
                    PaperOrder.symbol == symbol,
                    PaperOrder.lifecycle_state.in_(ACTIVE_ORDER_STATES),
                    PaperOrder.status == "PENDING",
                    PaperOrder.monitor_enabled.is_(True),
                )
            )
        )
        for order in orders:
            prior = order.lifecycle_state
            order.last_seen_ltp = price
            order.last_evaluated_at = datetime.utcnow()
            account = service._get_or_create_account()
            filled_order, position, _, _ = service._try_fill_order(account, order, price)
            if filled_order.status == "FILLED":
                filled_order.lifecycle_state = "ENTRY_FILLED"
                if position:
                    position.lifecycle_state = "OPEN_POSITION"
                self.logger.info("Entry filled | order_id=%s symbol=%s price=%s", order.id, symbol, price)
                self._record_event(
                    db,
                    "ENTRY_FILLED",
                    symbol,
                    order.id,
                    getattr(position, "id", None),
                    prior,
                    "ENTRY_FILLED",
                    price,
                    dedupe_key=f"entry-filled:{order.id}",
                )
                service.add_notification(
                    account.id,
                    f"{symbol} paper buy auto-filled at Rs {round(price, 2)}.",
                    "success",
                    "ENTRY_FILLED",
                    "order",
                    order.id,
                    dedupe_key=f"entry-filled:{order.id}",
                    commit=False,
                )

        positions = list(
            db.scalars(
                select(PaperPosition).where(
                    PaperPosition.symbol == symbol,
                    PaperPosition.lifecycle_state.in_(ACTIVE_POSITION_STATES),
                    PaperPosition.status == "OPEN",
                    PaperPosition.monitor_enabled.is_(True),
                )
            )
        )
        for position in positions:
            if position.target is not None and price >= position.target:
                self.logger.info("Target hit | position_id=%s symbol=%s price=%s", position.id, symbol, price)
                service.auto_exit(position.id, price, "TARGET_HIT")
                self._record_event(db, "EXIT_FILLED", symbol, None, position.id, "OPEN_POSITION", "EXIT_FILLED", price, dedupe_key=f"exit-filled:{position.id}:TARGET_HIT")
            elif position.stop_loss is not None and price <= position.stop_loss:
                self.logger.info("Stop loss hit | position_id=%s symbol=%s price=%s", position.id, symbol, price)
                service.auto_exit(position.id, price, "STOPLOSS_HIT")
                self._record_event(db, "EXIT_FILLED", symbol, None, position.id, "OPEN_POSITION", "EXIT_FILLED", price, dedupe_key=f"exit-filled:{position.id}:STOPLOSS_HIT")

    def _desired_symbols(self, db) -> set[str]:
        order_symbols = set(
            db.scalars(
                select(PaperOrder.symbol).where(
                    PaperOrder.status == "PENDING",
                    PaperOrder.lifecycle_state.in_(ACTIVE_ORDER_STATES),
                    PaperOrder.monitor_enabled.is_(True),
                )
            )
        )
        position_symbols = set(
            db.scalars(
                select(PaperPosition.symbol).where(
                    PaperPosition.status == "OPEN",
                    PaperPosition.lifecycle_state.in_(ACTIVE_POSITION_STATES),
                    PaperPosition.monitor_enabled.is_(True),
                )
            )
        )
        return {s for s in order_symbols | position_symbols if s}

    def _set_market_closed_waiting(self, db) -> None:
        for order in db.scalars(select(PaperOrder).where(PaperOrder.status == "PENDING")):
            if order.lifecycle_state in ACTIVE_ORDER_STATES:
                order.lifecycle_state = "MARKET_CLOSED_WAITING"
        for position in db.scalars(select(PaperPosition).where(PaperPosition.status == "OPEN")):
            if position.lifecycle_state in ACTIVE_POSITION_STATES:
                position.lifecycle_state = "MARKET_CLOSED_WAITING"

    def _resume_active_models(self, db) -> None:
        for order in db.scalars(select(PaperOrder).where(PaperOrder.status == "PENDING")):
            if order.lifecycle_state in {"MARKET_CLOSED_WAITING", "ERROR_RETRYING", "TOKEN_EXPIRED_PAUSED"}:
                order.lifecycle_state = "PENDING_ENTRY"
                order.paused_reason = None
        for position in db.scalars(select(PaperPosition).where(PaperPosition.status == "OPEN")):
            if position.lifecycle_state in {"MARKET_CLOSED_WAITING", "ERROR_RETRYING", "TOKEN_EXPIRED_PAUSED"}:
                position.lifecycle_state = "OPEN_POSITION"
                position.paused_reason = None

    def _pause_for_token(self, db, session: MarketEngineSession) -> None:
        already_paused = session.status == "PAUSED_TOKEN_EXPIRED"
        session.status = "PAUSED_TOKEN_EXPIRED"
        session.token_status = "EXPIRED"
        session.paused_reason = "TOKEN_EXPIRED"
        session.websocket_connected = False
        account = PaperTradingService(db)._get_or_create_account()
        for order in db.scalars(select(PaperOrder).where(PaperOrder.status == "PENDING")):
            order.lifecycle_state = "TOKEN_EXPIRED_PAUSED"
            order.paused_reason = "TOKEN_EXPIRED"
        for position in db.scalars(select(PaperPosition).where(PaperPosition.status == "OPEN")):
            position.lifecycle_state = "TOKEN_EXPIRED_PAUSED"
            position.paused_reason = "TOKEN_EXPIRED"
        if not already_paused:
            self.logger.warning("Token expired; monitoring paused | session_id=%s", session.id)
        PaperTradingService(db).add_notification(
            account.id,
            "FYERS token expired; monitoring paused.",
            "error",
            "TOKEN_EXPIRED",
            "engine",
            session.id,
            dedupe_key=f"token-expired:{session.id}",
            commit=False,
        )
        self._feed.stop(notify=False)

    def _on_feed_error(self, message: str) -> None:
        if "expired" in message.lower():
            with SessionLocal() as db:
                session = self._get_or_create_session(db)
                self._pause_for_token(db, session)
                db.commit()
            return
        with SessionLocal() as db:
            session = self._get_or_create_session(db)
            session.status = "ERROR_RETRYING"
            session.websocket_connected = False
            account = PaperTradingService(db)._get_or_create_account()
            PaperTradingService(db).add_notification(
                account.id,
                "Live market feed disconnected; monitoring degraded while retrying.",
                "error",
                "WEBSOCKET_DISCONNECTED",
                "engine",
                session.id,
                dedupe_key=f"feed-disconnected:{session.id}",
                commit=False,
            )
            db.commit()

    def _on_connection_change(self, connected: bool) -> None:
        try:
            with SessionLocal() as db:
                session = self._get_or_create_session(db)
                self.logger.info("Websocket connection state changed | connected=%s", connected)
                session.websocket_connected = connected
                db.commit()
        except Exception:
            self.logger.exception("Failed to persist websocket state change | connected=%s", connected)

    def _record_event(
        self,
        db,
        event_type: str,
        symbol: str | None,
        order_id: int | None,
        position_id: int | None,
        from_state: str | None,
        to_state: str | None,
        price: float | None,
        dedupe_key: str | None = None,
    ) -> None:
        if dedupe_key:
            for pending in db.new:
                if isinstance(pending, ExecutionEvent) and pending.dedupe_key == dedupe_key:
                    return
            existing = db.scalar(select(ExecutionEvent).where(ExecutionEvent.dedupe_key == dedupe_key))
            if existing:
                return
        db.add(
            ExecutionEvent(
                event_type=event_type,
                symbol=symbol,
                order_id=order_id,
                position_id=position_id,
                from_state=from_state,
                to_state=to_state,
                price=price,
                dedupe_key=dedupe_key,
            )
        )

    def _get_or_create_session(self, db) -> MarketEngineSession:
        today = datetime.now(IST).date().isoformat()
        session = db.scalar(select(MarketEngineSession).where(MarketEngineSession.trading_date == today))
        if session:
            return session
        session = MarketEngineSession(trading_date=today, status="STOPPED")
        db.add(session)
        db.flush()
        return session

    def is_market_hours(self, now: datetime | None = None) -> bool:
        local = (now or datetime.now(timezone.utc)).astimezone(IST)
        if local.weekday() >= 5:
            return False
        return time(9, 0) <= local.time() <= time(16, 0)


market_engine = MarketEngineService()
