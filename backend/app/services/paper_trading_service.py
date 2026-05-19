from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

import pandas as pd
from sqlalchemy import delete, select, func
from sqlalchemy.orm import Session
from ta.trend import EMAIndicator

from ..config import settings
from ..models.paper_trading import PaperOrder, PaperPosition, PaperTradeHistory, PaperTradingAccount, PaperNotification, PaperTransaction, PaperAlert
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
from ..utils import advisory_payload, get_logger
from ..core.log_manager import trading_logger



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
    def __init__(self, db: Session) -> None:
        self.db = db
        self.logger = get_logger("app.paper_trading")
        self.fyers_service = FyersService()

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
            if snapshot:
                position.current_price = snapshot.current_price
        self.db.commit()

        summary = self._build_account_summary(account, positions, orders, trades, price_cache)
        workspace_symbol = selected_symbol or (positions[0].symbol if positions else orders[0].symbol if orders else None)
        workspace = self._workspace_snapshot(workspace_symbol, price_cache) if workspace_symbol else None

        return PaperTradingDashboardResponse(
            account=summary,
            positions=[self._serialize_position(item, price_cache.get(item.symbol)) for item in positions],
            open_orders=[self._serialize_order(item, price_cache.get(item.symbol)) for item in orders if item.status == "PENDING"],
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
            if snapshot:
                position.current_price = snapshot.current_price
        self.db.commit()
        # Re-fetch positions after commit to avoid stale object errors
        positions = self._position_models(account.id)
        return [self._serialize_position(item, price_cache.get(item.symbol)) for item in positions]

    def get_pending_orders(self) -> list[PaperOrderResponse]:
        account = self._get_or_create_account()
        self._refresh_pending_orders(account.id)
        orders = [item for item in self._order_models(account.id) if item.status == "PENDING"]
        price_cache = self._load_price_cache({item.symbol for item in orders})
        self.db.commit()
        # Re-fetch orders after commit to avoid stale object errors
        orders = [item for item in self._order_models(account.id) if item.status == "PENDING"]
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
        account.updated_at = datetime.utcnow()
        self.db.execute(delete(PaperPosition).where(PaperPosition.account_id == account.id))
        self.db.execute(delete(PaperOrder).where(PaperOrder.account_id == account.id))
        self.db.execute(delete(PaperTradeHistory).where(PaperTradeHistory.account_id == account.id))
        self.db.execute(delete(PaperTransaction).where(PaperTransaction.account_id == account.id))
        self.db.commit()
        self.logger.info("Paper account reset | account_id=%s | starting_balance=%s", account.id, payload.starting_balance)
        return self.get_dashboard()

    def place_order(self, payload: PaperOrderCreateRequest) -> PaperOrderActionResponse:
        account = self._get_or_create_account()
        self._validate_symbol(payload.symbol)
        self._refresh_pending_orders(account.id)
        price = self._price_snapshot(payload.symbol)
        trigger_price = self._requested_price(payload, price.current_price)
        order = PaperOrder(
            account_id=account.id,
            symbol=payload.symbol,
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
        )
        self.db.add(order)
        self.db.flush()
        try:
            trading_logger.info(
                "ORDER_PLACED | account=%s | order_id=%s | symbol=%s | side=%s | qty=%s | order_type=%s | order_price=%s | stop_loss=%s | target=%s | source_signal=%s | source_score=%s | source_confidence=%s",
                account.id,
                getattr(order, "id", None),
                order.symbol,
                order.side,
                order.qty,
                order.order_type,
                order.order_price,
                order.stop_loss,
                order.target,
                order.source_signal,
                order.source_score,
                order.source_confidence,
            )
        except Exception:
            pass
        order.last_evaluated_at = datetime.utcnow()
        order.last_seen_ltp = price.current_price
        # Try to fill the order (this will update order.status, create/update position, and adjust account in the same session)
        filled_order, position, trade, message = self._try_fill_order(account, order, price.current_price)

        # Commit the order + position + account changes as one atomic unit
        try:
            self.db.commit()
        except Exception as e:
            # Rollback to ensure the session is not left in a broken state
            try:
                self.db.rollback()
            except Exception:
                pass
            self.logger.exception("Failed to commit order fill for symbol=%s account=%s", payload.symbol, account.id)
            raise

        # If BUY was filled, log transaction (cash outflow) to SQLite after commit
        try:
            if filled_order.status == "FILLED" and filled_order.side == "BUY":
                filled_order.lifecycle_state = "ENTRY_FILLED"
                if position:
                    position.lifecycle_state = "OPEN_POSITION"
                tx = PaperTransaction(
                    account_id=int(account.id),
                    timestamp=datetime.utcnow(),
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
                    f"{filled_order.symbol} paper buy filled at Rs {round(float(filled_order.filled_price or 0.0), 2)}.",
                    "success",
                    "ENTRY_FILLED",
                    "order",
                    filled_order.id,
                    dedupe_key=f"entry-filled:{filled_order.id}",
                )
                self.db.commit()
            elif filled_order.status == "PENDING" and filled_order.side == "BUY":
                self.add_notification(
                    account.id,
                    f"{filled_order.symbol} limit buy waiting for entry at Rs {round(float(filled_order.order_price or 0.0), 2)}.",
                    "info",
                    "PENDING_ENTRY_CREATED",
                    "order",
                    filled_order.id,
                    dedupe_key=f"pending-entry:{filled_order.id}",
                )
        except Exception as e:
            print(f"ERROR in place_order: {e}")
            self.logger.exception("Failed to write BUY transaction to SQLite")
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
        if order.status != "PENDING":
            raise ValueError("Only pending orders can be cancelled.")
        order.status = "CANCELLED"
        order.lifecycle_state = "CANCELLED"
        order.cancelled_at = datetime.utcnow()
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
        if order.status != "PENDING":
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
        position.updated_at = datetime.utcnow()
        self.db.commit()
        return PaperOrderActionResponse(
            account=self.get_dashboard(selected_symbol=position.symbol).account,
            position=self._serialize_position(position),
            message="Position updated.",
        )

    def recommendation_prefill(self, payload: RecommendationPrefillRequest) -> RecommendationPrefillResponse:
        targets = payload.suggested_targets or []
        return RecommendationPrefillResponse(
            symbol=payload.symbol.strip().upper(),
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
        self._validate_symbol(symbol)
        snapshot = self._price_snapshot(symbol)
        return self._workspace_from_snapshot(snapshot, None, None, None)

    def get_quote(self, symbol: str) -> PaperQuoteResponse:
        normalized_symbol = symbol.strip().upper()
        self._validate_symbol(normalized_symbol)
        ltp = self.fyers_service.fetch_ltp(normalized_symbol)
        source = "FYERS_QUOTE"
        if ltp is None:
            candles = self.fyers_service.fetch_ohlcv(normalized_symbol, AnalysisMode.swing, "1d", 2)
            if candles:
                ltp = candles[-1].close
                source = "CANDLE_FALLBACK"
            else:
                ltp = 0.0
                source = "NO_DATA"
        return PaperQuoteResponse(
            symbol=normalized_symbol,
            current_price=round(ltp, 2),
            source=source,  # type: ignore[arg-type]
            updated_at=datetime.now(timezone.utc),
        )

    def _get_or_create_account(self) -> PaperTradingAccount:
        account = self.db.scalar(select(PaperTradingAccount).order_by(PaperTradingAccount.id.asc()))
        if account:
            return account
        account = PaperTradingAccount(
            name="Primary Paper Account",
            starting_balance=1000000.0,
            cash_balance=1000000.0,
            max_risk_per_trade=0.02,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def _validate_symbol(self, symbol: str) -> None:
        if symbol.strip().upper() not in settings.nifty500_symbols:
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
    ) -> tuple[PaperOrder, PaperPosition | None, PaperTradeHistory | None, str]:
        if current_price <= 0:
            order.status = "PENDING"
            if order.lifecycle_state not in {"TOKEN_EXPIRED_PAUSED", "MARKET_CLOSED_WAITING", "ERROR_RETRYING"}:
                order.lifecycle_state = "PENDING_ENTRY"
            return order, None, None, "Live market price unavailable; order remains pending."

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
            if order.lifecycle_state not in {"TOKEN_EXPIRED_PAUSED", "MARKET_CLOSED_WAITING", "ERROR_RETRYING"}:
                order.lifecycle_state = "PENDING_ENTRY"
            return order, None, None, "Order placed and kept pending."

        fill_price = current_price
        if order.side == "BUY":
            estimated_cost = fill_price * order.qty
            # compute available cash using current open positions/orders
            available_cash = self._build_account_summary(
                account, self._position_models(account.id), self._order_models(account.id), self._trade_models(account.id), {}
            ).available_cash
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
            order.filled_at = datetime.utcnow()
            order.filled_price = fill_price
            # Deduct funds and create/update OPEN position
            account.cash_balance -= estimated_cost
            position = self.db.scalar(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.symbol == order.symbol,
                    PaperPosition.status == "OPEN",
                )
            )
            if position:
                total_cost = (position.avg_entry_price * position.qty) + estimated_cost
                position.qty += order.qty
                position.avg_entry_price = total_cost / position.qty
                position.current_price = fill_price
                position.stop_loss = order.stop_loss
                position.target = order.target
                position.updated_at = datetime.utcnow()
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
            account.updated_at = datetime.utcnow()
            try:
                trading_logger.info(
                    "ORDER_FILLED | order_id=%s | account=%s | symbol=%s | side=BUY | qty=%s | filled_price=%s | position_id=%s",
                    getattr(order, "id", None),
                    account.id,
                    order.symbol,
                    order.qty,
                    order.filled_price,
                    getattr(position, "id", None),
                )
            except Exception:
                pass
            return order, position, None, "Buy order filled."

        position = self.db.scalar(select(PaperPosition).where(PaperPosition.account_id == account.id, PaperPosition.symbol == order.symbol))
        if not position or position.qty < order.qty:
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
        order.filled_at = datetime.utcnow()
        order.filled_price = fill_price
        account.cash_balance += fill_price * order.qty
        pnl = (fill_price - position.avg_entry_price) * order.qty
        pnl_percent = ((fill_price - position.avg_entry_price) / position.avg_entry_price) * 100 if position.avg_entry_price else 0.0
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
            closed_at=datetime.utcnow(),
            exit_reason="MANUAL",
        )
        self.db.add(trade)
        # Log transaction for manual SELL to SQLite (if configured)
        try:
            tx = PaperTransaction(
                account_id=int(account.id),
                timestamp=datetime.utcnow(),
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
        if position.qty == order.qty:
            self.db.delete(position)
            updated_position = None
        else:
            position.qty -= order.qty
            position.current_price = fill_price
            position.updated_at = datetime.utcnow()
            updated_position = position
        try:
            trading_logger.info(
                "ORDER_FILLED | order_id=%s | account=%s | symbol=%s | side=SELL | qty=%s | filled_price=%s | pnl=%s | pnl_percent=%.2f",
                getattr(order, "id", None),
                account.id,
                position.symbol,
                order.qty,
                fill_price,
                round(pnl, 2),
                round(pnl_percent, 2),
            )
        except Exception:
            pass
        account.updated_at = datetime.utcnow()
        return order, updated_position, trade, "Sell order filled."

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
        items = list(self.db.scalars(select(PaperNotification).where(PaperNotification.account_id == account.id, PaperNotification.is_read == False).order_by(PaperNotification.created_at.desc())))
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
            q = q.where(PaperNotification.is_read == False)
        q = q.order_by(PaperNotification.created_at.desc()).limit(limit)
        items = list(self.db.scalars(q))
        return items

    def mark_all_notifications_read(self) -> int:
        account = self._get_or_create_account()
        rows = list(self.db.scalars(select(PaperNotification).where(PaperNotification.account_id == account.id, PaperNotification.is_read == False)))
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
        account = self._get_or_create_account()
        items = list(self.db.scalars(select(PaperAlert).where(PaperAlert.account_id == account.id, PaperAlert.status == "ACTIVE")))
        return items

    def trigger_alert(self, alert_id: int, triggered_price: float) -> None:
        account = self._get_or_create_account()
        alert = self.db.scalar(select(PaperAlert).where(PaperAlert.id == alert_id, PaperAlert.account_id == account.id))
        if not alert:
            return
        alert.status = "TRIGGERED"
        alert.triggered_at = datetime.utcnow()
        alert.triggered_price = float(triggered_price)
        self.db.commit()
        try:
            msg = f"Price alert: {alert.symbol} {alert.condition} ₹{round(triggered_price,2)}"
            self.add_notification(account.id, msg, level="success")
        except Exception as e:
            print(f"ERROR adding notification for triggered alert: {e}")
            self.logger.exception("Failed to add notification for triggered alert")

    def auto_exit(self, position_id: int, fill_price: float, reason: str = "MANUAL") -> PaperOrderActionResponse:
        account = self._get_or_create_account()
        position = self.db.scalar(select(PaperPosition).where(PaperPosition.id == position_id, PaperPosition.account_id == account.id))
        if not position:
            raise ValueError("Position not found.")

        # Create a filled sell order representing the exit
        order = PaperOrder(
            account_id=account.id,
            symbol=position.symbol,
            side="SELL",
            order_type="MARKET",
            product_type="CNC",
            qty=position.qty,
            order_price=fill_price,
            stop_price=None,
            stop_loss=None,
            target=None,
            status="FILLED",
            lifecycle_state="EXIT_FILLED",
            notes=f"Auto exit: {reason}",
            filled_price=fill_price,
            filled_at=datetime.utcnow(),
        )
        self.db.add(order)
        self.db.flush()

        pnl = (fill_price - position.avg_entry_price) * position.qty
        pnl_percent = ((fill_price - position.avg_entry_price) / position.avg_entry_price) * 100 if position.avg_entry_price else 0.0
        trade = PaperTradeHistory(
            account_id=account.id,
            symbol=position.symbol,
            qty=position.qty,
            entry_price=position.avg_entry_price,
            exit_price=fill_price,
            pnl=pnl,
            pnl_percent=pnl_percent,
            notes=position.notes,
            source_signal=position.source_signal,
            source_score=position.source_score,
            source_confidence=position.source_confidence,
            opened_at=position.created_at,
            closed_at=datetime.utcnow(),
            exit_reason=reason,
        )
        self.db.add(trade)

        # Credit account and remove position
        account.cash_balance += fill_price * position.qty
        account.updated_at = datetime.utcnow()
        self.db.delete(position)
        self.db.commit()

        # Create a notification
        try:
            if reason == "TARGET_HIT":
                msg = f"{position.symbol} sold at ₹{round(fill_price,2)} — Target Hit ✅"
                level = "success"
            elif reason == "STOPLOSS_HIT":
                msg = f"{position.symbol} sold at ₹{round(fill_price,2)} — Stop Loss Hit 🔴"
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
                timestamp=datetime.utcnow(),
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
        pending_orders = list(
            self.db.scalars(
                select(PaperOrder).where(PaperOrder.account_id == account_id, PaperOrder.status == "PENDING")
            )
        )
        if not pending_orders:
            return
        account = self._get_or_create_account()
        for order in pending_orders:
            price = self._price_snapshot(order.symbol)
            order.last_evaluated_at = datetime.utcnow()
            order.last_seen_ltp = price.current_price
            self._try_fill_order(account, order, price.current_price)
        self.db.commit()

    def _load_price_cache(self, symbols: set[str]) -> dict[str, PriceSnapshot]:
        cache: dict[str, PriceSnapshot] = {}
        for symbol in sorted(symbols):
            normalized = symbol.strip().upper()
            if not normalized:
                continue
            try:
                cache[normalized] = self._price_snapshot(normalized)
            except Exception as exc:
                self.logger.exception("Failed to load price snapshot for symbol=%s", normalized)
        return cache

    def _price_snapshot(self, symbol: str) -> PriceSnapshot:
        candles = self.fyers_service.fetch_ohlcv(symbol, AnalysisMode.swing, "1d", 90)
        if not candles:
            self.logger.warning("No OHLCV candles available for price snapshot | symbol=%s", symbol)

        low_level_price = None
        if candles:
            low_level_price = candles[-1].close

        ltp = self.fyers_service.fetch_ltp(symbol)
        source = "FYERS_QUOTE"
        current_price = ltp
        if current_price is None:
            if candles:
                current_price = low_level_price
                source = "CANDLE_FALLBACK"
            else:
                current_price = 0.0
                source = "NO_DATA"
        if current_price is None:
            self.logger.warning("No current price available for symbol %s; using 0.0 default", symbol)
            current_price = 0.0

        frame = pd.DataFrame(
            {
                "high": [item.high for item in candles],
                "low": [item.low for item in candles],
                "close": [item.close for item in candles],
            }
        )
        ema_20 = float(EMAIndicator(close=frame["close"], window=20).ema_indicator().iloc[-1]) if len(frame) >= 20 else None
        supertrend = self._approx_supertrend(frame)
        return PriceSnapshot(
            symbol=symbol,
            current_price=current_price,
            candles=candles[-60:],
            ema_20=ema_20,
            supertrend=supertrend,
            source=source,
            fetched_at=datetime.now(timezone.utc),
        )

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
        realized = round(sum(item.pnl for item in trades), 2)
        invested = 0.0
        unrealized = 0.0
        for position in positions:
            current_price = price_cache.get(position.symbol).current_price if position.symbol in price_cache else position.current_price
            invested += position.avg_entry_price * position.qty
            unrealized += (current_price - position.avg_entry_price) * position.qty
        reserved_cash = 0.0
        for order in orders:
            if order.status == "PENDING" and order.side == "BUY":
                order_price = order.order_price or price_cache.get(order.symbol, self._price_snapshot(order.symbol)).current_price
                reserved_cash += order_price * order.qty
        equity = round(account.cash_balance + sum((price_cache.get(item.symbol).current_price if item.symbol in price_cache else item.current_price) * item.qty for item in positions), 2)
        return PaperAccountSummary(
            account_id=account.id,
            account_name=account.name,
            base_currency=account.base_currency,
            starting_balance=round(account.starting_balance, 2),
            balance=round(account.cash_balance, 2),
            equity=equity,
            realized_pnl=realized,
            unrealized_pnl=round(unrealized, 2),
            total_invested=round(invested, 2),
            reserved_cash=round(reserved_cash, 2),
            available_cash=round(account.cash_balance - reserved_cash, 2),
            open_positions_count=len(positions),
            open_orders_count=len([item for item in orders if item.status == "PENDING"]),
            max_risk_per_trade=account.max_risk_per_trade,
            updated_at=datetime.now(timezone.utc),
        )

    def _serialize_position(self, position: PaperPosition, snapshot: PriceSnapshot | None = None) -> PaperPositionResponse:
        unrealized = (position.current_price - position.avg_entry_price) * position.qty
        unrealized_pct = ((position.current_price - position.avg_entry_price) / position.avg_entry_price) * 100 if position.avg_entry_price else 0.0
        risk_reward = None
        if position.stop_loss and position.target:
            risk = abs(position.avg_entry_price - position.stop_loss)
            reward = abs(position.target - position.avg_entry_price)
            risk_reward = round(reward / risk, 2) if risk else None
        return PaperPositionResponse(
            id=position.id,
            symbol=position.symbol,
            qty=position.qty,
            avg_entry_price=round(position.avg_entry_price, 2),
            current_price=round(position.current_price, 2),
            unrealized_pnl=round(unrealized, 2),
            unrealized_pnl_percent=round(unrealized_pct, 2),
            invested_value=round(position.avg_entry_price * position.qty, 2),
            stop_loss=round(position.stop_loss, 2) if position.stop_loss else None,
            target=round(position.target, 2) if position.target else None,
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
        return PaperOrderResponse(
            id=order.id,
            symbol=order.symbol,
            side=order.side,  # type: ignore[arg-type]
            type=order.order_type,  # type: ignore[arg-type]
            qty=order.qty,
            price=round(order.order_price, 2) if order.order_price is not None else None,
            stop_price=round(order.stop_price, 2) if getattr(order, "stop_price", None) is not None else None,
            stop_loss=round(order.stop_loss, 2) if order.stop_loss is not None else None,
            target=round(order.target, 2) if order.target is not None else None,
            status=order.status,  # type: ignore[arg-type]
            lifecycle_state=order.lifecycle_state,  # type: ignore[arg-type]
            requested_entry_price=round(order.requested_entry_price, 2) if order.requested_entry_price is not None else None,
            monitor_enabled=bool(order.monitor_enabled),
            paused_reason=order.paused_reason,
            notes=order.notes,
            source_signal=order.source_signal,
            source_score=order.source_score,
            source_confidence=order.source_confidence,
            last_evaluated_at=order.last_evaluated_at,
            last_seen_ltp=round(order.last_seen_ltp, 2) if order.last_seen_ltp is not None else None,
            price_source=snapshot.source if snapshot else None,
            price_fetched_at=snapshot.fetched_at if snapshot else None,
            is_price_stale=(snapshot.source != "FYERS_QUOTE") if snapshot else False,
            created_at=order.created_at,
            filled_at=order.filled_at,
            filled_price=round(order.filled_price, 2) if order.filled_price is not None else None,
            product_type=getattr(order, "product_type", None),
        )

    def _serialize_trade(self, trade: PaperTradeHistory) -> PaperTradeHistoryItem:
        holding_period = (trade.closed_at - trade.opened_at).total_seconds() / 3600
        return PaperTradeHistoryItem(
            id=trade.id,
            symbol=trade.symbol,
            qty=trade.qty,
            entry_price=round(trade.entry_price, 2),
            exit_price=round(trade.exit_price, 2),
            pnl=round(trade.pnl, 2),
            pnl_percent=round(trade.pnl_percent, 2),
            notes=trade.notes,
            source_signal=trade.source_signal,
            source_score=trade.source_score,
            source_confidence=trade.source_confidence,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            exit_reason=getattr(trade, "exit_reason", None),
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

    def get_analytics(self) -> dict:
        account = self._get_or_create_account()
        trades = self._trade_models(account.id)

        total_trades = len(trades)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        sum_wins = round(sum(t.pnl for t in wins), 2) if wins else 0.0
        sum_losses = round(sum(t.pnl for t in losses), 2) if losses else 0.0

        profit_factor = None
        if abs(sum_losses) > 1e-9:
            profit_factor = round((sum_wins / abs(sum_losses)) if sum_losses != 0 else None, 2)

        average_profit = round((sum_wins / len(wins)), 2) if wins else None
        average_loss = round((sum_losses / len(losses)), 2) if losses else None

        best_trade = max(trades, key=lambda t: t.pnl) if trades else None
        worst_trade = min(trades, key=lambda t: t.pnl) if trades else None

        # daily pnl aggregation by closed date (ISO date)
        daily_map: dict[str, float] = {}
        for t in trades:
            try:
                key = t.closed_at.date().isoformat()
            except Exception as e:
                print(f"ERROR parsing closed_at for trade id {getattr(t,'id',None)}: {e}")
                key = str(t.closed_at)[:10]
            daily_map[key] = daily_map.get(key, 0.0) + float(t.pnl)

        sorted_dates = sorted(daily_map.keys())
        daily_pnl = [
            {"date": d, "pnl": round(daily_map[d], 2)} for d in sorted_dates
        ]
        cumulative_pnl = []
        running = 0.0
        peak_equity = float(account.starting_balance)
        max_drawdown = 0.0
        for d in sorted_dates:
            running += daily_map[d]
            equity = float(account.starting_balance) + running
            peak_equity = max(peak_equity, equity)
            max_drawdown = max(max_drawdown, peak_equity - equity)
            cumulative_pnl.append({"date": d, "pnl": round(running, 2)})

        wins_count = len(wins)
        losses_count = len(losses)

        # holding periods per symbol
        symbol_stats: dict[str, dict] = {}
        for t in trades:
            s = t.symbol
            if s not in symbol_stats:
                symbol_stats[s] = {"durations": [], "count": 0, "wins": 0}
            dur_min = (t.closed_at - t.opened_at).total_seconds() / 60
            symbol_stats[s]["durations"].append(dur_min)
            symbol_stats[s]["count"] += 1
            if t.pnl > 0:
                symbol_stats[s]["wins"] += 1

        holding_periods = []
        for s, data in symbol_stats.items():
            avg_h = sum(data["durations"]) / len(data["durations"]) if data["durations"] else 0.0
            win_rate = (data["wins"] / data["count"] * 100) if data["count"] else 0.0
            holding_periods.append({
                "symbol": s,
                "avg_holding_minutes": round(avg_h, 2),
                "total_trades": data["count"],
                "win_rate_pct": round(win_rate, 2),
            })

        win_rate_pct = round((wins_count / total_trades * 100), 2) if total_trades else 0.0
        streak_type = "none"
        streak_count = 0
        for trade in sorted(trades, key=lambda t: t.closed_at, reverse=True):
            trade_type = "win" if trade.pnl > 0 else "loss" if trade.pnl < 0 else "flat"
            if streak_type == "none":
                streak_type = trade_type
                streak_count = 1
            elif trade_type == streak_type:
                streak_count += 1
            else:
                break

        result = {
            "total_trades": total_trades,
            "win_rate_pct": win_rate_pct,
            "profit_factor": profit_factor,
            "average_profit": average_profit,
            "average_loss": average_loss,
            "best_trade_symbol": best_trade.symbol if best_trade else None,
            "best_trade_amount": round(best_trade.pnl, 2) if best_trade else None,
            "worst_trade_symbol": worst_trade.symbol if worst_trade else None,
            "worst_trade_amount": round(worst_trade.pnl, 2) if worst_trade else None,
            "daily_pnl": daily_pnl,
            "cumulative_pnl": cumulative_pnl,
            "wins": wins_count,
            "losses": losses_count,
            "holding_periods": holding_periods,
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": round((max_drawdown / peak_equity) * 100, 2) if peak_equity else 0.0,
            "current_streak_type": streak_type,
            "current_streak_count": streak_count,
        }

        return result

    def update_starting_capital(self, amount: float) -> PaperTradingDashboardResponse:
        account = self._get_or_create_account()
        try:
            delta = float(amount) - float(account.starting_balance)
        except Exception as e:
            print(f"ERROR parsing starting capital amount: {e}")
            raise ValueError("Invalid amount")
        account.starting_balance = float(amount)
        # Adjust cash balance by the delta so the user's relative balance is preserved
        account.cash_balance = float(account.cash_balance) + delta
        account.updated_at = datetime.utcnow()
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
