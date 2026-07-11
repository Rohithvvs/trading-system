"""Professional order ticket preview — charges, margin, risk, expected PnL."""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from ..models.paper_trading import PaperTradingAccount
from ..schemas.retail import (
    OrderChargeBreakdown,
    OrderPreviewRequest,
    OrderPreviewResponse,
)
from .market_quotes_service import MarketQuotesService
from .risk_enforcement_service import RiskEnforcementService, FREEZE_QTY_DEFAULT


class OrderTicketService:
    def __init__(self, db: Session, user_id: uuid.UUID, account: PaperTradingAccount) -> None:
        self.db = db
        self.user_id = user_id
        self.account = account
        self.quotes = MarketQuotesService(db)
        self.risk = RiskEnforcementService(db, user_id)

    def preview(self, payload: OrderPreviewRequest) -> OrderPreviewResponse:
        qmap = self.quotes.get_quotes_batch([payload.symbol])
        quote = qmap.get(payload.symbol, {})
        ltp = quote.get("ltp") or 0.0
        est_price = payload.limit_price or payload.stop_price or ltp or 0.0
        if payload.type in ("MARKET", "SL-M") and ltp:
            est_price = float(ltp)

        qty = payload.qty
        order_value = float(Decimal(str(qty)) * Decimal(str(est_price)))
        charges = self._charges(order_value, payload.side, payload.product_type)
        taxes_total = charges.stt + charges.exchange_txn + charges.sebi_fees + charges.gst + charges.stamp_duty

        # Margin: CNC full, MIS leveraged
        limits = self.risk.get_or_create_limits()
        if payload.product_type == "MIS":
            margin_required = order_value / max(float(limits.max_leverage), 1.0)
        elif payload.product_type == "NRML":
            margin_required = order_value * 0.2  # approx SPAN-like
        else:
            margin_required = order_value

        funds_required = margin_required + charges.total_charges if payload.side == "BUY" else charges.total_charges
        available = float(self.account.cash_balance)

        expected_pnl = None
        risk_reward = None
        if payload.stop_loss and payload.target and est_price:
            if payload.side == "BUY":
                risk = (est_price - payload.stop_loss) * qty
                reward = (payload.target - est_price) * qty
            else:
                risk = (payload.stop_loss - est_price) * qty
                reward = (est_price - payload.target) * qty
            expected_pnl = round(reward, 2)
            if risk > 0:
                risk_reward = round(reward / risk, 2)

        risk_result = self.risk.validate_order(
            account=self.account,
            symbol=payload.symbol,
            side=payload.side,
            qty=qty,
            price=est_price,
            product_type=payload.product_type,
            order_type=payload.type,
            stop_loss=payload.stop_loss,
            quote=quote,
        )

        circuit_status = None
        if quote.get("upper_circuit") or quote.get("lower_circuit"):
            circuit_status = f"UC:{quote.get('upper_circuit')} LC:{quote.get('lower_circuit')}"

        return OrderPreviewResponse(
            symbol=payload.symbol,
            side=payload.side,
            type=payload.type,
            product_type=payload.product_type,
            validity=payload.validity,
            qty=qty,
            estimated_price=round(est_price, 2),
            order_value=round(order_value, 2),
            charges=charges,
            taxes_total=round(taxes_total, 2),
            margin_required=round(margin_required, 2),
            funds_required=round(funds_required, 2),
            available_funds=round(available, 2),
            expected_pnl=expected_pnl,
            risk_reward=risk_reward,
            risk_checks=risk_result.checks,
            can_place=risk_result.allowed and (payload.side != "BUY" or funds_required <= available),
            reject_reasons=risk_result.reasons
            + (
                [f"Insufficient funds: need ₹{funds_required:,.2f}, have ₹{available:,.2f}"]
                if payload.side == "BUY" and funds_required > available and risk_result.allowed
                else []
            ),
            circuit_status=circuit_status,
            freeze_qty=FREEZE_QTY_DEFAULT,
        )

    def _charges(self, order_value: float, side: str, product: str) -> OrderChargeBreakdown:
        """Approx Indian equity charge model (educational; not broker-exact)."""
        brokerage = min(20.0, order_value * 0.0003)  # 0.03% or ₹20
        if product == "MIS":
            brokerage = min(20.0, order_value * 0.0003)

        stt = order_value * 0.001 if side == "SELL" and product == "CNC" else order_value * 0.00025 if side == "SELL" else 0.0
        if side == "BUY" and product == "CNC":
            stt = order_value * 0.001  # delivery STT on buy too in simplified model? actually sell only for equity delivery sell
            stt = 0.0  # equity delivery STT on sell only

        exchange_txn = order_value * 0.0000297
        sebi_fees = order_value * 0.000001
        stamp = order_value * 0.00015 if side == "BUY" else 0.0
        gst = (brokerage + exchange_txn) * 0.18
        total = brokerage + stt + exchange_txn + sebi_fees + gst + stamp

        return OrderChargeBreakdown(
            brokerage=round(brokerage, 2),
            stt=round(stt, 2),
            exchange_txn=round(exchange_txn, 2),
            sebi_fees=round(sebi_fees, 2),
            gst=round(gst, 2),
            stamp_duty=round(stamp, 2),
            total_charges=round(total, 2),
        )
