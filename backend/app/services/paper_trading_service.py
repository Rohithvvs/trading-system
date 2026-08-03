from __future__ import annotations

import concurrent.futures
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, time as dt_time
from decimal import Decimal
from math import isfinite

import pandas as pd
from sqlalchemy import delete, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ta.trend import EMAIndicator

_account_creation_lock = threading.Lock()

from ..config import settings
from ..models.paper_trading import (
    DEFAULT_PAPER_STARTING_BALANCE,
    OPEN_ORDER_STATUSES,
    PENDING_MARKET_OPEN_STATUS,
    TERMINAL_ORDER_STATUSES,
    ExecutionEvent,
    PaperOrder,
    PaperPosition,
    PaperTradeHistory,
    PaperTradingAccount,
    PaperNotification,
    PaperTransaction,
    PaperAlert,
)
from ..services.trading_hours_service import trading_hours
from ..schemas import AnalysisMode, OHLCVPoint
from ..schemas.paper_trading import (
    PaperAccountSummary,
    PaperOrderActionResponse,
    PaperOrderCreateRequest,
    PaperQuoteResponse,
    PaperOrderResponse,
    PaperPositionResponse,
    PaperPositionUpdateRequest,
    PaperTradeHistoryItem,
    PaperTradingAccountResetRequest,
    PaperTradingDashboardResponse,
    PaperWorkspaceSnapshot,
    RecommendationPrefillRequest,
    RecommendationPrefillResponse,
)
from ..services.fyers_service import FyersService
from ..utils import get_logger, safe_int
from ..core.log_manager import trading_logger
from ..utils.money import as_float, dec, q_pnl, q_price, q_qty
from ..observability.metrics import DUPLICATE_EXECUTIONS, ORDER_EXECUTIONS

# In-memory PriceSnapshot cache with TTL (avoids redundant FYERS calls across requests within short window)
_price_snapshot_cache: dict[str, tuple[PriceSnapshot, float]] = {}
_price_snapshot_cache_lock = threading.Lock()
_PRICE_CACHE_TTL_SEC = 3.0  # 3-second TTL — fresh enough for paper trading



@dataclass(slots=True)
class PriceSnapshot:
    symbol: str
    current_price: float
    candles: list[OHLCVPoint]
    ema_20: float | None
    supertrend: float | None
    source: str
    fetched_at: datetime


