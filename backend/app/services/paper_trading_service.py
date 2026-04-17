from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from ta.trend import EMAIndicator

from ..config import settings
from ..models.paper_trading import PaperOrder, PaperPosition, PaperTradeHistory, PaperTradingAccount
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


@dataclass(slots=True)
class PriceSnapshot:
    symbol: str
    current_price: float
    candles: list[OHLCVPoint]
    ema_20: float | None
    supertrend: float | None


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

        price_cache: dict[str, PriceSnapshot] = {}
        for position in positions:
            price_cache[position.symbol] = self._price_snapshot(position.symbol)
            position.current_price = price_cache[position.symbol].current_price
        self.db.commit()

        summary = self._build_account_summary(account, positions, orders, trades, price_cache)
        workspace_symbol = selected_symbol or (positions[0].symbol if positions else orders[0].symbol if orders else None)
        workspace = self._workspace_snapshot(workspace_symbol, price_cache) if workspace_symbol else None

        return PaperTradingDashboardResponse(
            account=summary,
            positions=[self._serialize_position(item) for item in positions],
            open_orders=[self._serialize_order(item) for item in orders if item.status == "PENDING"],
            order_history=[self._serialize_order(item) for item in orders],
            trades=[self._serialize_trade(item) for item in trades],
            symbols=settings.nifty500_symbols,
            selected_workspace=workspace,
        )

    def reset_account(self, payload: PaperTradingAccountResetRequest) -> PaperTradingDashboardResponse:
        account = self._get_or_create_account()
        account.starting_balance = payload.starting_balance
        account.cash_balance = payload.starting_balance
        account.updated_at = datetime.utcnow()
        self.db.execute(delete(PaperPosition).where(PaperPosition.account_id == account.id))
        self.db.execute(delete(PaperOrder).where(PaperOrder.account_id == account.id))
        self.db.execute(delete(PaperTradeHistory).where(PaperTradeHistory.account_id == account.id))
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
            qty=payload.qty,
            order_price=trigger_price,
            stop_loss=payload.stop_loss,
            target=payload.target,
            notes=payload.notes,
            source_signal=payload.source_signal,
            source_score=payload.source_score,
            source_confidence=payload.source_confidence,
            status="PENDING",
        )
        self.db.add(order)
        self.db.flush()

        filled_order, position, trade, message = self._try_fill_order(account, order, price.current_price)
        self.db.commit()
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
        order.cancelled_at = datetime.utcnow()
        self.db.commit()
        return PaperOrderActionResponse(
            account=self.get_dashboard(selected_symbol=order.symbol).account,
            order=self._serialize_order(order),
            message="Order cancelled.",
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
            ltp = self.fyers_service.fetch_ohlcv(normalized_symbol, AnalysisMode.swing, "1d", 2)[-1].close
            source = "CANDLE_FALLBACK"
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
            starting_balance=100000.0,
            cash_balance=100000.0,
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
        return list(self.db.scalars(select(PaperPosition).where(PaperPosition.account_id == account_id).order_by(PaperPosition.created_at.desc())))

    def _order_models(self, account_id: int) -> list[PaperOrder]:
        return list(self.db.scalars(select(PaperOrder).where(PaperOrder.account_id == account_id).order_by(PaperOrder.created_at.desc())))

    def _trade_models(self, account_id: int) -> list[PaperTradeHistory]:
        return list(self.db.scalars(select(PaperTradeHistory).where(PaperTradeHistory.account_id == account_id).order_by(PaperTradeHistory.closed_at.desc())))

    def _requested_price(self, payload: PaperOrderCreateRequest, current_price: float) -> float | None:
        if payload.type == "LIMIT":
            if payload.limit_price is None:
                raise ValueError("Limit orders require limit_price.")
            return payload.limit_price
        if payload.type == "STOP":
            if payload.stop_price is None:
                raise ValueError("Stop orders require stop_price.")
            return payload.stop_price
        return current_price

    def _try_fill_order(
        self,
        account: PaperTradingAccount,
        order: PaperOrder,
        current_price: float,
    ) -> tuple[PaperOrder, PaperPosition | None, PaperTradeHistory | None, str]:
        should_fill = False
        if order.order_type == "MARKET":
            should_fill = True
        elif order.order_type == "LIMIT":
            should_fill = (order.side == "BUY" and current_price <= (order.order_price or current_price)) or (
                order.side == "SELL" and current_price >= (order.order_price or current_price)
            )
        elif order.order_type == "STOP":
            should_fill = (order.side == "BUY" and current_price >= (order.order_price or current_price)) or (
                order.side == "SELL" and current_price <= (order.order_price or current_price)
            )

        if not should_fill:
            order.status = "PENDING"
            return order, None, None, "Order placed and kept pending."

        fill_price = current_price
        if order.side == "BUY":
            estimated_cost = fill_price * order.qty
            available_cash = self._build_account_summary(account, self._position_models(account.id), self._order_models(account.id), self._trade_models(account.id), {}).available_cash
            if estimated_cost > available_cash:
                order.status = "REJECTED"
                return order, None, None, "Order rejected: insufficient available cash."
            order.status = "FILLED"
            order.filled_at = datetime.utcnow()
            order.filled_price = fill_price
            account.cash_balance -= estimated_cost
            position = self.db.scalar(select(PaperPosition).where(PaperPosition.account_id == account.id, PaperPosition.symbol == order.symbol))
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
            account.updated_at = datetime.utcnow()
            return order, position, None, "Buy order filled."

        position = self.db.scalar(select(PaperPosition).where(PaperPosition.account_id == account.id, PaperPosition.symbol == order.symbol))
        if not position or position.qty < order.qty:
            order.status = "REJECTED"
            return order, None, None, "Order rejected: not enough position quantity to sell."

        order.status = "FILLED"
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
        )
        self.db.add(trade)
        if position.qty == order.qty:
            self.db.delete(position)
            updated_position = None
        else:
            position.qty -= order.qty
            position.current_price = fill_price
            position.updated_at = datetime.utcnow()
            updated_position = position
        account.updated_at = datetime.utcnow()
        return order, updated_position, trade, "Sell order filled."

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
            self._try_fill_order(account, order, price.current_price)
        self.db.commit()

    def _price_snapshot(self, symbol: str) -> PriceSnapshot:
        candles = self.fyers_service.fetch_ohlcv(symbol, AnalysisMode.swing, "1d", 90)
        current_price = self.fyers_service.fetch_ltp(symbol) or candles[-1].close
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

    def _serialize_position(self, position: PaperPosition) -> PaperPositionResponse:
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
            risk_reward_ratio=risk_reward,
            source_signal=position.source_signal,
            source_score=position.source_score,
            source_confidence=position.source_confidence,
            created_at=position.created_at,
            updated_at=position.updated_at,
        )

    def _serialize_order(self, order: PaperOrder) -> PaperOrderResponse:
        return PaperOrderResponse(
            id=order.id,
            symbol=order.symbol,
            side=order.side,  # type: ignore[arg-type]
            type=order.order_type,  # type: ignore[arg-type]
            qty=order.qty,
            price=round(order.order_price, 2) if order.order_price is not None else None,
            stop_loss=round(order.stop_loss, 2) if order.stop_loss is not None else None,
            target=round(order.target, 2) if order.target is not None else None,
            status=order.status,  # type: ignore[arg-type]
            notes=order.notes,
            source_signal=order.source_signal,
            source_score=order.source_score,
            source_confidence=order.source_confidence,
            created_at=order.created_at,
            filled_at=order.filled_at,
            filled_price=round(order.filled_price, 2) if order.filled_price is not None else None,
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
        )
