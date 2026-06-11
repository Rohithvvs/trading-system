from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select


from ..models.paper_trading import ExecutionEvent, MarketEngineSession, PaperOrder, PaperPosition
from ..services.token_service import get_current_access_token
from ..services.fyers_service import FyersAuthExpiredError, FyersAuthInvalidError, FyersService
from ..services.market_data_feed import FyersMarketDataFeed
from ..db.session import AsyncSessionLocal, SessionLocal
from ..services.paper_trading_service import PaperTradingService
from ..utils import get_logger


IST = ZoneInfo("Asia/Kolkata")
ACTIVE_ORDER_STATES = {"PENDING_ENTRY"}
ACTIVE_POSITION_STATES = {"OPEN_POSITION"}


class MarketEngineService:
    def __init__(self) -> None:
        self.logger = get_logger("app.market_engine")
        self.fyers = FyersService()
        self.latest_ltp: dict[str, float] = {}
        self._active_positions_cache: dict[str, list[PaperPosition]] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        self._feed = FyersMarketDataFeed(
            self._sync_on_tick, 
            self._sync_on_feed_error, 
            self._sync_on_connection_change
        )
        self._loop = None

    def _sync_on_tick(self, symbol: str, price: float):
        if self._loop and self._running:
            asyncio.run_coroutine_threadsafe(self._on_tick(symbol, price), self._loop)

    def _sync_on_feed_error(self, message: str | Exception):
        if self._loop and self._running:
            asyncio.run_coroutine_threadsafe(self._on_feed_error(message), self._loop)

    def _sync_on_connection_change(self, connected: bool):
        if self._loop and self._running:
            asyncio.run_coroutine_threadsafe(self._on_connection_change(connected), self._loop)

    async def start_loop(self) -> None:
        if self._task and not self._task.done():
            self.logger.info("Market engine loop already running; start is idempotent")
            return
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._run_loop(), name="market-engine-loop")
        self.logger.info("MARKET_ENGINE_STARTED | Market engine loop started")

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
        self.logger.info("MARKET_ENGINE_STOPPED | Market engine loop stopped")

    async def request_start(self) -> MarketEngineSession:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                session = await self._get_or_create_session(db)
                session.status = "STARTING"
                session.requested_start_at = datetime.utcnow()
                session.paused_reason = None
                await db.refresh(session)
                self.logger.info("Market engine start requested | session_id=%s", session.id)
                return session

    async def request_stop(self) -> MarketEngineSession:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                session = await self._get_or_create_session(db)
                session.status = "STOPPED"
                session.stopped_at = datetime.utcnow()
                session.websocket_connected = False
                await db.refresh(session)
                self.logger.info("Market engine stop requested | session_id=%s", session.id)
        self._feed.stop()
        return session

    async def heartbeat(self) -> None:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                session = await self._get_or_create_session(db)
                session.last_heartbeat_at = datetime.utcnow()
                
                # Try to load symbols/positions for logging
                try:
                    positions_count = len((await db.scalars(select(PaperPosition.id).where(PaperPosition.status == "OPEN"))).all())
                    symbols_count = len(await self._desired_symbols(db))
                except Exception:
                    positions_count = 0
                    symbols_count = 0
                
                self.logger.info("MARKET_ENGINE_HEARTBEAT | session_id=%s | active_positions=%s | subscribed_symbols=%s", session.id, positions_count, symbols_count)

    async def status(self) -> dict:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                session = await self._get_or_create_session(db)
                symbols = sorted(await self._desired_symbols(db))
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
                async with AsyncSessionLocal() as db:
                    async with db.begin():
                        session = await self._get_or_create_session(db)
                        if session.status in {"STARTING", "RUNNING", "PAUSED_TOKEN_EXPIRED", "WAITING_MARKET_OPEN"}:
                            if session.status == "ERROR_RETRYING":
                                session.status = "RUNNING"
                                self.logger.info("MARKET_ENGINE_RECOVERED | Engine recovered from error state")
                            await self._reconcile_session(db, session)
            except Exception as e:
                self.logger.exception("MARKET_ENGINE_EXCEPTION | Market engine loop failed | error=%s", str(e))
                self.logger.error("PRODUCTION_ALERT | category=MARKET_ENGINE_DOWN | error=%s", str(e))
                await db.rollback()
            await asyncio.sleep(2)

    async def _reconcile_session(self, db, session: MarketEngineSession) -> None:
        if not self.is_market_hours():
            if session.status != "WAITING_MARKET_OPEN":
                self.logger.info("Market closed; engine waiting for next session")
            session.status = "WAITING_MARKET_OPEN"
            session.websocket_connected = False
            await self._set_market_closed_waiting(db)
            self._feed.stop(notify=False)
            return

        try:
            desired = await self._desired_symbols(db)
            session.monitored_symbols_count = len(desired)
            await self._resume_active_models(db)
            self._feed.sync_symbols(desired)
            if desired:
                token = await get_current_access_token(db)
                if token:
                    self._feed.start(str(token))
                else:
                    self.logger.warning("No token available to start feed")
            session.status = "RUNNING"
            session.token_status = "VALID"
            session.paused_reason = None
            if session.started_at is None:
                session.started_at = datetime.utcnow()
            await self._poll_missing_prices(desired)
        except (FyersAuthExpiredError, FyersAuthInvalidError):
            await self._pause_for_token(db, session)
        except Exception:
            self.logger.exception("Market engine reconcile failed")
            session.status = "ERROR_RETRYING"

    async def _poll_missing_prices(self, symbols: set[str]) -> None:
        missing = [sym for sym in symbols if sym not in self.latest_ltp]
        if not missing:
            return
            
        sem = asyncio.Semaphore(10)
        
        async def fetch_and_process(sym: str):
            async with sem:
                ltp = await self.fyers.fetch_ltp(sym)
                if ltp is not None:
                    await self._on_tick(sym, ltp)

        await asyncio.gather(*(fetch_and_process(sym) for sym in missing))

    async def _on_tick(self, symbol: str, price: float) -> None:
        normalized = symbol.replace("NSE:", "").upper()
        self.latest_ltp[normalized] = price
        try:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    await self._process_symbol(db, normalized, price)
                    session = await self._get_or_create_session(db)
                    session.last_tick_at = datetime.utcnow()
        except Exception as e:
            self.logger.error("Tick processing error for %s: %s", normalized, e)

    async def _process_symbol(self, db, symbol: str, price: float) -> None:
        service = PaperTradingService(db)
        order_query = select(PaperOrder).where(
            PaperOrder.symbol == symbol,
            PaperOrder.lifecycle_state.in_(ACTIVE_ORDER_STATES),
            PaperOrder.status == "PENDING",
            PaperOrder.monitor_enabled.is_(True),
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            order_query = order_query.with_for_update(skip_locked=True)
        orders = list((await db.scalars(order_query)).all())
        for order in orders:
            prior = order.lifecycle_state
            order.last_seen_ltp = price
            order.last_evaluated_at = datetime.utcnow()
            account = await service._get_or_create_account(for_update=True)
            filled_order, position, _, _ = await service._try_fill_order(account, order, price)
            if filled_order.status == "FILLED":
                filled_order.lifecycle_state = "ENTRY_FILLED"
                if position:
                    position.lifecycle_state = "OPEN_POSITION"
                self.logger.info("PAPER_POSITION_OPENED | order_id=%s symbol=%s price=%s position_id=%s", order.id, symbol, price, getattr(position, "id", None))
                await self._record_event(
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
                def _add_notif(acc_id, oid):
                    with SessionLocal() as s:
                        PaperTradingService(s).add_notification(
                            acc_id, f"{symbol} paper buy auto-filled at Rs {round(price, 2)}.",
                            "success", "ENTRY_FILLED", "order", oid, dedupe_key=f"entry-filled:{oid}", commit=True)
                await asyncio.to_thread(_add_notif, account_id, order.id)

        position_query = select(PaperPosition).where(
            PaperPosition.symbol == symbol,
            PaperPosition.status == "OPEN",
            PaperPosition.lifecycle_state.in_(ACTIVE_POSITION_STATES),
            PaperPosition.monitor_enabled.is_(True),
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            position_query = position_query.with_for_update(skip_locked=True)
        positions = list((await db.scalars(position_query)).all())
        for position in positions:
            if position.target is not None and price >= position.target:
                self.logger.info("AUTO_EXIT_TARGET_TRIGGERED | position_id=%s | symbol=%s | entry_price=%s | target_price=%s | stoploss_price=%s | exit_price=%s | reason=%s", position.id, symbol, position.entry_price, position.target, position.stop_loss, price, "TARGET_HIT")
                try:
                    await service.auto_exit(position.id, price, "TARGET_HIT")
                    self.logger.info("AUTO_EXIT_ORDER_CREATED | position_id=%s | symbol=%s | exit_price=%s | reason=%s", position.id, symbol, price, "TARGET_HIT")
                except ValueError as exc:
                    self.logger.error("AUTO_EXIT_FAILED | position_id=%s | symbol=%s | entry_price=%s | target_price=%s | stoploss_price=%s | exit_price=%s | reason=%s", position.id, symbol, position.entry_price, position.target, position.stop_loss, price, str(exc))
                    self.logger.error("PRODUCTION_ALERT | category=AUTO_EXIT_FAILED | position_id=%s | reason=%s", position.id, str(exc))
                await self._record_event(db, "EXIT_FILLED", symbol, None, position.id, "OPEN_POSITION", "EXIT_FILLED", price, dedupe_key=f"exit-filled:{position.id}:TARGET_HIT")
            elif position.stop_loss is not None and price <= position.stop_loss:
                self.logger.info("AUTO_EXIT_STOPLOSS_TRIGGERED | position_id=%s | symbol=%s | entry_price=%s | target_price=%s | stoploss_price=%s | exit_price=%s | reason=%s", position.id, symbol, position.entry_price, position.target, position.stop_loss, price, "STOPLOSS_HIT")
                try:
                    await service.auto_exit(position.id, price, "STOPLOSS_HIT")
                    self.logger.info("AUTO_EXIT_ORDER_CREATED | position_id=%s | symbol=%s | exit_price=%s | reason=%s", position.id, symbol, price, "STOPLOSS_HIT")
                except ValueError as exc:
                    self.logger.error("AUTO_EXIT_FAILED | position_id=%s | symbol=%s | entry_price=%s | target_price=%s | stoploss_price=%s | exit_price=%s | reason=%s", position.id, symbol, position.entry_price, position.target, position.stop_loss, price, str(exc))
                    self.logger.error("PRODUCTION_ALERT | category=AUTO_EXIT_FAILED | position_id=%s | reason=%s", position.id, str(exc))
                await self._record_event(db, "EXIT_FILLED", symbol, None, position.id, "OPEN_POSITION", "EXIT_FILLED", price, dedupe_key=f"exit-filled:{position.id}:STOPLOSS_HIT")

    async def _desired_symbols(self, db) -> set[str]:
        order_symbols = set(
            (await db.scalars(
                select(PaperOrder.symbol).where(
                    PaperOrder.status == "PENDING",
                    PaperOrder.lifecycle_state.in_(ACTIVE_ORDER_STATES),
                    PaperOrder.monitor_enabled.is_(True),
                )
            )).all()
        )
        positions = list(
            (await db.scalars(
                select(PaperPosition).where(
                    PaperPosition.status == "OPEN",
                    PaperPosition.lifecycle_state.in_(ACTIVE_POSITION_STATES),
                    PaperPosition.monitor_enabled.is_(True),
                )
            )).all()
        )
        
        self._active_positions_cache.clear()
        for pos in positions:
            self._active_positions_cache.setdefault(pos.symbol, []).append(pos)
            
        position_symbols = {pos.symbol for pos in positions if pos.symbol}
        return {s for s in order_symbols | position_symbols if s}

    async def _set_market_closed_waiting(self, db) -> None:
        for order in (await db.scalars(select(PaperOrder).where(PaperOrder.status == "PENDING"))).all():
            if order.lifecycle_state in ACTIVE_ORDER_STATES:
                order.lifecycle_state = "MARKET_CLOSED_WAITING"
        for position in (await db.scalars(select(PaperPosition).where(PaperPosition.status == "OPEN"))).all():
            if position.lifecycle_state in ACTIVE_POSITION_STATES:
                position.lifecycle_state = "MARKET_CLOSED_WAITING"

    async def _resume_active_models(self, db) -> None:
        for order in (await db.scalars(select(PaperOrder).where(PaperOrder.status == "PENDING"))).all():
            if order.lifecycle_state in {"MARKET_CLOSED_WAITING", "ERROR_RETRYING", "TOKEN_EXPIRED_PAUSED"}:
                order.lifecycle_state = "PENDING_ENTRY"
                order.paused_reason = None
        for position in (await db.scalars(select(PaperPosition).where(PaperPosition.status == "OPEN"))).all():
            if position.lifecycle_state in {"MARKET_CLOSED_WAITING", "ERROR_RETRYING", "TOKEN_EXPIRED_PAUSED"}:
                position.lifecycle_state = "OPEN_POSITION"
                position.paused_reason = None

    async def _pause_for_token(self, db, session: MarketEngineSession) -> None:
        already_paused = session.status == "PAUSED_TOKEN_EXPIRED"
        session.status = "PAUSED_TOKEN_EXPIRED"
        session.token_status = "EXPIRED"
        session.paused_reason = "TOKEN_EXPIRED"
        session.websocket_connected = False
        def _get_acc():
            with SessionLocal() as s:
                return PaperTradingService(s)._get_or_create_account().id
        account_id = await asyncio.to_thread(_get_acc)
        for order in (await db.scalars(select(PaperOrder).where(PaperOrder.status == "PENDING"))).all():
            order.lifecycle_state = "TOKEN_EXPIRED_PAUSED"
            order.paused_reason = "TOKEN_EXPIRED"
        for position in (await db.scalars(select(PaperPosition).where(PaperPosition.status == "OPEN"))).all():
            position.lifecycle_state = "TOKEN_EXPIRED_PAUSED"
            position.paused_reason = "TOKEN_EXPIRED"
        if not already_paused:
            self.logger.warning("Token expired; monitoring paused | session_id=%s", session.id)
        def _add_notif(acc_id, sid):
            with SessionLocal() as s:
                PaperTradingService(s).add_notification(acc_id, "FYERS token expired; monitoring paused.", "error", "TOKEN_EXPIRED", "engine", sid, dedupe_key=f"token-expired:{sid}", commit=True)
        await asyncio.to_thread(_add_notif, account_id, session.id)
        self._feed.stop(notify=False)

    async def _on_feed_error(self, message: str | Exception) -> None:
        if "expired" in str(message).lower():
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    session = await self._get_or_create_session(db)
                    await self._pause_for_token(db, session)
            return
        async with AsyncSessionLocal() as db:
            async with db.begin():
                session = await self._get_or_create_session(db)
                session.status = "ERROR_RETRYING"
                session.websocket_connected = False
                def _get_acc():
                    with SessionLocal() as s:
                        return PaperTradingService(s)._get_or_create_account().id
                account_id = await asyncio.to_thread(_get_acc)
                def _add_err_notif(acc_id, sid):
                    with SessionLocal() as s:
                        PaperTradingService(s).add_notification(acc_id, "Live market feed disconnected; monitoring degraded while retrying.", "error", "WEBSOCKET_DISCONNECTED", "engine", sid, dedupe_key=f"feed-disconnected:{sid}", commit=True)
                await asyncio.to_thread(_add_err_notif, account_id, session.id)
                self.logger.error("FYERS_WS_ERROR | Websocket connection failed | disconnect_reason=%s | downtime_seconds=0", str(message))
                self.logger.error("PRODUCTION_ALERT | category=WEBSOCKET_DOWN | reason=%s", str(message))

    async def _on_connection_change(self, connected: bool) -> None:
        try:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    session = await self._get_or_create_session(db)
                    if connected:
                        self.logger.info("FYERS_WS_CONNECTED | Websocket connection state changed | connected=True")
                    else:
                        self.logger.warning("FYERS_WS_DISCONNECTED | Websocket connection state changed | connected=False | disconnect_reason=connection_lost | downtime_seconds=0")
                        self.logger.error("PRODUCTION_ALERT | category=WEBSOCKET_DOWN | reason=connection_lost")
                    session.websocket_connected = connected
        except Exception:
            self.logger.exception("Failed to persist websocket state change | connected=%s", connected)

    async def _record_event(
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
            existing = await db.scalar(select(ExecutionEvent).where(ExecutionEvent.dedupe_key == dedupe_key))
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

    async def _get_or_create_session(self, db) -> MarketEngineSession:
        today = datetime.now(IST).date().isoformat()
        session = await db.scalar(select(MarketEngineSession).where(MarketEngineSession.trading_date == today))
        if session:
            return session
        session = MarketEngineSession(trading_date=today, status="STOPPED")
        db.add(session)
        await db.flush()
        return session

    def is_market_hours(self, now: datetime | None = None) -> bool:
        local = (now or datetime.now(timezone.utc)).astimezone(IST)
        if local.weekday() >= 5:
            return False
        return time(9, 0) <= local.time() <= time(16, 0)


market_engine = MarketEngineService()