class PaperTradingService:
    """
    Paper trading operations are always scoped to a single authenticated user.

    - Pass ``user_id`` for HTTP API paths (required for account get/create).
    - Engine/background paths may omit ``user_id`` and must use account_id from
      the order/position being processed (never a global shared account).
    """

    def __init__(self, db: Session, user_id: uuid.UUID | str | None = None) -> None:
        self.db = db
        self.logger = get_logger("app.paper_trading")
        self.fyers_service = FyersService()
        self.user_id: uuid.UUID | None = uuid.UUID(str(user_id)) if user_id else None

    def get_dashboard(self, selected_symbol: str | None = None) -> PaperTradingDashboardResponse:
        account = self._get_or_create_account()
        self._refresh_pending_orders(account.id)
        positions = self._position_models(account.id)
        orders = self._order_models(account.id)
        trades = self._trade_models(account.id)

        symbols = {item.symbol for item in positions} | {item.symbol for item in orders}
        price_cache = self._load_price_cache(symbols)
        for position in positions:
            snapshot = price_cache.get(position.symbol)
            if snapshot and snapshot.current_price > 0:
                position.current_price = snapshot.current_price

        summary = self._build_account_summary(account, positions, orders, trades, price_cache)
        workspace_symbol = selected_symbol or (positions[0].symbol if positions else orders[0].symbol if orders else None)
        workspace = self._workspace_snapshot(workspace_symbol, price_cache) if workspace_symbol else None

        return PaperTradingDashboardResponse(
            account=summary,
            positions=[self._serialize_position(item, price_cache.get(item.symbol)) for item in positions],
            open_orders=[
                self._serialize_order(item, price_cache.get(item.symbol))
                for item in orders
                if item.status in OPEN_ORDER_STATUSES
            ],
            order_history=[self._serialize_order(item, price_cache.get(item.symbol)) for item in orders],
            trades=[self._serialize_trade(item) for item in trades],
            symbols=settings.nifty500_symbols,
            selected_workspace=workspace,
        )

    def get_positions(self) -> list[PaperPositionResponse]:
        account = self._get_or_create_account()
        self._refresh_pending_orders(account.id)
        positions = self._position_models(account.id)
        price_cache = self._load_price_cache({item.symbol for item in positions})
        for position in positions:
            snapshot = price_cache.get(position.symbol)
            if snapshot and snapshot.current_price > 0:
                position.current_price = snapshot.current_price
        self.db.commit()
        # Re-fetch positions after commit to avoid stale object errors
        positions = self._position_models(account.id)
        return [self._serialize_position(item, price_cache.get(item.symbol)) for item in positions]

    def get_pending_orders(self) -> list[PaperOrderResponse]:
        account = self._get_or_create_account()
        self._refresh_pending_orders(account.id)
        orders = [item for item in self._order_models(account.id) if item.status in OPEN_ORDER_STATUSES]
        price_cache = self._load_price_cache({item.symbol for item in orders})
        self.db.commit()
        # Re-fetch orders after commit to avoid stale object errors
        orders = [item for item in self._order_models(account.id) if item.status in OPEN_ORDER_STATUSES]
        return [self._serialize_order(item, price_cache.get(item.symbol)) for item in orders]

    def get_order_history(self) -> list[PaperOrderResponse]:
        account = self._get_or_create_account()
        self._refresh_pending_orders(account.id)
        orders = self._order_models(account.id)
        price_cache = self._load_price_cache({item.symbol for item in orders})
        self.db.commit()
        # Re-fetch orders after commit to avoid stale object errors
        orders = self._order_models(account.id)
        return [self._serialize_order(item, price_cache.get(item.symbol)) for item in orders]

    def get_trades(self) -> list[PaperTradeHistoryItem]:
        account = self._get_or_create_account()
        self._refresh_pending_orders(account.id)
        trades = self._trade_models(account.id)
        self.db.commit()
        # Re-fetch trades after commit to avoid stale object errors
        trades = self._trade_models(account.id)
        return [self._serialize_trade(item) for item in trades]

    def reset_account(self, payload: PaperTradingAccountResetRequest) -> PaperTradingDashboardResponse:
        account = self._get_or_create_account()
        account.starting_balance = payload.starting_balance
        account.cash_balance = payload.starting_balance
        account.updated_at = datetime.now(timezone.utc)
        self.db.execute(delete(PaperPosition).where(PaperPosition.account_id == account.id))
        self.db.execute(delete(PaperOrder).where(PaperOrder.account_id == account.id))
        self.db.execute(delete(PaperTradeHistory).where(PaperTradeHistory.account_id == account.id))
        self.db.execute(delete(PaperTransaction).where(PaperTransaction.account_id == account.id))
        self.db.commit()
        self.logger.info("Paper account reset | account_id=%s | starting_balance=%s", account.id, payload.starting_balance)
        return self.get_dashboard()

    def place_order(self, payload: PaperOrderCreateRequest) -> PaperOrderActionResponse:
        if not payload.idempotency_key:
            raise ValueError("Idempotency key is required.")

        account = self._get_or_create_account(for_update=True)
        from ..utils.symbol import canonical_symbol

        self._validate_symbol(payload.symbol)
        # Always persist canonical form so quote polling and positions stay consistent
        order_symbol = canonical_symbol(payload.symbol)
        existing = self.db.scalar(
            select(PaperOrder).where(
                PaperOrder.account_id == account.id,
                PaperOrder.idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            position = self.db.scalar(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.symbol == existing.symbol,
                    PaperPosition.status == "OPEN",
                )
            )
            return PaperOrderActionResponse(
                account=self.get_dashboard(selected_symbol=existing.symbol).account,
                order=self._serialize_order(existing),
                position=self._serialize_position(position) if position else None,
                message="Idempotent retry: existing order returned.",
            )
        self._refresh_pending_orders(account.id)
        price = self._price_snapshot(order_symbol)
        trigger_price = self._requested_price(payload, price.current_price)
        market_status = trading_hours.get_market_status()
        market_is_open = bool(market_status.get("is_open"))
        next_open = None if market_is_open else trading_hours.get_next_market_open()

        order = PaperOrder(
            account_id=account.id,
            symbol=order_symbol,
            side=payload.side,
            order_type=payload.type,
            product_type=payload.product_type,
            qty=payload.qty,
            order_price=trigger_price,
            requested_entry_price=trigger_price,
            stop_price=payload.stop_price,
            stop_loss=payload.stop_loss,
            target=payload.target,
            notes=payload.notes,
            source_signal=payload.source_signal,
            source_score=payload.source_score,
            source_confidence=payload.source_confidence,
            status="PENDING",
            lifecycle_state="PENDING_ENTRY",
            market_session=str(market_status.get("status") or market_status.get("session") or "UNKNOWN"),
            scheduled_execution=next_open,
            idempotency_key=payload.idempotency_key,
        )
        self.db.add(order)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(PaperOrder).where(
                    PaperOrder.account_id == account.id,
                    PaperOrder.idempotency_key == payload.idempotency_key,
                )
            )
            if existing:
                return PaperOrderActionResponse(
                    account=self.get_dashboard(selected_symbol=existing.symbol).account,
                    order=self._serialize_order(existing),
                    message="Idempotent retry: existing order returned.",
                )
            raise

        order.last_evaluated_at = datetime.now(timezone.utc)
        order.last_seen_ltp = price.current_price if price.current_price > 0 else None
        filled_order = order
        position = None
        trade = None
        message = "Order placed."

        if not market_is_open:
            # After hours / weekend / holiday: accept order, do NOT create position or touch capital
            order.status = PENDING_MARKET_OPEN_STATUS
            order.lifecycle_state = PENDING_MARKET_OPEN_STATUS
            order.scheduled_execution = next_open
            try:
                trading_logger.info(
                    "ORDER_PLACED_PENDING | user_id=%s | account=%s | order_id=%s | symbol=%s | side=%s | qty=%s | "
                    "status=%s | market_status=%s | scheduled_execution=%s | order_type=%s | requested_price=%s",
                    self.user_id,
                    account.id,
                    getattr(order, "id", None),
                    order.symbol,
                    order.side,
                    order.qty,
                    order.status,
                    order.market_session,
                    order.scheduled_execution.isoformat() if order.scheduled_execution else None,
                    order.order_type,
                    order.order_price,
                )
            except Exception:
                pass
            message = (
                "Order accepted. The market is currently closed. "
                "Your order has been placed successfully and will be executed automatically when the market opens."
            )
            try:
                self.add_notification(
                    account.id,
                    (
                        f"Order accepted for {order.symbol}. Market is closed "
                        f"({order.market_session}). "
                        f"Scheduled for next market open"
                        f"{(' at ' + order.scheduled_execution.astimezone(timezone.utc).isoformat()) if order.scheduled_execution else ''}."
                    ),
                    "info",
                    "ORDER_PLACED_PENDING",
                    "order",
                    order.id,
                    dedupe_key=f"pending-market-open:{order.id}",
                    commit=False,
                )
            except Exception:
                self.logger.exception("Failed to write PENDING_MARKET_OPEN notification")
        else:
            try:
                trading_logger.info(
                    "ORDER_PLACED | account=%s | order_id=%s | symbol=%s | side=%s | qty=%s | order_type=%s | "
                    "order_price=%s | market_status=OPEN | stop_loss=%s | target=%s",
                    account.id,
                    getattr(order, "id", None),
                    order.symbol,
                    order.side,
                    order.qty,
                    order.order_type,
                    order.order_price,
                    order.stop_loss,
                    order.target,
                )
            except Exception:
                pass
            # Market open: attempt immediate execution (MARKET) or leave pending for price trigger
            filled_order, position, trade, message = self._try_fill_order(
                account, order, price.current_price, require_market_open=True
            )

            try:
                if filled_order.status in {"FILLED", "EXECUTED"} and filled_order.side == "BUY":
                    filled_order.lifecycle_state = "ENTRY_FILLED"
                    if position:
                        position.lifecycle_state = "OPEN_POSITION"
                    tx = PaperTransaction(
                        account_id=int(account.id),
                        timestamp=datetime.now(timezone.utc),
                        symbol=filled_order.symbol,
                        action="BUY",
                        qty=int(filled_order.qty),
                        price=float(filled_order.filled_price) if filled_order.filled_price is not None else None,
                        amount=-float(filled_order.filled_price or 0.0) * int(filled_order.qty),
                        balance_after=float(account.cash_balance),
                    )
                    self.db.add(tx)
                    self.add_notification(
                        account.id,
                        (
                            f"Your BUY order for {filled_order.symbol} has been executed successfully. "
                            f"Position has been added to your portfolio "
                            f"(Rs {round(float(filled_order.filled_price or 0.0), 2)})."
                        ),
                        "success",
                        "ORDER_EXECUTED",
                        "order",
                        filled_order.id,
                        dedupe_key=f"entry-filled:{filled_order.id}",
                        commit=False,
                    )
                elif filled_order.status in OPEN_ORDER_STATUSES and filled_order.side == "BUY":
                    self.add_notification(
                        account.id,
                        f"{filled_order.symbol} {filled_order.order_type.lower()} buy waiting for entry at Rs {round(float(filled_order.order_price or 0.0), 2)}.",
                        "info",
                        "PENDING_ENTRY_CREATED",
                        "order",
                        filled_order.id,
                        dedupe_key=f"pending-entry:{filled_order.id}",
                        commit=False,
                    )
                elif filled_order.status in {"FILLED", "EXECUTED"} and filled_order.side == "SELL":
                    self.add_notification(
                        account.id,
                        f"Your SELL order for {filled_order.symbol} has been executed successfully.",
                        "success",
                        "ORDER_EXECUTED",
                        "order",
                        filled_order.id,
                        dedupe_key=f"exit-filled:{filled_order.id}",
                        commit=False,
                    )
            except Exception as e:
                print(f"ERROR creating notifications in place_order: {e}")
                self.logger.exception("Failed to write transaction or notification in place_order")

        # Commit the order + position + account + transactions + notifications as one atomic unit
        try:
            self.db.commit()
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            self.logger.exception("Failed to commit order for symbol=%s account=%s", payload.symbol, account.id)
            raise

        summary = self.get_dashboard(selected_symbol=payload.symbol).account
        return PaperOrderActionResponse(
            account=summary,
            order=self._serialize_order(filled_order),
            position=self._serialize_position(position) if position else None,
            trade=self._serialize_trade(trade) if trade else None,
            message=message,
        )

    def cancel_order(self, order_id: int) -> PaperOrderActionResponse:
        account = self._get_or_create_account()
        order = self.db.scalar(select(PaperOrder).where(PaperOrder.id == order_id, PaperOrder.account_id == account.id))
        if not order:
            raise ValueError("Order not found.")
        if order.status not in OPEN_ORDER_STATUSES:
            raise ValueError("Only pending orders can be cancelled.")
        prior_status = order.status
        order.status = "CANCELLED"
        order.lifecycle_state = "CANCELLED"
        order.cancelled_at = datetime.now(timezone.utc)
        try:
            trading_logger.info(
                "PENDING_ORDER_CANCELLED | user_id=%s | account=%s | order_id=%s | symbol=%s | qty=%s | "
                "prior_status=%s | market_status=%s",
                self.user_id,
                account.id,
                order.id,
                order.symbol,
                order.qty,
                prior_status,
                trading_hours.get_market_status().get("status"),
            )
        except Exception:
            pass
        try:
            self.add_notification(
                account.id,
                f"Pending order for {order.symbol} cancelled.",
                "info",
                "PENDING_ORDER_CANCELLED",
                "order",
                order.id,
                dedupe_key=f"order-cancelled:{order.id}",
                commit=False,
            )
        except Exception:
            pass
        self.db.commit()
        return PaperOrderActionResponse(
            account=self.get_dashboard(selected_symbol=order.symbol).account,
            order=self._serialize_order(order),
            message="Order cancelled.",
        )

    def modify_order(self, order_id: int, payload) -> PaperOrderActionResponse:
        account = self._get_or_create_account()
        order = self.db.scalar(select(PaperOrder).where(PaperOrder.id == order_id, PaperOrder.account_id == account.id))
        if not order:
            raise ValueError("Order not found.")
        if order.status not in OPEN_ORDER_STATUSES:
            raise ValueError("Only pending orders can be modified.")

        # Apply provided updates
        if getattr(payload, "qty", None) is not None:
            order.qty = int(payload.qty)
        if getattr(payload, "limit_price", None) is not None:
            order.order_price = float(payload.limit_price)
        if getattr(payload, "stop_price", None) is not None:
            order.stop_price = float(payload.stop_price)
        if getattr(payload, "stop_loss", None) is not None:
            order.stop_loss = float(payload.stop_loss)
        if getattr(payload, "target", None) is not None:
            order.target = float(payload.target)
        if getattr(payload, "type", None) is not None:
            order.order_type = payload.type
        if getattr(payload, "product_type", None) is not None:
            try:
                order.product_type = payload.product_type
            except Exception as e:
                print(f"ERROR setting product_type for order update: {e}")
                order.product_type = str(payload.product_type)

        self.db.commit()
        return PaperOrderActionResponse(
            account=self.get_dashboard(selected_symbol=order.symbol).account,
            order=self._serialize_order(order),
            message="Order updated.",
        )

    def close_position(self, position_id: int) -> PaperOrderActionResponse:
        position = self.db.scalar(select(PaperPosition).where(PaperPosition.id == position_id))
        if not position:
            raise ValueError("Position not found.")
        payload = PaperOrderCreateRequest(
            symbol=position.symbol,
            side="SELL",
            type="MARKET",
            qty=position.qty,
            notes="Position closed from paper trading workspace.",
            stop_loss=position.stop_loss,
            target=position.target,
            source_signal=position.source_signal,
            source_score=position.source_score,
            source_confidence=position.source_confidence,
        )
        return self.place_order(payload)

    def update_position(self, position_id: int, payload: PaperPositionUpdateRequest) -> PaperOrderActionResponse:
        position = self.db.scalar(select(PaperPosition).where(PaperPosition.id == position_id))
        if not position:
            raise ValueError("Position not found.")
        position.stop_loss = payload.stop_loss
        position.target = payload.target
        if payload.notes is not None:
            position.notes = payload.notes
        position.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return PaperOrderActionResponse(
            account=self.get_dashboard(selected_symbol=position.symbol).account,
            position=self._serialize_position(position),
            message="Position updated.",
        )

    def recommendation_prefill(self, payload: RecommendationPrefillRequest) -> RecommendationPrefillResponse:
        from ..utils.symbol import canonical_symbol

        targets = payload.suggested_targets or []
        return RecommendationPrefillResponse(
            symbol=canonical_symbol(payload.symbol),
            qty=1,
            limit_price=payload.suggested_entry,
            stop_loss=payload.suggested_stop,
            target=targets[0] if targets else None,
            note=(
                f"Imported from system recommendation | signal={payload.recommendation_meta.get('signal', 'BUY')} | "
                f"score={payload.recommendation_meta.get('score', 'n/a')} | "
                f"confidence={payload.recommendation_meta.get('confidence', 'n/a')}"
            ),
        )

    def get_workspace(self, symbol: str) -> PaperWorkspaceSnapshot:
        from ..utils.symbol import canonical_symbol

        normalized = canonical_symbol(symbol)
        self._validate_symbol(normalized)
        snapshot = self._price_snapshot(normalized)
        return self._workspace_from_snapshot(snapshot, None, None, None)

    def get_quote(self, symbol: str) -> PaperQuoteResponse:
        """Return latest paper-trading quote with graceful degradation.

        Always canonicalizes symbols (e.g. ``INFY-EQ`` → ``INFY``) before
        universe validation and broker calls. Temporary provider failures return
        a structured degraded status and last-known price when available instead
        of failing the request.
        """
        import time as _time
        from ..utils.symbol import canonical_symbol

        started = _time.perf_counter()
        raw_symbol = (symbol or "").strip()
        normalized_symbol = canonical_symbol(raw_symbol)
        user = str(self.user_id) if self.user_id else "system"
        broker = "FYERS"
        endpoint = "quotes"
        retry_count = 0
        exception_name: str | None = None
        status_code = 200
        reason: str | None = None
        is_stale = False
        last_successful_at: datetime | None = None
        now = datetime.now(timezone.utc)

        self.logger.info(
            "QUOTE_REQUEST_STARTED | timestamp=%s | user=%s | broker=%s | symbol=%s | "
            "raw_symbol=%s | endpoint=%s | retry_count=%s",
            now.isoformat(),
            user,
            broker,
            normalized_symbol,
            raw_symbol,
            endpoint,
            retry_count,
        )

        self._validate_symbol(normalized_symbol)

        ltp: float | None = None
        source = "NO_DATA"

        # 1) Live LTP via shared event loop (bounded timeout).
        # Unit tests mock run_coroutine_threadsafe; production uses main_event_loop.
        try:
            import asyncio
            from ..db.session import main_event_loop

            future = asyncio.run_coroutine_threadsafe(
                self.fyers_service.fetch_ltp(normalized_symbol),
                main_event_loop,
            )
            ltp = future.result(timeout=5)
            if ltp is not None and float(ltp) > 0:
                source = "FYERS_QUOTE"
            else:
                ltp = None
        except Exception as e:
            exception_name = type(e).__name__
            latency_ms = int((_time.perf_counter() - started) * 1000)
            self.logger.error(
                "QUOTE_REQUEST_FAILURE | timestamp=%s | user=%s | broker=%s | symbol=%s | "
                "endpoint=%s | status_code=%s | latency_ms=%s | retry_count=%s | exception=%s | error=%s",
                datetime.now(timezone.utc).isoformat(),
                user,
                broker,
                normalized_symbol,
                endpoint,
                status_code,
                latency_ms,
                retry_count,
                exception_name,
                str(e)[:200],
                exc_info=True,
            )
            ltp = None

        # 2) Candle fallback (bounded) when live LTP missing
        if ltp is None:
            try:
                from .fyers_service import _run_sync

                candles = None
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(
                        _run_sync,
                        self.fyers_service.fetch_ohlcv(normalized_symbol, AnalysisMode.swing, "1d", 2),
                    )
                    candles = fut.result(timeout=8)
                if candles:
                    close = getattr(candles[-1], "close", None)
                    if close is not None and float(close) > 0:
                        ltp = float(close)
                        source = "CANDLE_FALLBACK"
                        reason = reason or (
                            "Quote Provider Timeout"
                            if exception_name in {"TimeoutError", "CancelledError", "FuturesTimeoutError"}
                            else "Live quote unavailable; using candle fallback"
                        )
                        is_stale = True
            except Exception as e:
                retry_count += 1
                exception_name = exception_name or type(e).__name__
                self.logger.warning(
                    "QUOTE_CANDLE_FALLBACK_FAILURE | timestamp=%s | user=%s | broker=%s | symbol=%s | "
                    "endpoint=ohlcv | latency_ms=%s | retry_count=%s | exception=%s | error=%s",
                    datetime.now(timezone.utc).isoformat(),
                    user,
                    broker,
                    normalized_symbol,
                    int((_time.perf_counter() - started) * 1000),
                    retry_count,
                    type(e).__name__,
                    str(e)[:200],
                )

        # 3) Last successful in-process snapshot (failover display)
        if ltp is None:
            try:
                import time as _mono

                with _price_snapshot_cache_lock:
                    cached_entry = _price_snapshot_cache.get(normalized_symbol)
                if cached_entry:
                    snap, _ts = cached_entry
                    if snap and snap.current_price and float(snap.current_price) > 0:
                        ltp = float(snap.current_price)
                        source = (
                            snap.source
                            if snap.source in {"FYERS_QUOTE", "CANDLE_FALLBACK", "NO_DATA", "TEST_MOCK"}
                            else "CANDLE_FALLBACK"
                        )
                        reason = reason or (
                            "Quote Provider Timeout"
                            if exception_name in {"TimeoutError", "CancelledError", "FuturesTimeoutError"}
                            else "Using last successful price"
                        )
                        is_stale = True
                        last_successful_at = snap.fetched_at
                        self.logger.info(
                            "QUOTE_LAST_KNOWN_PRICE | symbol=%s | ltp=%s | age_source=%s",
                            normalized_symbol,
                            ltp,
                            snap.source,
                        )
            except Exception:
                pass

        if ltp is None or float(ltp) <= 0:
            ltp = 0.0
            source = "NO_DATA"
            reason = reason or (
                "Quote Provider Timeout"
                if exception_name in {"TimeoutError", "CancelledError", "FuturesTimeoutError"}
                else "Market data unavailable"
            )
            is_stale = True
            self.logger.warning(
                "PAPER_PRICE_UNAVAILABLE | timestamp=%s | user=%s | broker=%s | symbol=%s | "
                "endpoint=%s | status_code=%s | latency_ms=%s | retry_count=%s | exception=%s | reason=%s",
                datetime.now(timezone.utc).isoformat(),
                user,
                broker,
                normalized_symbol,
                endpoint,
                status_code,
                int((_time.perf_counter() - started) * 1000),
                retry_count,
                exception_name,
                reason,
            )
        else:
            reason = None
            is_stale = False
            self.logger.info(
                "PAPER_PRICE_UPDATE | symbol=%s | ltp=%s | source=%s",
                normalized_symbol,
                ltp,
                source,
            )

        latency_ms = int((_time.perf_counter() - started) * 1000)
        self.logger.info(
            "QUOTE_REQUEST_SUCCESS | timestamp=%s | user=%s | broker=%s | symbol=%s | endpoint=%s | "
            "status_code=%s | latency_ms=%s | retry_count=%s | exception=%s | ltp=%s | source=%s | "
            "reason=%s",
            datetime.now(timezone.utc).isoformat(),
            user,
            broker,
            normalized_symbol,
            endpoint,
            status_code,
            latency_ms,
            retry_count,
            exception_name,
            ltp,
            source,
            reason,
        )

        # Seed snapshot cache on successful live/candle prices for future failover
        if ltp and float(ltp) > 0 and source != "NO_DATA":
            try:
                import time as _mono

                snap = PriceSnapshot(
                    symbol=normalized_symbol,
                    current_price=float(ltp),
                    candles=[],
                    ema_20=None,
                    supertrend=None,
                    source=source,
                    fetched_at=last_successful_at or now,
                )
                with _price_snapshot_cache_lock:
                    # Only overwrite with fresher live data; keep last known if degraded re-hit
                    existing = _price_snapshot_cache.get(normalized_symbol)
                    if not existing or source == "FYERS_QUOTE" or not existing[0].current_price:
                        _price_snapshot_cache[normalized_symbol] = (snap, _mono.monotonic())
            except Exception:
                pass

        return PaperQuoteResponse(
            symbol=normalized_symbol,
            current_price=round(float(ltp), 2),
            source=source,  # type: ignore[arg-type]
            updated_at=now,
            reason=reason,
            is_stale=is_stale,
            last_successful_at=last_successful_at,
        )

    def get_account_by_id(self, account_id: int, for_update: bool = False) -> PaperTradingAccount:
        """Load a specific paper account (engine/system use). Does not create."""
        query = select(PaperTradingAccount).where(PaperTradingAccount.id == account_id)
        if for_update and self.db.bind and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        account = self.db.scalar(query)
        if not account:
            raise ValueError(f"Paper account {account_id} not found.")
        return account

    def _get_or_create_account(self, for_update: bool = False) -> PaperTradingAccount:
        """
        Get or create the paper account for ``self.user_id`` only.
        Never returns another user's account. Never creates a global shared account.

        When ``user_id`` is omitted (legacy unit tests / engine helpers), load an
        existing seeded account if exactly one is present — do NOT create a shared
        multi-user account without ownership.
        """
        if self.user_id is None:
            query = select(PaperTradingAccount).order_by(PaperTradingAccount.id.asc())
            if for_update and self.db.bind and self.db.bind.dialect.name == "postgresql":
                query = query.with_for_update()
            account = self.db.scalar(query)
            if account:
                # Legacy test path — log loudly so production miswiring is visible
                self.logger.warning(
                    "PAPER_ACCOUNT_LEGACY_UNSCOPED | account_id=%s | "
                    "service constructed without user_id (test/engine only)",
                    account.id,
                )
                return account
            raise ValueError(
                "PaperTradingService requires user_id for user-scoped account operations. "
                "Background/engine paths must load accounts via get_account_by_id()."
            )

        user_id = self.user_id
        query = select(PaperTradingAccount).where(PaperTradingAccount.user_id == user_id)
        if for_update and self.db.bind and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update()

        with _account_creation_lock:
            account = self.db.scalar(query)
            if account:
                return account

            account = PaperTradingAccount(
                user_id=user_id,
                name="Primary Paper Account",
                starting_balance=DEFAULT_PAPER_STARTING_BALANCE,
                cash_balance=DEFAULT_PAPER_STARTING_BALANCE,
                max_risk_per_trade=Decimal("0.02"),
            )
            self.db.add(account)
            try:
                self.db.commit()
            except IntegrityError:
                # Concurrent first request — race on unique user_id
                self.db.rollback()
                account = self.db.scalar(
                    select(PaperTradingAccount).where(PaperTradingAccount.user_id == user_id)
                )
                if account:
                    return account
                raise
            self.db.refresh(account)
            self.logger.info(
                "PAPER_ACCOUNT_CREATED | user_id=%s | account_id=%s | starting_balance=%s",
                user_id,
                account.id,
                account.starting_balance,
            )
            return account

    @staticmethod
    def ensure_paper_account_for_user(db: Session, user_id: uuid.UUID | str) -> PaperTradingAccount:
        """Idempotent helper used at registration — creates ₹10L account if missing."""
        svc = PaperTradingService(db, user_id=user_id)
        return svc._get_or_create_account()

    def _validate_symbol(self, symbol: str) -> None:
        """Accept raw, exchange-prefixed, or ``-EQ`` forms by canonicalizing first.

        Universe symbols are stored in canonical form (e.g. ``INFY``), while the
        UI/broker often send ``INFY-EQ`` or ``NSE:INFY-EQ``. Exact-string checks
        previously rejected valid cash symbols and broke live quote polling.
        """
        from ..utils.symbol import canonical_symbol

        raw = (symbol or "").strip().upper()
        canon = canonical_symbol(raw)
        allowed = settings.nifty500_symbols
        if canon in allowed or raw in allowed:
            return
        raise ValueError("Only configured Nifty 500 cash symbols are allowed.")

    def _position_models(self, account_id: int) -> list[PaperPosition]:
        try:
            # Return only OPEN positions (avoid closed/archived rows)
            return list(
                self.db.scalars(
                    select(PaperPosition)
                    .where(PaperPosition.account_id == account_id, PaperPosition.status == "OPEN")
                    .order_by(PaperPosition.created_at.desc())
                )
            )
        except Exception as e:
            print(f"ERROR in _position_models: {e}")
            self.logger.exception("Failed to load position models for account=%s", account_id)
            return []

    def _order_models(self, account_id: int) -> list[PaperOrder]:
        return list(self.db.scalars(select(PaperOrder).where(PaperOrder.account_id == account_id).order_by(PaperOrder.created_at.desc())))

    def _trade_models(self, account_id: int) -> list[PaperTradeHistory]:
        return list(self.db.scalars(select(PaperTradeHistory).where(PaperTradeHistory.account_id == account_id).order_by(PaperTradeHistory.closed_at.desc())))

    def _requested_price(self, payload: PaperOrderCreateRequest, current_price: float) -> float | None:
        if payload.type == "MARKET":
            return current_price
        if payload.type == "LIMIT" or payload.type == "GTT":
            if payload.limit_price is None:
                raise ValueError("Limit orders require limit_price.")
            return payload.limit_price
        if payload.type == "STOP":
            if payload.stop_price is None:
                raise ValueError("Stop orders require stop_price.")
            return payload.stop_price
        if payload.type == "STOP_LIMIT":
            if payload.stop_price is None or payload.limit_price is None:
                raise ValueError("Stop-Limit orders require stop_price and limit_price.")
            # store the limit price as the order_price used for the eventual limit fill
            return payload.limit_price
        return current_price

    def _try_fill_order(
        self,
        account: PaperTradingAccount,
        order: PaperOrder,
        current_price: float,
        *,
        require_market_open: bool = True,
    ) -> tuple[PaperOrder, PaperPosition | None, PaperTradeHistory | None, str]:
        if order.status in TERMINAL_ORDER_STATUSES:
            position = self.db.scalar(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.symbol == order.symbol,
                    PaperPosition.status == "OPEN",
                )
            )
            return order, position, None, "Order is already terminal."

        # Never execute outside market hours unless explicitly forced (tests only).
        if require_market_open and not trading_hours.is_market_open():
            if order.status != PENDING_MARKET_OPEN_STATUS:
                # Preserve after-hours intent if already pending market open; otherwise leave working.
                if order.status not in OPEN_ORDER_STATUSES:
                    order.status = "PENDING"
                if order.lifecycle_state not in {"TOKEN_EXPIRED_PAUSED", "ERROR_RETRYING", PENDING_MARKET_OPEN_STATUS}:
                    order.lifecycle_state = "PENDING_ENTRY"
            return order, None, None, "Market closed; order remains pending until next session."

        if current_price <= 0:
            if order.status != PENDING_MARKET_OPEN_STATUS:
                order.status = "PENDING"
            if order.lifecycle_state not in {"TOKEN_EXPIRED_PAUSED", "ERROR_RETRYING", PENDING_MARKET_OPEN_STATUS}:
                order.lifecycle_state = "PENDING_ENTRY"
            return order, None, None, "Live market price unavailable; order remains pending."

        # After-hours queue promoted to working when session is open
        if order.status == PENDING_MARKET_OPEN_STATUS:
            order.status = "PENDING"
            if order.lifecycle_state == PENDING_MARKET_OPEN_STATUS:
                order.lifecycle_state = "PENDING_ENTRY"

        should_fill = False
        if order.order_type == "MARKET":
            should_fill = True
        elif order.order_type == "LIMIT" or order.order_type == "GTT":
            should_fill = (order.side == "BUY" and current_price <= (order.order_price or current_price)) or (
                order.side == "SELL" and current_price >= (order.order_price or current_price)
            )
        elif order.order_type == "STOP":
            # STOP triggers a market fill when price crosses the stop_price
            stop_trigger = getattr(order, "stop_price", None) or order.order_price
            should_fill = (order.side == "BUY" and current_price >= (stop_trigger or current_price)) or (
                order.side == "SELL" and current_price <= (stop_trigger or current_price)
            )
        elif order.order_type == "STOP_LIMIT":
            # STOP_LIMIT triggers when stop price crossed, then behaves as LIMIT using order.order_price
            trigger_crossed = (
                (order.side == "BUY" and current_price >= (getattr(order, "stop_price", order.order_price) or current_price))
                or (order.side == "SELL" and current_price <= (getattr(order, "stop_price", order.order_price) or current_price))
            )
            # Check limit condition against stored limit price (order_price)
            limit_ok = (
                (order.side == "BUY" and current_price <= (order.order_price or current_price))
                or (order.side == "SELL" and current_price >= (order.order_price or current_price))
            )
            should_fill = trigger_crossed and limit_ok

        if not should_fill:
            order.status = "PENDING"
            if order.lifecycle_state not in {"TOKEN_EXPIRED_PAUSED", "ERROR_RETRYING"}:
                order.lifecycle_state = "PENDING_ENTRY"
            return order, None, None, "Order placed and kept pending."

        fill_price = q_price(current_price)
        order_qty = q_qty(order.qty)
        if order.side == "BUY":
            estimated_cost = q_pnl(fill_price * order_qty)
            # compute available cash using current open positions/orders
            available_cash = dec(self._build_account_summary(
                account, self._position_models(account.id), self._order_models(account.id), self._trade_models(account.id), {}
            ).available_cash)
            if estimated_cost > available_cash:
                order.status = "REJECTED"
                try:
                    trading_logger.warning(
                        "ORDER_REJECTED | order_id=%s | account=%s | symbol=%s | reason=INSUFFICIENT_CASH | cost=%s | available=%s",
                        getattr(order, "id", None),
                        account.id,
                        order.symbol,
                        estimated_cost,
                        available_cash,
                    )
                except Exception:
                    pass
                return order, None, None, "Order rejected: insufficient available cash."
            order.status = "FILLED"
            order.lifecycle_state = "ENTRY_FILLED"
            order.filled_at = datetime.now(timezone.utc)
            order.filled_price = fill_price
            order.scheduled_execution = None
            # Deduct funds and create/update OPEN position
            prior_cash = account.cash_balance
            account.cash_balance = q_pnl(dec(account.cash_balance) - estimated_cost)
            position = self.db.scalar(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.symbol == order.symbol,
                    PaperPosition.status == "OPEN",
                )
            )
            if position:
                total_cost = (dec(position.avg_entry_price) * dec(position.qty)) + estimated_cost
                position.qty = q_qty(dec(position.qty) + order_qty)
                position.avg_entry_price = q_price(total_cost / dec(position.qty))
                position.current_price = fill_price
                position.stop_loss = order.stop_loss
                position.target = order.target
                position.updated_at = datetime.now(timezone.utc)
            else:
                position = PaperPosition(
                    account_id=account.id,
                    status="OPEN",
                    lifecycle_state="OPEN_POSITION",
                    symbol=order.symbol,
                    qty=order.qty,
                    avg_entry_price=fill_price,
                    current_price=fill_price,
                    stop_loss=order.stop_loss,
                    target=order.target,
                    notes=order.notes,
                    source_signal=order.source_signal,
                    source_score=order.source_score,
                    source_confidence=order.source_confidence,
                )
                self.db.add(position)
                self.db.flush()
                try:
                    trading_logger.info(
                        "POSITION_CREATED | account=%s | position_id=%s | symbol=%s | qty=%s | avg_entry_price=%s",
                        account.id,
                        getattr(position, "id", None),
                        position.symbol,
                        position.qty,
                        position.avg_entry_price,
                    )
                except Exception:
                    pass
            account.updated_at = datetime.now(timezone.utc)
            self._record_execution_event(
                "ENTRY_FILLED",
                order.symbol,
                getattr(order, "id", None),
                getattr(position, "id", None),
                "PENDING_ENTRY",
                "ENTRY_FILLED",
                as_float(fill_price),
                f"entry-filled:{getattr(order, 'id', None) or order.idempotency_key}",
            )
            try:
                trading_logger.info(
                    "ORDER_EXECUTED | order_id=%s | account=%s | user_id=%s | symbol=%s | side=BUY | qty=%s | "
                    "filled_price=%s | status=FILLED | market_status=OPEN | execution_time=%s | position_id=%s",
                    getattr(order, "id", None),
                    account.id,
                    self.user_id,
                    order.symbol,
                    order.qty,
                    order.filled_price,
                    order.filled_at.isoformat() if order.filled_at else None,
                    getattr(position, "id", None),
                )
                trading_logger.info(
                    "CAPITAL_UPDATED | account=%s | order_id=%s | symbol=%s | side=BUY | "
                    "delta=%s | cash_before=%s | cash_after=%s",
                    account.id,
                    getattr(order, "id", None),
                    order.symbol,
                    -estimated_cost,
                    prior_cash,
                    account.cash_balance,
                )
                if position:
                    trading_logger.info(
                        "POSITION_CREATED | account=%s | position_id=%s | order_id=%s | symbol=%s | qty=%s | avg_entry_price=%s",
                        account.id,
                        getattr(position, "id", None),
                        getattr(order, "id", None),
                        position.symbol,
                        position.qty,
                        position.avg_entry_price,
                    )
            except Exception:
                pass
            return order, position, None, "Buy order filled."

        position = self.db.scalar(select(PaperPosition).where(PaperPosition.account_id == account.id, PaperPosition.symbol == order.symbol, PaperPosition.status == "OPEN"))
        if not position or dec(position.qty) < order_qty:
            order.status = "REJECTED"
            try:
                trading_logger.warning(
                    "ORDER_REJECTED | order_id=%s | account=%s | symbol=%s | reason=NOT_ENOUGH_POSITION | requested_qty=%s | available_qty=%s",
                    getattr(order, "id", None),
                    account.id,
                    order.symbol,
                    order.qty,
                    position.qty if position else 0,
                )
            except Exception:
                pass
            return order, None, None, "Order rejected: not enough position quantity to sell."

        order.status = "FILLED"
        order.lifecycle_state = "EXIT_FILLED"
        order.filled_at = datetime.now(timezone.utc)
        order.filled_price = fill_price
        order.scheduled_execution = None
        prior_cash = account.cash_balance
        account.cash_balance = q_pnl(dec(account.cash_balance) + q_pnl(fill_price * order_qty))
        pnl = q_pnl((fill_price - dec(position.avg_entry_price)) * order_qty)
        pnl_percent = q_pnl(((fill_price - dec(position.avg_entry_price)) / dec(position.avg_entry_price)) * Decimal("100")) if position.avg_entry_price else Decimal("0.00")
        trade = PaperTradeHistory(
            account_id=account.id,
            symbol=position.symbol,
            qty=order.qty,
            entry_price=position.avg_entry_price,
            exit_price=fill_price,
            pnl=pnl,
            pnl_percent=pnl_percent,
            notes=order.notes or position.notes,
            source_signal=position.source_signal,
            source_score=position.source_score,
            source_confidence=position.source_confidence,
            opened_at=position.created_at,
            closed_at=datetime.now(timezone.utc),
            exit_reason="MANUAL",
            exit_source="MANUAL",
        )
        self.db.add(trade)
        
        self.logger.info("POSITION_CLOSED | position_id=%s | symbol=%s | exit_price=%s | pnl=%s | pnl_percent=%.2f | reason=MANUAL", getattr(position, "id", None), position.symbol, fill_price, round(pnl, 2), round(pnl_percent, 2))
        # Log transaction for manual SELL to SQLite (if configured)
        try:
            tx = PaperTransaction(
                account_id=int(account.id),
                timestamp=datetime.now(timezone.utc),
                symbol=position.symbol,
                action="SELL",
                qty=int(order.qty),
                price=float(fill_price),
                amount=float(fill_price) * int(order.qty),
                balance_after=float(account.cash_balance),
            )
            self.db.add(tx)
        except Exception as e:
            print(f"ERROR in _try_fill_order (SELL tx): {e}")
            self.logger.exception("Failed to write SELL transaction to SQLite")
        if dec(position.qty) == order_qty:
            self.db.delete(position)
            updated_position = None
        else:
            position.qty = q_qty(dec(position.qty) - order_qty)
            position.current_price = fill_price
            position.updated_at = datetime.now(timezone.utc)
            updated_position = position
        try:
            trading_logger.info(
                "ORDER_EXECUTED | order_id=%s | account=%s | user_id=%s | symbol=%s | side=SELL | qty=%s | "
                "filled_price=%s | status=FILLED | market_status=OPEN | execution_time=%s | pnl=%s | pnl_percent=%.2f",
                getattr(order, "id", None),
                account.id,
                self.user_id,
                position.symbol,
                order.qty,
                fill_price,
                order.filled_at.isoformat() if order.filled_at else None,
                round(pnl, 2),
                round(pnl_percent, 2),
            )
            trading_logger.info(
                "CAPITAL_UPDATED | account=%s | order_id=%s | symbol=%s | side=SELL | "
                "delta=%s | cash_before=%s | cash_after=%s",
                account.id,
                getattr(order, "id", None),
                position.symbol,
                q_pnl(fill_price * order_qty),
                prior_cash,
                account.cash_balance,
            )
        except Exception:
            pass
        account.updated_at = datetime.now(timezone.utc)
        self._record_execution_event(
            "EXIT_FILLED",
            order.symbol,
            getattr(order, "id", None),
            getattr(position, "id", None),
            "OPEN_POSITION",
            "EXIT_FILLED",
            as_float(fill_price),
            f"exit-filled:order:{getattr(order, 'id', None) or order.idempotency_key}",
        )
        return order, updated_position, trade, "Sell order filled."

    def _record_execution_event(
        self,
        event_type: str,
        symbol: str | None,
        order_id: int | None,
        position_id: int | None,
        from_state: str | None,
        to_state: str | None,
        price: float | None,
        dedupe_key: str,
        message: str | None = None,
    ) -> None:
        if not dedupe_key:
            raise ValueError("Execution event dedupe key is required.")
        for pending in self.db.new:
            if isinstance(pending, ExecutionEvent) and pending.dedupe_key == dedupe_key:
                return
        existing = self.db.scalar(select(ExecutionEvent).where(ExecutionEvent.dedupe_key == dedupe_key))
        if existing:
            if DUPLICATE_EXECUTIONS:
                DUPLICATE_EXECUTIONS.labels(kind=event_type).inc()
            return
        if ORDER_EXECUTIONS:
            ORDER_EXECUTIONS.labels(event_type=event_type, symbol=symbol or "UNKNOWN").inc()
        self.db.add(
            ExecutionEvent(
                event_type=event_type,
                symbol=symbol,
                order_id=order_id,
                position_id=position_id,
                from_state=from_state,
                to_state=to_state,
                price=price,
                message=message,
                dedupe_key=dedupe_key,
            )
        )

    def add_notification(
        self,
        account_id: int,
        message: str,
        level: str = "info",
        event_type: str | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        dedupe_key: str | None = None,
        commit: bool = True,
    ) -> None:
        if dedupe_key:
            for pending in self.db.new:
                if isinstance(pending, PaperNotification) and pending.account_id == account_id and pending.dedupe_key == dedupe_key:
                    return
            existing = self.db.scalar(
                select(PaperNotification).where(
                    PaperNotification.account_id == account_id,
                    PaperNotification.dedupe_key == dedupe_key,
                )
            )
            if existing:
                return
        note = PaperNotification(
            account_id=account_id,
            message=message,
            level=level,
            is_read=False,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            dedupe_key=dedupe_key,
        )
        self.db.add(note)
        if commit:
            self.db.commit()

    def get_unread_notifications(self) -> list[PaperNotification]:
        account = self._get_or_create_account()
        items = list(self.db.scalars(select(PaperNotification).where(PaperNotification.account_id == account.id, PaperNotification.is_read.is_(False)).order_by(PaperNotification.created_at.desc())))
        return items

    def mark_notifications_read(self, ids: list[int]) -> None:
        account = self._get_or_create_account()
        if not ids:
            return
        rows = list(self.db.scalars(select(PaperNotification).where(PaperNotification.account_id == account.id, PaperNotification.id.in_(ids))))
        for r in rows:
            r.is_read = True
        self.db.commit()

    def get_notifications(self, unread: bool | None = None, limit: int = 10) -> list[PaperNotification]:
        account = self._get_or_create_account()
        q = select(PaperNotification).where(PaperNotification.account_id == account.id)
        if unread is True:
            q = q.where(PaperNotification.is_read.is_(False))
        q = q.order_by(PaperNotification.created_at.desc()).limit(limit)
        items = list(self.db.scalars(q))
        return items

    def mark_all_notifications_read(self) -> int:
        account = self._get_or_create_account()
        rows = list(self.db.scalars(select(PaperNotification).where(PaperNotification.account_id == account.id, PaperNotification.is_read.is_(False))))
        for r in rows:
            r.is_read = True
        self.db.commit()
        return len(rows)

    def create_alert(self, symbol: str, condition: str, price: float) -> PaperAlert:
        account = self._get_or_create_account()
        symbol = symbol.strip().upper()
        if condition not in (">=", "<="):
            raise ValueError("Invalid condition; use '>=' or '<='")
        alert = PaperAlert(account_id=account.id, symbol=symbol, condition=condition, target_price=float(price), status="ACTIVE")
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def get_alerts(self) -> list[PaperAlert]:
        account = self._get_or_create_account()
        items = list(self.db.scalars(select(PaperAlert).where(PaperAlert.account_id == account.id).order_by(PaperAlert.created_at.desc())))
        return items

    def delete_alert(self, alert_id: int) -> None:
        account = self._get_or_create_account()
        alert = self.db.scalar(select(PaperAlert).where(PaperAlert.id == alert_id, PaperAlert.account_id == account.id))
        if not alert:
            raise ValueError("Alert not found")
        self.db.delete(alert)
        self.db.commit()

    def get_active_alerts(self) -> list[PaperAlert]:
        """
        User-scoped: only this user's alerts.
        System-scoped (no user_id): all active alerts across accounts for the monitor loop.
        """
        if self.user_id is not None:
            account = self._get_or_create_account()
            return list(
                self.db.scalars(
                    select(PaperAlert).where(
                        PaperAlert.account_id == account.id,
                        PaperAlert.status == "ACTIVE",
                    )
                )
            )
        return list(
            self.db.scalars(select(PaperAlert).where(PaperAlert.status == "ACTIVE"))
        )

    def trigger_alert(self, alert_id: int, triggered_price: float) -> None:
        """Trigger by alert id. System path uses the alert's own account_id (multi-user safe)."""
        alert = self.db.scalar(select(PaperAlert).where(PaperAlert.id == alert_id, PaperAlert.status == "ACTIVE"))
        if not alert:
            return
        if self.user_id is not None:
            account = self._get_or_create_account()
            if alert.account_id != account.id:
                return
        alert.status = "TRIGGERED"
        alert.triggered_at = datetime.now(timezone.utc)
        alert.triggered_price = float(triggered_price)
        self.db.commit()
        try:
            msg = f"Price alert: {alert.symbol} {alert.condition} ₹{round(triggered_price,2)}"
            self.add_notification(int(alert.account_id), msg, level="success")
        except Exception as e:
            print(f"ERROR adding notification for triggered alert: {e}")
            self.logger.exception("Failed to add notification for triggered alert")

    def auto_exit(self, position_id: int, fill_price: float, reason: str = "MANUAL", source: str = "MANUAL") -> PaperOrderActionResponse:
        # Load position first — never use a global/shared account for exits
        query = select(PaperPosition).where(
            PaperPosition.id == position_id,
            PaperPosition.status == "OPEN",
        )
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        position = self.db.scalar(query)
        if not position:
            raise ValueError("Position not found.")

        # User-scoped path: reject cross-user exits
        if self.user_id is not None:
            user_account = self._get_or_create_account(for_update=True)
            if position.account_id != user_account.id:
                raise ValueError("Position not found.")
            account = user_account
        else:
            account = self.get_account_by_id(position.account_id, for_update=True)

        dedupe_key = f"exit-filled:{position.id}:{reason}"
        if self.db.scalar(select(ExecutionEvent).where(ExecutionEvent.dedupe_key == dedupe_key)):
            raise ValueError("Position exit has already been processed.")
        fill_price_dec = q_price(fill_price)

        # Create a filled sell order representing the exit
        order = PaperOrder(
            account_id=account.id,
            symbol=position.symbol,
            side="SELL",
            order_type="MARKET",
            product_type="CNC",
            qty=position.qty,
            order_price=fill_price_dec,
            stop_price=None,
            stop_loss=None,
            target=None,
            status="FILLED",
            lifecycle_state="EXIT_FILLED",
            notes=f"Auto exit: {reason} (Source: {source})",
            filled_price=fill_price_dec,
            filled_at=datetime.now(timezone.utc),
        )
        self.db.add(order)
        self.db.flush()

        pnl = q_pnl((fill_price_dec - dec(position.avg_entry_price)) * dec(position.qty))
        pnl_percent = q_pnl(((fill_price_dec - dec(position.avg_entry_price)) / dec(position.avg_entry_price)) * Decimal("100")) if position.avg_entry_price else Decimal("0.00")
        trade = PaperTradeHistory(
            account_id=account.id,
            symbol=position.symbol,
            qty=position.qty,
            entry_price=position.avg_entry_price,
            exit_price=fill_price_dec,
            pnl=pnl,
            pnl_percent=pnl_percent,
            notes=position.notes,
            source_signal=position.source_signal,
            source_score=position.source_score,
            source_confidence=position.source_confidence,
            opened_at=position.created_at,
            closed_at=datetime.now(timezone.utc),
            exit_reason=reason,
            exit_source=source,
        )
        self.db.add(trade)
        
        self.logger.info("POSITION_CLOSED | position_id=%s | symbol=%s | exit_price=%s | pnl=%s | pnl_percent=%.2f | reason=%s | source=%s", position.id, position.symbol, fill_price_dec, round(pnl, 2), round(pnl_percent, 2), reason, source)

        # Credit account and remove position
        account.cash_balance = q_pnl(dec(account.cash_balance) + q_pnl(fill_price_dec * dec(position.qty)))
        account.updated_at = datetime.now(timezone.utc)
        self._record_execution_event(
            "EXIT_FILLED",
            position.symbol,
            order.id,
            position.id,
            "OPEN_POSITION",
            "EXIT_FILLED",
            as_float(fill_price_dec),
            dedupe_key,
            message=f"Auto exit: {reason}",
        )
        self.db.delete(position)
        self.db.commit()

        # Create a notification
        try:
            if reason == "TARGET_HIT":
                msg = f"{position.symbol} sold at ₹{round(fill_price,2)} — Target Hit"
                level = "success"
            elif reason == "STOPLOSS_HIT":
                msg = f"{position.symbol} sold at ₹{round(fill_price,2)} — Stop Loss Hit"
                level = "error"
            else:
                msg = f"{position.symbol} sold at ₹{round(fill_price,2)} — {reason}"
                level = "info"
            self.add_notification(
                account.id,
                msg,
                level,
                "EXIT_FILLED",
                "position",
                position.id,
                dedupe_key=f"exit-filled:{position.id}:{reason}",
            )
        except Exception as e:
            print(f"ERROR adding notification for auto_exit: {e}")
            self.logger.exception("Failed to add notification for auto_exit")

        # Log transaction for AUTO_EXIT to SQLite
        try:
            tx = PaperTransaction(
                account_id=int(account.id),
                timestamp=datetime.now(timezone.utc),
                symbol=position.symbol,
                action="AUTO_EXIT",
                qty=int(position.qty),
                price=float(fill_price),
                amount=float(fill_price) * int(position.qty),
                balance_after=float(account.cash_balance),
            )
            self.db.add(tx)
            self.db.commit()
            try:
                trading_logger.info(
                    "AUTO_EXIT | account=%s | symbol=%s | qty=%s | price=%s | pnl=%s | pnl_percent=%.2f | reason=%s",
                    int(account.id),
                    position.symbol,
                    int(position.qty),
                    float(fill_price),
                    round(pnl, 2),
                    round(pnl_percent, 2),
                    reason,
                )
            except Exception:
                pass
        except Exception as e:
            print(f"ERROR writing AUTO_EXIT transaction to SQLite: {e}")
            self.logger.exception("Failed to write AUTO_EXIT transaction to SQLite")

        return PaperOrderActionResponse(
            account=self.get_dashboard(selected_symbol=position.symbol).account,
            order=self._serialize_order(order),
            position=None,
            trade=self._serialize_trade(trade),
            message=f"Position auto-exited: {position.symbol} reason={reason}",
        )

    def square_off_all(self) -> PaperTradingDashboardResponse:
        account = self._get_or_create_account()
        positions = self._position_models(account.id)
        for pos in positions:
            try:
                price_snapshot = self._price_snapshot(pos.symbol)
                self.auto_exit(pos.id, price_snapshot.current_price, "MANUAL")
            except Exception as e:
                print(f"ERROR squaring off position {pos.symbol}: {e}")
                self.logger.exception("Failed to square off position %s", pos.symbol)
        return self.get_dashboard()

    def _refresh_pending_orders(self, account_id: int) -> None:
        """
        Re-evaluate working orders for this account.

        - When market is CLOSED: leave PENDING_MARKET_OPEN orders untouched (no position, no capital).
        - When market is OPEN: promote PENDING_MARKET_OPEN and attempt fills for all open orders.
        """
        if not trading_hours.is_market_open():
            return

        pending_orders = list(
            self.db.scalars(
                select(PaperOrder).where(
                    PaperOrder.account_id == account_id,
                    PaperOrder.status.in_(tuple(OPEN_ORDER_STATUSES)),
                )
            )
        )
        if not pending_orders:
            return

        symbols = {o.symbol for o in pending_orders}
        self.db.commit()  # Release connection before network I/O
        price_cache = self._load_price_cache(symbols)

        # Re-fetch since we committed
        account = self._get_or_create_account(for_update=True)
        pending_orders = list(
            self.db.scalars(
                select(PaperOrder).where(
                    PaperOrder.account_id == account_id,
                    PaperOrder.status.in_(tuple(OPEN_ORDER_STATUSES)),
                )
            )
        )
        for order in pending_orders:
            price = price_cache.get(order.symbol)
            if not price or price.current_price <= 0:
                continue
            was_pending_market_open = order.status == PENDING_MARKET_OPEN_STATUS
            order.last_evaluated_at = datetime.now(timezone.utc)
            order.last_seen_ltp = price.current_price
            filled, position, trade, _msg = self._try_fill_order(
                account, order, price.current_price, require_market_open=True
            )
            if was_pending_market_open and filled.status in {"FILLED", "EXECUTED"}:
                try:
                    trading_logger.info(
                        "MARKET_OPEN_TRIGGER | account=%s | order_id=%s | symbol=%s | side=%s | qty=%s | "
                        "status=%s | execution_time=%s",
                        account.id,
                        filled.id,
                        filled.symbol,
                        filled.side,
                        filled.qty,
                        filled.status,
                        filled.filled_at.isoformat() if filled.filled_at else None,
                    )
                except Exception:
                    pass
                try:
                    if filled.side == "BUY":
                        tx = PaperTransaction(
                            account_id=int(account.id),
                            timestamp=datetime.now(timezone.utc),
                            symbol=filled.symbol,
                            action="BUY",
                            qty=int(filled.qty),
                            price=float(filled.filled_price) if filled.filled_price is not None else None,
                            amount=-float(filled.filled_price or 0.0) * int(filled.qty),
                            balance_after=float(account.cash_balance),
                        )
                        self.db.add(tx)
                        self.add_notification(
                            account.id,
                            (
                                f"Your BUY order for {filled.symbol} has been executed successfully. "
                                f"Position has been added to your portfolio."
                            ),
                            "success",
                            "ORDER_EXECUTED",
                            "order",
                            filled.id,
                            dedupe_key=f"entry-filled:{filled.id}",
                            commit=False,
                        )
                    elif filled.side == "SELL":
                        self.add_notification(
                            account.id,
                            f"Your SELL order for {filled.symbol} has been executed successfully.",
                            "success",
                            "ORDER_EXECUTED",
                            "order",
                            filled.id,
                            dedupe_key=f"exit-filled:{filled.id}",
                            commit=False,
                        )
                except Exception:
                    self.logger.exception("Failed post-execution bookkeeping for order_id=%s", filled.id)

    def execute_pending_market_open_orders_for_account(self, account_id: int | None = None) -> dict:
        """
        Execute all PENDING_MARKET_OPEN orders for one account (or current user's account).
        Intended for market-open scheduler and dashboard refresh.
        """
        if not trading_hours.is_market_open():
            return {"executed": 0, "rejected": 0, "still_pending": 0, "market_open": False}

        account = (
            self.get_account_by_id(int(account_id), for_update=True)
            if account_id is not None
            else self._get_or_create_account(for_update=True)
        )
        self._refresh_pending_orders(account.id)
        self.db.commit()
        remaining = list(
            self.db.scalars(
                select(PaperOrder).where(
                    PaperOrder.account_id == account.id,
                    PaperOrder.status == PENDING_MARKET_OPEN_STATUS,
                )
            )
        )
        return {
            "executed": 0,  # detailed counts computed by global runner
            "rejected": 0,
            "still_pending": len(remaining),
            "market_open": True,
            "account_id": account.id,
        }

    @staticmethod
    def execute_all_pending_market_open_orders() -> dict:
        """
        System-wide market-open sweep: load every PENDING_MARKET_OPEN order and execute.
        Safe to call repeatedly (idempotent for already-filled orders).
        """
        from ..db.session import SessionLocal

        summary = {
            "market_open": trading_hours.is_market_open(),
            "processed": 0,
            "executed": 0,
            "rejected": 0,
            "still_pending": 0,
            "errors": 0,
        }
        if not summary["market_open"]:
            return summary

        try:
            trading_logger.info(
                "MARKET_OPEN_TRIGGER | scope=ALL | status=%s | next_action=execute_pending",
                trading_hours.get_market_status().get("status"),
            )
        except Exception:
            pass

        with SessionLocal() as db:
            order_ids = list(
                db.scalars(
                    select(PaperOrder.id).where(PaperOrder.status == PENDING_MARKET_OPEN_STATUS)
                )
            )
        for oid in order_ids:
            try:
                with SessionLocal() as db:
                    order = db.get(PaperOrder, oid)
                    if not order or order.status != PENDING_MARKET_OPEN_STATUS:
                        continue
                    svc = PaperTradingService(db)  # system path
                    account = svc.get_account_by_id(int(order.account_id), for_update=True)
                    snap = svc._price_snapshot(order.symbol)
                    price = snap.current_price if snap else 0.0
                    if price <= 0:
                        summary["still_pending"] += 1
                        summary["processed"] += 1
                        continue
                    filled, position, trade, message = svc._try_fill_order(
                        account, order, price, require_market_open=True
                    )
                    summary["processed"] += 1
                    if filled.status in {"FILLED", "EXECUTED"}:
                        summary["executed"] += 1
                        try:
                            trading_logger.info(
                                "MARKET_OPEN_TRIGGER | order_id=%s | account=%s | symbol=%s | status=EXECUTED | price=%s",
                                filled.id,
                                account.id,
                                filled.symbol,
                                filled.filled_price,
                            )
                        except Exception:
                            pass
                        if filled.side == "BUY":
                            tx = PaperTransaction(
                                account_id=int(account.id),
                                timestamp=datetime.now(timezone.utc),
                                symbol=filled.symbol,
                                action="BUY",
                                qty=int(filled.qty),
                                price=float(filled.filled_price) if filled.filled_price is not None else None,
                                amount=-float(filled.filled_price or 0.0) * int(filled.qty),
                                balance_after=float(account.cash_balance),
                            )
                            db.add(tx)
                            svc.add_notification(
                                account.id,
                                (
                                    f"Your BUY order for {filled.symbol} has been executed successfully. "
                                    f"Position has been added to your portfolio."
                                ),
                                "success",
                                "ORDER_EXECUTED",
                                "order",
                                filled.id,
                                dedupe_key=f"entry-filled:{filled.id}",
                                commit=False,
                            )
                        elif filled.side == "SELL":
                            svc.add_notification(
                                account.id,
                                f"Your SELL order for {filled.symbol} has been executed successfully.",
                                "success",
                                "ORDER_EXECUTED",
                                "order",
                                filled.id,
                                dedupe_key=f"exit-filled:{filled.id}",
                                commit=False,
                            )
                    elif filled.status == "REJECTED":
                        summary["rejected"] += 1
                        svc.add_notification(
                            account.id,
                            f"Order for {filled.symbol} rejected at market open: {message}",
                            "error",
                            "ORDER_REJECTED",
                            "order",
                            filled.id,
                            dedupe_key=f"order-rejected-open:{filled.id}",
                            commit=False,
                        )
                    else:
                        summary["still_pending"] += 1
                    db.commit()
            except Exception:
                summary["errors"] += 1
                try:
                    trading_logger.exception(
                        "MARKET_OPEN_TRIGGER | order_id=%s | error=execution_failed", oid
                    )
                except Exception:
                    pass
        return summary

    def _load_price_cache(self, symbols: set[str]) -> dict[str, PriceSnapshot]:
        cache: dict[str, PriceSnapshot] = {}
        if not symbols:
            return cache
        normalized = {s.strip().upper() for s in symbols if s.strip()}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(normalized), 10)) as pool:
            fut_map = {pool.submit(self._price_snapshot, sym): sym for sym in normalized}
            for future in concurrent.futures.as_completed(fut_map):
                sym = fut_map[future]
                try:
                    cache[sym] = future.result()
                except Exception:
                    self.logger.exception("Failed to load price snapshot for symbol=%s", sym)
        return cache

    def _price_snapshot(self, symbol: str) -> PriceSnapshot:
        import time as _time
        now = _time.monotonic()
        with _price_snapshot_cache_lock:
            cached = _price_snapshot_cache.get(symbol)
            if cached and (now - cached[1]) < _PRICE_CACHE_TTL_SEC:
                return cached[0]

        from .fyers_service import _run_sync
        candles = _run_sync(self.fyers_service.fetch_ohlcv(symbol, AnalysisMode.swing, "1d", 90))
        if not candles:
            self.logger.warning("No OHLCV candles available for price snapshot | symbol=%s", symbol)
            try:
                import yfinance as yf
                clean = symbol.replace("NSE:", "").replace("-EQ", "").strip()
                yf_sym = f"{clean}.NS"
                df = yf.download(yf_sym, period="6mo", interval="1d", progress=False)
                if df is not None and not df.empty:
                    candles = []
                    for index, row in df.iterrows():
                        dt = index
                        if hasattr(dt, "to_pydatetime"):
                            dt = dt.to_pydatetime()
                        if dt.tzinfo is not None:
                            dt = dt.replace(tzinfo=None)
                        open_val = float(row["Open"]) if isinstance(row["Open"], (int, float)) else float(row["Open"].iloc[0])
                        high_val = float(row["High"]) if isinstance(row["High"], (int, float)) else float(row["High"].iloc[0])
                        low_val = float(row["Low"]) if isinstance(row["Low"], (int, float)) else float(row["Low"].iloc[0])
                        close_val = float(row["Close"]) if isinstance(row["Close"], (int, float)) else float(row["Close"].iloc[0])
                        vol_val = safe_int(row["Volume"], field="volume") if isinstance(row["Volume"], (int, float)) else safe_int(row["Volume"].iloc[0], field="volume")
                        candles.append(OHLCVPoint(
                            timestamp=dt, open=open_val, high=high_val,
                            low=low_val, close=close_val, volume=vol_val,
                        ))
                    self.logger.info("YFINANCE_CANDLES_FALLBACK | symbol=%s | candles=%s", symbol, len(candles))
                else:
                    self.logger.warning("YFINANCE_CANDLES_EMPTY | symbol=%s", symbol)
            except Exception as yf_err:
                self.logger.warning("YFINANCE_CANDLES_FALLBACK_FAILED | symbol=%s | error=%s", symbol, str(yf_err)[:120])

        low_level_price = None
        if candles:
            low_level_price = candles[-1].close

        import asyncio; from ..db.session import main_event_loop
        try:
            future = asyncio.run_coroutine_threadsafe(self.fyers_service.fetch_ltp(symbol), main_event_loop)
            ltp = future.result(timeout=5)
        except Exception as e:
            self.logger.exception(f'Error fetching ltp: {e}')
            ltp = None

        source = "FYERS_QUOTE"
        current_price = ltp
        if current_price is None:
            if settings.app_env == "test":
                current_price = 150.0
                source = "TEST_MOCK"
            elif candles:
                current_price = low_level_price
                source = "CANDLE_FALLBACK"
            else:
                current_price = 0.0
                source = "NO_DATA"
        if current_price is not None and current_price <= 0 and settings.app_env == "test":
            current_price = 150.0
            source = "TEST_MOCK"
        elif current_price is None:
            current_price = 0.0

        if current_price <= 0 and source != "TEST_MOCK":
            self.logger.warning("PRICE_SNAPSHOT_FAILURE | No current price available for symbol %s; using 0.0 default", symbol)
            # Last resort: try yfinance LTP directly
            if settings.app_env != "test":
                try:
                    import yfinance as yf
                    clean = symbol.replace("NSE:", "").replace("-EQ", "").strip()
                    yf_sym = f"{clean}.NS"
                    ticker = yf.Ticker(yf_sym)
                    data = ticker.history(period="5d")
                    if not data.empty:
                        current_price = round(float(data["Close"].iloc[-1]), 2)
                        source = "YFINANCE_LTP"
                        self.logger.info("PRICE_SNAPSHOT_YFINANCE_LTP | symbol=%s | ltp=%s", symbol, current_price)
                except Exception:
                    pass
        else:
            self.logger.info("PRICE_SNAPSHOT_SUCCESS | symbol=%s | ltp=%s | source=%s", symbol, current_price, source)

        frame = pd.DataFrame()
        if candles:
            frame = pd.DataFrame(
                {
                    "high": [item.high for item in candles],
                    "low": [item.low for item in candles],
                    "close": [item.close for item in candles],
                }
            )
        ema_20 = float(EMAIndicator(close=frame["close"], window=20).ema_indicator().iloc[-1]) if len(frame) >= 20 else None
        supertrend = self._approx_supertrend(frame) if not frame.empty else None
        result = PriceSnapshot(
            symbol=symbol,
            current_price=current_price,
            candles=candles[-60:] if candles else [],
            ema_20=ema_20,
            supertrend=supertrend,
            source=source,
            fetched_at=datetime.now(timezone.utc),
        )
        with _price_snapshot_cache_lock:
            _price_snapshot_cache[symbol] = (result, _time.monotonic())
        return result

    def _approx_supertrend(self, frame: pd.DataFrame) -> float | None:
        if len(frame) < 10:
            return None
        tr = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - frame["close"].shift(1)).abs(),
                (frame["low"] - frame["close"].shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.ewm(alpha=1 / 10, adjust=False).mean().iloc[-1]
        hl2 = ((frame["high"].iloc[-1] + frame["low"].iloc[-1]) / 2)
        value = hl2 - (3 * atr)
        return float(value) if isfinite(value) else None

    def _build_account_summary(
        self,
        account: PaperTradingAccount,
        positions: list[PaperPosition],
        orders: list[PaperOrder],
        trades: list[PaperTradeHistory],
        price_cache: dict[str, PriceSnapshot],
    ) -> PaperAccountSummary:
        realized_dec = q_pnl(sum((dec(item.pnl) for item in trades), Decimal("0")))
        invested = Decimal("0")
        unrealized = Decimal("0")
        for position in positions:
            cached = price_cache.get(position.symbol)
            raw_price = cached.current_price if (cached and cached.current_price > 0) else position.current_price
            current_price = dec(raw_price if raw_price > 0 else position.avg_entry_price)
            invested += dec(position.avg_entry_price) * dec(position.qty)
            unrealized += (current_price - dec(position.avg_entry_price)) * dec(position.qty)
        reserved_cash = Decimal("0")
        for order in orders:
            # Do NOT reserve capital for PENDING_MARKET_OPEN (per market-hours lifecycle).
            # Only reserve for in-session working limit/GTT buys.
            if (
                order.status in {"PENDING", "OPEN", "PARTIALLY_EXECUTED"}
                and order.side == "BUY"
                and order.order_type in ["LIMIT", "GTT"]
            ):
                cached = price_cache.get(order.symbol)
                snap_price = cached.current_price if cached else None
                if order.order_price and order.order_price > 0:
                    order_price = dec(order.order_price)
                elif snap_price and snap_price > 0:
                    order_price = dec(snap_price)
                else:
                    order_price = dec(position.avg_entry_price) if positions else dec("100")
                reserved_cash += order_price * dec(order.qty)
        position_value = sum(
            (
                dec(
                    (price_cache.get(item.symbol).current_price if item.symbol in price_cache and price_cache[item.symbol].current_price > 0 else item.current_price)
                    if price_cache.get(item.symbol) else item.current_price
                ) * dec(item.qty)
                for item in positions
            ),
            Decimal("0"),
        )
        equity = q_pnl(dec(account.cash_balance) + position_value)
        return PaperAccountSummary(
            account_id=account.id,
            account_name=account.name,
            base_currency=account.base_currency,
            starting_balance=as_float(q_pnl(account.starting_balance)),
            balance=as_float(q_pnl(account.cash_balance)),
            equity=as_float(equity),
            realized_pnl=as_float(realized_dec),
            unrealized_pnl=as_float(q_pnl(unrealized)),
            total_invested=as_float(q_pnl(invested)),
            reserved_cash=as_float(q_pnl(reserved_cash)),
            available_cash=as_float(q_pnl(dec(account.cash_balance) - reserved_cash)),
            open_positions_count=len(positions),
            open_orders_count=len([item for item in orders if item.status in OPEN_ORDER_STATUSES]),
            max_risk_per_trade=as_float(account.max_risk_per_trade),
            updated_at=datetime.now(timezone.utc),
        )

    def _serialize_position(self, position: PaperPosition, snapshot: PriceSnapshot | None = None) -> PaperPositionResponse:
        current_price = dec(position.current_price)
        avg_entry = dec(position.avg_entry_price)
        qty = dec(position.qty)
        # If current_price is 0 or invalid, use snapshot price or avg_entry (break-even fallback)
        if current_price <= 0 and snapshot and snapshot.current_price > 0:
            current_price = dec(snapshot.current_price)
        elif current_price <= 0:
            current_price = avg_entry
        unrealized = q_pnl((current_price - avg_entry) * qty)
        unrealized_pct = q_pnl(((current_price - avg_entry) / avg_entry) * Decimal("100")) if avg_entry else Decimal("0.00")
        risk_reward = None
        if position.stop_loss and position.target:
            risk = abs(avg_entry - dec(position.stop_loss))
            reward = abs(dec(position.target) - avg_entry)
            risk_reward = as_float(q_pnl(reward / risk)) if risk else None
        return PaperPositionResponse(
            id=position.id,
            symbol=position.symbol,
            qty=int(qty),
            avg_entry_price=as_float(q_price(avg_entry)),
            current_price=as_float(q_price(current_price)),
            unrealized_pnl=as_float(unrealized),
            unrealized_pnl_percent=as_float(unrealized_pct),
            invested_value=as_float(q_pnl(avg_entry * qty)),
            stop_loss=as_float(q_price(position.stop_loss)) if position.stop_loss else None,
            target=as_float(q_price(position.target)) if position.target else None,
            lifecycle_state=position.lifecycle_state,
            monitor_enabled=bool(position.monitor_enabled),
            paused_reason=position.paused_reason,
            risk_reward_ratio=risk_reward,
            source_signal=position.source_signal,
            source_score=position.source_score,
            source_confidence=position.source_confidence,
            price_source=snapshot.source if snapshot else None,
            price_fetched_at=snapshot.fetched_at if snapshot else None,
            is_price_stale=(snapshot.source != "FYERS_QUOTE") if snapshot else False,
            created_at=position.created_at,
            updated_at=position.updated_at,
        )

    def _serialize_order(self, order: PaperOrder, snapshot: PriceSnapshot | None = None) -> PaperOrderResponse:
        filled_price = as_float(q_price(order.filled_price)) if order.filled_price is not None else None
        return PaperOrderResponse(
            id=order.id,
            symbol=order.symbol,
            side=order.side,  # type: ignore[arg-type]
            type=order.order_type,  # type: ignore[arg-type]
            qty=int(dec(order.qty)),
            price=as_float(q_price(order.order_price)) if order.order_price is not None else None,
            stop_price=as_float(q_price(order.stop_price)) if getattr(order, "stop_price", None) is not None else None,
            stop_loss=as_float(q_price(order.stop_loss)) if order.stop_loss is not None else None,
            target=as_float(q_price(order.target)) if order.target is not None else None,
            status=order.status,  # type: ignore[arg-type]
            lifecycle_state=order.lifecycle_state,  # type: ignore[arg-type]
            requested_entry_price=as_float(q_price(order.requested_entry_price)) if order.requested_entry_price is not None else None,
            execution_price=filled_price,
            monitor_enabled=bool(order.monitor_enabled),
            paused_reason=order.paused_reason,
            notes=order.notes,
            source_signal=order.source_signal,
            source_score=order.source_score,
            source_confidence=order.source_confidence,
            last_evaluated_at=order.last_evaluated_at,
            last_seen_ltp=as_float(q_price(order.last_seen_ltp)) if order.last_seen_ltp is not None else None,
            price_source=snapshot.source if snapshot else None,
            price_fetched_at=snapshot.fetched_at if snapshot else None,
            is_price_stale=(snapshot.source != "FYERS_QUOTE") if snapshot else False,
            created_at=order.created_at,
            scheduled_execution=getattr(order, "scheduled_execution", None),
            executed_at=order.filled_at,
            filled_at=order.filled_at,
            filled_price=filled_price,
            market_session=getattr(order, "market_session", None),
            product_type=getattr(order, "product_type", None),
        )

    def _serialize_trade(self, trade: PaperTradeHistory) -> PaperTradeHistoryItem:
        holding_period = (trade.closed_at - trade.opened_at).total_seconds() / 3600
        return PaperTradeHistoryItem(
            id=trade.id,
            symbol=trade.symbol,
            qty=int(dec(trade.qty)),
            entry_price=as_float(q_price(trade.entry_price)),
            exit_price=as_float(q_price(trade.exit_price)),
            pnl=as_float(q_pnl(trade.pnl)),
            pnl_percent=as_float(q_pnl(trade.pnl_percent)),
            notes=trade.notes,
            source_signal=trade.source_signal,
            source_score=trade.source_score,
            source_confidence=trade.source_confidence,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            exit_reason=getattr(trade, "exit_reason", None),
            exit_source=getattr(trade, "exit_source", None),
            holding_period_hours=round(holding_period, 2),
        )

    def _workspace_snapshot(self, symbol: str | None, cache: dict[str, PriceSnapshot]) -> PaperWorkspaceSnapshot | None:
        if not symbol:
            return None
        snapshot = cache.get(symbol) or self._price_snapshot(symbol)
        position = self.db.scalar(select(PaperPosition).where(PaperPosition.symbol == symbol))
        return self._workspace_from_snapshot(
            snapshot,
            position.source_signal if position else None,
            position.source_score if position else None,
            position.source_confidence if position else None,
        )

    def _workspace_from_snapshot(
        self,
        snapshot: PriceSnapshot,
        source_signal: str | None,
        source_score: float | None,
        source_confidence: float | None,
    ) -> PaperWorkspaceSnapshot:
        return PaperWorkspaceSnapshot(
            symbol=snapshot.symbol,
            current_price=round(snapshot.current_price, 2),
            candles=snapshot.candles,
            ema_20=round(snapshot.ema_20, 2) if snapshot.ema_20 is not None else None,
            supertrend=round(snapshot.supertrend, 2) if snapshot.supertrend is not None else None,
            source_signal=source_signal,
            source_score=source_score,
            source_confidence=source_confidence,
            price_source=snapshot.source,
            price_fetched_at=snapshot.fetched_at,
            is_price_stale=(snapshot.source != "FYERS_QUOTE"),
        )

    @staticmethod
    def _aware_dt(dt: datetime | None) -> datetime | None:
        """Normalize naive/aware datetimes so analytics never raises on subtract."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def _analytics_period_bounds(period: str) -> tuple[datetime | None, datetime | None, str]:
        """Return (start_utc, end_utc, label). None start means all-time."""
        from zoneinfo import ZoneInfo

        IST = ZoneInfo("Asia/Kolkata")
        now_ist = datetime.now(IST)
        today = now_ist.date()
        end = now_ist.astimezone(timezone.utc) + timedelta(seconds=1)

        def day_start(d):
            return datetime.combine(d, dt_time.min, tzinfo=IST).astimezone(timezone.utc)

        p = (period or "all").lower().strip()
        if p in ("today",):
            return day_start(today), end, "Today"
        if p in ("week", "this_week"):
            start = today - timedelta(days=today.weekday())
            return day_start(start), end, "This Week"
        if p in ("month", "this_month"):
            start = today.replace(day=1)
            return day_start(start), end, "This Month"
        if p in ("last_month",):
            first_this = today.replace(day=1)
            last_prev = first_this - timedelta(days=1)
            start = last_prev.replace(day=1)
            return day_start(start), day_start(first_this), "Last Month"
        if p in ("last_3_months", "3m"):
            return day_start(today - timedelta(days=90)), end, "Last 3 Months"
        if p in ("last_6_months", "6m"):
            return day_start(today - timedelta(days=180)), end, "Last 6 Months"
        if p in ("last_year", "year", "1y"):
            return day_start(today - timedelta(days=365)), end, "Last Year"
        # all time
        return None, end, "All Time"

    def get_analytics(self, period: str = "all") -> dict:
        """Full paper-trading analytics dashboard payload.

        Always returns JSON-safe floats (never Decimal). Empty-history accounts
        get zeroed defaults so the UI can render charts without erroring.
        """
        import math
        from collections import defaultdict

        account = self._get_or_create_account()
        all_trades = self._trade_models(account.id)
        start_utc, end_utc, range_label = self._analytics_period_bounds(period)

        def in_range(t: PaperTradeHistory) -> bool:
            closed = self._aware_dt(t.closed_at)
            if closed is None:
                return False
            if start_utc and closed < start_utc:
                return False
            if end_utc and closed >= end_utc:
                return False
            return True

        trades = [t for t in all_trades if in_range(t)]
        positions = self._position_models(account.id)
        open_positions = [p for p in positions if (p.status or "").upper() == "OPEN"]
        orders = self._order_models(account.id)

        def fnum(v) -> float:
            try:
                return as_float(v)
            except Exception:
                try:
                    return float(v or 0)
                except Exception:
                    return 0.0

        total_trades = len(trades)
        wins = [t for t in trades if fnum(t.pnl) > 0]
        losses = [t for t in trades if fnum(t.pnl) < 0]
        sum_wins = round(sum(fnum(t.pnl) for t in wins), 2)
        sum_losses = round(sum(fnum(t.pnl) for t in losses), 2)  # negative or zero
        gross_loss_abs = abs(sum_losses)

        profit_factor: float | None = None
        if gross_loss_abs > 1e-9:
            profit_factor = round(sum_wins / gross_loss_abs, 2)
        elif sum_wins > 0:
            profit_factor = 99.0

        average_profit = round(sum_wins / len(wins), 2) if wins else None
        average_loss = round(sum_losses / len(losses), 2) if losses else None
        avg_rr = None
        if average_profit is not None and average_loss is not None and abs(average_loss) > 1e-9:
            avg_rr = round(abs(average_profit / average_loss), 2)

        best_trade = max(trades, key=lambda t: fnum(t.pnl)) if trades else None
        worst_trade = min(trades, key=lambda t: fnum(t.pnl)) if trades else None

        # Today's realized (IST calendar day) from all history, not just filtered set
        from zoneinfo import ZoneInfo
        IST = ZoneInfo("Asia/Kolkata")
        today_ist = datetime.now(IST).date()
        todays_pnl = 0.0
        for t in all_trades:
            closed = self._aware_dt(t.closed_at)
            if closed and closed.astimezone(IST).date() == today_ist:
                todays_pnl += fnum(t.pnl)
        todays_pnl = round(todays_pnl, 2)

        # Unrealized / portfolio from open positions
        unrealized = round(sum(fnum(p.unrealized_pnl) for p in open_positions), 2)
        invested = round(
            sum(fnum(p.avg_entry_price) * fnum(p.qty) for p in open_positions), 2
        )
        cash = round(fnum(account.cash_balance), 2)
        starting = round(fnum(account.starting_balance), 2) or 1_000_000.0
        realized_all = round(sum(fnum(t.pnl) for t in all_trades), 2)
        realized_period = round(sum(fnum(t.pnl) for t in trades), 2)
        portfolio_value = round(cash + invested + unrealized, 2)
        total_pnl = round(realized_period + unrealized, 2)
        roi_pct = round(((portfolio_value - starting) / starting) * 100, 2) if starting else 0.0

        # Daily + monthly + equity curve
        daily_map: dict[str, float] = {}
        monthly_map: dict[str, float] = {}
        for t in trades:
            closed = self._aware_dt(t.closed_at)
            if closed is None:
                continue
            local = closed.astimezone(IST)
            dkey = local.date().isoformat()
            mkey = local.strftime("%Y-%m")
            pnl = fnum(t.pnl)
            daily_map[dkey] = daily_map.get(dkey, 0.0) + pnl
            monthly_map[mkey] = monthly_map.get(mkey, 0.0) + pnl

        sorted_dates = sorted(daily_map.keys())
        daily_pnl = [{"date": d, "pnl": round(daily_map[d], 2)} for d in sorted_dates]
        monthly_pnl = [{"date": m, "pnl": round(monthly_map[m], 2)} for m in sorted(monthly_map.keys())]

        cumulative_pnl = []
        equity_curve = []
        capital_growth = []
        running = 0.0
        peak_equity = starting
        max_drawdown = 0.0
        daily_returns: list[float] = []
        prev_equity = starting
        for d in sorted_dates:
            running += daily_map[d]
            equity = starting + running
            peak_equity = max(peak_equity, equity)
            dd = peak_equity - equity
            max_drawdown = max(max_drawdown, dd)
            cumulative_pnl.append({"date": d, "pnl": round(running, 2)})
            equity_curve.append({"date": d, "equity": round(equity, 2)})
            capital_growth.append({"date": d, "value": round(equity, 2)})
            if prev_equity:
                daily_returns.append((equity - prev_equity) / prev_equity)
            prev_equity = equity

        max_drawdown_pct = round((max_drawdown / peak_equity) * 100, 2) if peak_equity else 0.0

        # Optional Sharpe (daily returns, risk-free ~0)
        sharpe_ratio = None
        if len(daily_returns) >= 2:
            mean_r = sum(daily_returns) / len(daily_returns)
            var = sum((r - mean_r) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            std = math.sqrt(var) if var > 0 else 0.0
            if std > 1e-12:
                sharpe_ratio = round((mean_r / std) * math.sqrt(252), 2)

        wins_count = len(wins)
        losses_count = len(losses)
        win_rate_pct = round((wins_count / total_trades * 100), 2) if total_trades else 0.0

        # Holding / symbol stats (timezone-safe)
        symbol_stats: dict[str, dict] = {}
        hold_mins_all: list[float] = []
        entry_prices: list[float] = []
        exit_prices: list[float] = []
        returns_pct: list[float] = []
        for t in trades:
            s = t.symbol
            if s not in symbol_stats:
                symbol_stats[s] = {"durations": [], "count": 0, "wins": 0, "pnl": 0.0}
            opened = self._aware_dt(t.opened_at)
            closed = self._aware_dt(t.closed_at)
            dur_min = 0.0
            if opened and closed:
                try:
                    dur_min = (closed - opened).total_seconds() / 60.0
                except Exception:
                    dur_min = 0.0
            symbol_stats[s]["durations"].append(dur_min)
            symbol_stats[s]["count"] += 1
            symbol_stats[s]["pnl"] += fnum(t.pnl)
            if fnum(t.pnl) > 0:
                symbol_stats[s]["wins"] += 1
            hold_mins_all.append(dur_min)
            entry_prices.append(fnum(t.entry_price))
            exit_prices.append(fnum(t.exit_price))
            returns_pct.append(fnum(t.pnl_percent))

        holding_periods = []
        for s, data in symbol_stats.items():
            avg_h = sum(data["durations"]) / len(data["durations"]) if data["durations"] else 0.0
            win_rate = (data["wins"] / data["count"] * 100) if data["count"] else 0.0
            holding_periods.append({
                "symbol": s,
                "avg_holding_minutes": round(avg_h, 2),
                "total_trades": data["count"],
                "win_rate_pct": round(win_rate, 2),
                "total_pnl": round(data["pnl"], 2),
            })
        holding_periods.sort(key=lambda r: r["total_pnl"], reverse=True)

        most_profitable_symbol = holding_periods[0]["symbol"] if holding_periods and holding_periods[0]["total_pnl"] > 0 else None
        most_losing_symbol = None
        if holding_periods:
            worst_sym = min(holding_periods, key=lambda r: r["total_pnl"])
            if worst_sym["total_pnl"] < 0:
                most_losing_symbol = worst_sym["symbol"]

        # Streaks
        chronological = sorted(
            trades,
            key=lambda t: self._aware_dt(t.closed_at) or datetime.min.replace(tzinfo=timezone.utc),
        )
        longest_win_streak = 0
        longest_loss_streak = 0
        cur_win = 0
        cur_loss = 0
        for trade in chronological:
            pnl = fnum(trade.pnl)
            if pnl > 0:
                cur_win += 1
                cur_loss = 0
            elif pnl < 0:
                cur_loss += 1
                cur_win = 0
            else:
                cur_win = 0
                cur_loss = 0
            longest_win_streak = max(longest_win_streak, cur_win)
            longest_loss_streak = max(longest_loss_streak, cur_loss)

        streak_type = "none"
        streak_count = 0
        for trade in reversed(chronological):
            pnl = fnum(trade.pnl)
            trade_type = "win" if pnl > 0 else "loss" if pnl < 0 else "flat"
            if streak_type == "none":
                streak_type = trade_type
                streak_count = 1
            elif trade_type == streak_type:
                streak_count += 1
            else:
                break

        # Order performance metrics (in range by created_at)
        def order_in_range(o: PaperOrder) -> bool:
            created = self._aware_dt(o.created_at)
            if created is None:
                return True if start_utc is None else False
            if start_utc and created < start_utc:
                return False
            if end_utc and created >= end_utc:
                return False
            return True

        orders_f = [o for o in orders if order_in_range(o)]
        total_orders = len(orders_f)
        executed_orders = len([
            o for o in orders_f if (o.status or "").upper() in {"FILLED", "EXECUTED"}
        ])
        cancelled_orders = len([o for o in orders_f if (o.status or "").upper() == "CANCELLED"])
        pending_orders = len([
            o for o in orders_f if (o.status or "").upper() in OPEN_ORDER_STATUSES
        ])
        buy_orders = len([o for o in orders_f if (o.side or "").upper() == "BUY"])
        sell_orders = len([o for o in orders_f if (o.side or "").upper() == "SELL"])
        intraday_trades = len([o for o in orders_f if (o.product_type or "").upper() == "MIS"])
        delivery_trades = len([o for o in orders_f if (o.product_type or "").upper() in ("CNC", "DELIVERY", "")])

        # Sector performance (lightweight map)
        _SECTOR = {
            "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking", "KOTAKBANK": "Banking",
            "AXISBANK": "Banking", "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT",
            "TECHM": "IT", "MARUTI": "Auto", "TATAMOTORS": "Auto", "M&M": "Auto",
            "RELIANCE": "Energy", "ONGC": "Energy", "NTPC": "Energy", "POWERGRID": "Energy",
            "BAJFINANCE": "Finance", "BAJAJFINSV": "Finance", "SUNPHARMA": "Pharma",
            "DRREDDY": "Pharma", "CIPLA": "Pharma", "HINDUNILVR": "FMCG", "ITC": "FMCG",
        }

        def sector_for(sym: str) -> str:
            s = (sym or "").upper().replace("NSE:", "").replace("-EQ", "").strip()
            return _SECTOR.get(s, "Others")

        sector_map: dict[str, float] = defaultdict(float)
        for t in trades:
            sector_map[sector_for(t.symbol)] += fnum(t.pnl)
        sector_performance = [
            {"sector": k, "pnl": round(v, 2)} for k, v in sorted(sector_map.items(), key=lambda x: -x[1])
        ]

        # Trade frequency (by date)
        freq_map: dict[str, int] = defaultdict(int)
        for t in trades:
            closed = self._aware_dt(t.closed_at)
            if closed:
                freq_map[closed.astimezone(IST).date().isoformat()] += 1
        trade_frequency = [{"date": d, "count": freq_map[d]} for d in sorted(freq_map.keys())]

        # Portfolio allocation (open positions)
        allocation = []
        for p in open_positions:
            val = fnum(p.avg_entry_price) * fnum(p.qty)
            allocation.append({
                "symbol": p.symbol,
                "value": round(val, 2),
                "pct": round((val / invested * 100), 2) if invested else 0.0,
            })
        if cash > 0:
            total_alloc = invested + cash
            allocation.append({
                "symbol": "CASH",
                "value": cash,
                "pct": round((cash / total_alloc * 100), 2) if total_alloc else 0.0,
            })

        avg_hold = round(sum(hold_mins_all) / len(hold_mins_all), 2) if hold_mins_all else 0.0
        avg_entry = round(sum(entry_prices) / len(entry_prices), 2) if entry_prices else None
        avg_exit = round(sum(exit_prices) / len(exit_prices), 2) if exit_prices else None
        avg_return_pct = round(sum(returns_pct) / len(returns_pct), 2) if returns_pct else 0.0

        result = {
            "period": period or "all",
            "range_label": range_label,
            # Overview cards
            "total_trades": total_trades,
            "winning_trades": wins_count,
            "losing_trades": losses_count,
            "wins": wins_count,
            "losses": losses_count,
            "win_rate_pct": win_rate_pct,
            "total_pnl": total_pnl,
            "todays_pnl": todays_pnl,
            "unrealized_pnl": unrealized,
            "realized_pnl": realized_period,
            "realized_pnl_all_time": realized_all,
            "portfolio_value": portfolio_value,
            "available_cash": cash,
            "capital_utilized": invested,
            "roi_pct": roi_pct,
            "average_profit": average_profit,
            "average_loss": average_loss,
            "profit_factor": profit_factor,
            "average_risk_reward": avg_rr,
            "largest_profit": round(fnum(best_trade.pnl), 2) if best_trade else None,
            "largest_loss": round(fnum(worst_trade.pnl), 2) if worst_trade else None,
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": max_drawdown_pct,
            "sharpe_ratio": sharpe_ratio,
            "open_positions_count": len(open_positions),
            # Trade analytics
            "average_holding_minutes": avg_hold,
            "average_holding_period": avg_hold,
            "average_entry_price": avg_entry,
            "average_exit_price": avg_exit,
            "best_trade_symbol": best_trade.symbol if best_trade else None,
            "best_trade_amount": round(fnum(best_trade.pnl), 2) if best_trade else None,
            "worst_trade_symbol": worst_trade.symbol if worst_trade else None,
            "worst_trade_amount": round(fnum(worst_trade.pnl), 2) if worst_trade else None,
            "most_profitable_symbol": most_profitable_symbol,
            "most_losing_symbol": most_losing_symbol,
            "longest_winning_streak": longest_win_streak,
            "longest_losing_streak": longest_loss_streak,
            "average_return_pct": avg_return_pct,
            "current_streak_type": streak_type,
            "current_streak_count": streak_count,
            # Performance / orders
            "total_orders": total_orders,
            "executed_orders": executed_orders,
            "cancelled_orders": cancelled_orders,
            "pending_orders": pending_orders,
            "buy_orders": buy_orders,
            "sell_orders": sell_orders,
            "intraday_trades": intraday_trades,
            "delivery_trades": delivery_trades,
            # Series for charts
            "daily_pnl": daily_pnl,
            "monthly_pnl": monthly_pnl,
            "cumulative_pnl": cumulative_pnl,
            "equity_curve": equity_curve,
            "capital_growth": capital_growth,
            "sector_performance": sector_performance,
            "trade_frequency": trade_frequency,
            "portfolio_allocation": allocation,
            "holding_periods": holding_periods,
            "starting_balance": starting,
        }
        return result

    def update_starting_capital(self, amount: float) -> PaperTradingDashboardResponse:
        account = self._get_or_create_account(for_update=True)
        try:
            delta = float(amount) - float(account.starting_balance)
        except Exception as e:
            print(f"ERROR parsing starting capital amount: {e}")
            raise ValueError("Invalid amount")
        account.starting_balance = float(amount)
        # Adjust cash balance by the delta so the user's relative balance is preserved
        account.cash_balance = float(account.cash_balance) + delta
        account.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.logger.info("Updated starting capital | account_id=%s | amount=%s", account.id, amount)
        return self.get_dashboard()

    def get_transactions(self, page: int = 1, per_page: int = 20) -> dict:
        """Fetch transactions from SQLite, newest first, paginated."""
        account = self._get_or_create_account()
        # Query all transactions for this account, ordered by timestamp DESC
        total = self.db.scalar(select(func.count(PaperTransaction.id)).where(PaperTransaction.account_id == account.id))
        skip = (page - 1) * per_page
        tx_models = list(self.db.scalars(
            select(PaperTransaction)
            .where(PaperTransaction.account_id == account.id)
            .order_by(PaperTransaction.timestamp.desc())
            .offset(skip)
            .limit(per_page)
        ))
        items = []
        for t in tx_models:
            items.append({
                "id": str(t.id),
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                "symbol": t.symbol,
                "action": t.action,
                "amount": float(t.amount) if t.amount is not None else 0.0,
                "balance_after": float(t.balance_after) if t.balance_after is not None else None,
                "qty": int(t.qty) if t.qty is not None else None,
                "price": float(t.price) if t.price is not None else None,
            })
        total_pages = (total + per_page - 1) // per_page if total else 0
        return {"items": items, "page": page, "per_page": per_page, "total": total or 0, "total_pages": total_pages}

    async def get_engine_status(self) -> dict:
        from app.services.market_engine_service import market_engine
        
        # Count open positions
        open_positions = self.db.scalar(
            select(func.count(PaperPosition.id))
            .where(PaperPosition.status == "OPEN")
        ) or 0
        
        # Max last_reconciled_at
        last_reconciliation_at = self.db.scalar(
            select(func.max(PaperPosition.last_reconciled_at))
        )
        
        engine_status = await market_engine.get_status()
        
        return {
            "status": engine_status.get("status", "STOPPED"),
            "last_tick_at": engine_status.get("last_tick_at"),
            "last_reconciliation_at": last_reconciliation_at,
            "open_positions": open_positions,
            "tracked_symbols": engine_status.get("active_monitored_symbols_count", 0),
        }
