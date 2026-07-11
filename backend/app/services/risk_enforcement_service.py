"""Hard risk enforcement — rejects orders that violate user limits."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..models.paper_trading import PaperOrder, PaperPosition, PaperTradeHistory, PaperTradingAccount
from ..models.retail import UserRiskLimits
from ..models.stock import StockMaster

# NSE freeze quantity (approx) — orders above this must be rejected or split
FREEZE_QTY_DEFAULT = 100000
# Circuit buffer: reject MARKET buys near upper circuit
CIRCUIT_NEAR_PCT = 0.5


@dataclass
class RiskCheckResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)

    def reject(self, code: str, message: str) -> None:
        self.allowed = False
        self.reasons.append(message)
        self.checks.append({"code": code, "passed": False, "message": message})

    def pass_check(self, code: str, message: str) -> None:
        self.checks.append({"code": code, "passed": True, "message": message})


class RiskEnforcementService:
    def __init__(self, db: Session, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def get_or_create_limits(self) -> UserRiskLimits:
        row = self.db.scalar(select(UserRiskLimits).where(UserRiskLimits.user_id == self.user_id))
        if row:
            return row
        row = UserRiskLimits(user_id=self.user_id)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_limits(self, **kwargs: Any) -> UserRiskLimits:
        row = self.get_or_create_limits()
        for k, v in kwargs.items():
            if v is not None and hasattr(row, k):
                setattr(row, k, v)
        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(row)
        return row

    def validate_order(
        self,
        *,
        account: PaperTradingAccount,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        product_type: str = "CNC",
        order_type: str = "MARKET",
        stop_loss: float | None = None,
        quote: dict[str, Any] | None = None,
    ) -> RiskCheckResult:
        result = RiskCheckResult(allowed=True)
        limits = self.get_or_create_limits()

        if not limits.enabled:
            result.pass_check("RISK_DISABLED", "Risk enforcement is disabled for this account")
            return result

        order_value = Decimal(str(qty)) * Decimal(str(price))
        quote = quote or {}

        # ── Freeze quantity ──
        freeze_qty = FREEZE_QTY_DEFAULT
        if qty > freeze_qty:
            result.reject("FREEZE_QTY", f"Quantity {qty} exceeds freeze quantity limit of {freeze_qty}")
        else:
            result.pass_check("FREEZE_QTY", f"Quantity {qty} within freeze limit {freeze_qty}")

        # ── Circuit checks ──
        upper = quote.get("upper_circuit")
        lower = quote.get("lower_circuit")
        ltp = quote.get("ltp") or price
        if upper is not None and side == "BUY" and float(ltp) >= float(upper) * (1 - CIRCUIT_NEAR_PCT / 100):
            if float(price) >= float(upper):
                result.reject("CIRCUIT", f"Price {price} at/above upper circuit {upper}")
            else:
                result.pass_check("CIRCUIT", "Price below upper circuit")
        elif lower is not None and side == "SELL" and float(ltp) <= float(lower) * (1 + CIRCUIT_NEAR_PCT / 100):
            if float(price) <= float(lower):
                result.reject("CIRCUIT", f"Price {price} at/below lower circuit {lower}")
            else:
                result.pass_check("CIRCUIT", "Price above lower circuit")
        else:
            result.pass_check("CIRCUIT", "No circuit violation")

        # ── Max position size ──
        if side == "BUY" and order_value > limits.max_position_size:
            result.reject(
                "MAX_POSITION_SIZE",
                f"Order value ₹{float(order_value):,.2f} exceeds max position size ₹{float(limits.max_position_size):,.2f}",
            )
        else:
            result.pass_check("MAX_POSITION_SIZE", "Position size within limit")

        # ── Max open positions ──
        open_count = self.db.scalar(
            select(func.count()).select_from(PaperPosition).where(
                PaperPosition.account_id == account.id,
                PaperPosition.status == "OPEN",
            )
        ) or 0
        existing_pos = self.db.scalar(
            select(PaperPosition).where(
                PaperPosition.account_id == account.id,
                PaperPosition.symbol == symbol,
                PaperPosition.status == "OPEN",
            )
        )
        if side == "BUY" and not existing_pos and open_count >= limits.max_open_positions:
            result.reject(
                "MAX_OPEN_POSITIONS",
                f"Open positions {open_count} at max limit {limits.max_open_positions}",
            )
        else:
            result.pass_check("MAX_OPEN_POSITIONS", f"Open positions {open_count}/{limits.max_open_positions}")

        # ── Max exposure ──
        current_exposure = self._current_exposure(account.id)
        projected = current_exposure + (order_value if side == "BUY" else Decimal("0"))
        if side == "BUY" and projected > limits.max_exposure:
            result.reject(
                "MAX_EXPOSURE",
                f"Projected exposure ₹{float(projected):,.2f} exceeds max ₹{float(limits.max_exposure):,.2f}",
            )
        else:
            result.pass_check("MAX_EXPOSURE", f"Exposure ₹{float(projected):,.2f} / ₹{float(limits.max_exposure):,.2f}")

        # ── Sector exposure ──
        if side == "BUY":
            sector = self._sector_for(symbol)
            if sector:
                sector_exp = self._sector_exposure(account.id, sector)
                sector_projected = sector_exp + order_value
                total_for_pct = max(projected, Decimal("1"))
                sector_pct = float(sector_projected / total_for_pct * 100)
                if sector_pct > float(limits.max_sector_exposure_pct):
                    result.reject(
                        "SECTOR_EXPOSURE",
                        f"Sector '{sector}' exposure {sector_pct:.1f}% exceeds max {float(limits.max_sector_exposure_pct):.1f}%",
                    )
                else:
                    result.pass_check("SECTOR_EXPOSURE", f"Sector '{sector}' {sector_pct:.1f}% within limit")
            else:
                result.pass_check("SECTOR_EXPOSURE", "Sector unknown — skipped")

        # ── Leverage ──
        equity = Decimal(str(account.cash_balance)) + current_exposure
        if equity > 0 and product_type == "MIS":
            lev = float(projected / equity) if side == "BUY" else 0
            if lev > float(limits.max_leverage):
                result.reject(
                    "LEVERAGE",
                    f"Leverage {lev:.2f}x exceeds max {float(limits.max_leverage):.2f}x",
                )
            else:
                result.pass_check("LEVERAGE", f"Leverage {lev:.2f}x within limit")
        else:
            result.pass_check("LEVERAGE", "Leverage check N/A for CNC or zero equity")

        # ── Margin / funds ──
        if side == "BUY":
            available = Decimal(str(account.cash_balance))
            margin_req = order_value if product_type == "CNC" else order_value / Decimal(str(limits.max_leverage or 5))
            if margin_req > available:
                result.reject(
                    "MARGIN",
                    f"Insufficient funds. Required ₹{float(margin_req):,.2f}, available ₹{float(available):,.2f}",
                )
            else:
                result.pass_check("MARGIN", f"Margin ₹{float(margin_req):,.2f} covered by ₹{float(available):,.2f}")

        # ── Max daily loss ──
        daily_pnl = self._daily_pnl(account.id)
        if daily_pnl < 0 and abs(daily_pnl) >= limits.max_daily_loss:
            result.reject(
                "MAX_DAILY_LOSS",
                f"Daily loss ₹{float(abs(daily_pnl)):,.2f} has hit max daily loss ₹{float(limits.max_daily_loss):,.2f}. New risk-increasing orders blocked.",
            )
        else:
            result.pass_check("MAX_DAILY_LOSS", f"Daily PnL ₹{float(daily_pnl):,.2f} within loss limit")

        # ── Max trade loss (if stop provided) ──
        if side == "BUY" and stop_loss is not None and price > 0:
            risk_per_share = Decimal(str(price)) - Decimal(str(stop_loss))
            if risk_per_share > 0:
                trade_risk = risk_per_share * Decimal(str(qty))
                if trade_risk > limits.max_trade_loss:
                    result.reject(
                        "MAX_TRADE_LOSS",
                        f"Trade risk ₹{float(trade_risk):,.2f} exceeds max trade loss ₹{float(limits.max_trade_loss):,.2f}",
                    )
                else:
                    result.pass_check("MAX_TRADE_LOSS", f"Trade risk ₹{float(trade_risk):,.2f} within limit")
            else:
                result.pass_check("MAX_TRADE_LOSS", "Stop above entry — skipped")
        else:
            result.pass_check("MAX_TRADE_LOSS", "No stop loss provided for trade risk calc")

        return result

    def _current_exposure(self, account_id: int) -> Decimal:
        positions = self.db.scalars(
            select(PaperPosition).where(PaperPosition.account_id == account_id, PaperPosition.status == "OPEN")
        ).all()
        total = Decimal("0")
        for p in positions:
            total += Decimal(str(p.qty)) * Decimal(str(p.current_price or p.avg_entry_price))
        return total

    def _sector_exposure(self, account_id: int, sector: str) -> Decimal:
        positions = self.db.scalars(
            select(PaperPosition).where(PaperPosition.account_id == account_id, PaperPosition.status == "OPEN")
        ).all()
        total = Decimal("0")
        for p in positions:
            if self._sector_for(p.symbol) == sector:
                total += Decimal(str(p.qty)) * Decimal(str(p.current_price or p.avg_entry_price))
        return total

    def _sector_for(self, symbol: str) -> str | None:
        row = self.db.scalar(select(StockMaster).where(StockMaster.symbol == symbol.upper()))
        return row.sector if row else None

    def _daily_pnl(self, account_id: int) -> Decimal:
        try:
            ist = ZoneInfo("Asia/Kolkata")
        except Exception:
            ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        start_ist = datetime(now_ist.year, now_ist.month, now_ist.day, 0, 0, 0, tzinfo=ist)
        start_utc = start_ist.astimezone(timezone.utc)

        trades = self.db.scalars(
            select(PaperTradeHistory).where(
                PaperTradeHistory.account_id == account_id,
                PaperTradeHistory.closed_at >= start_utc,
            )
        ).all()
        realized = sum((Decimal(str(t.pnl)) for t in trades), Decimal("0"))

        positions = self.db.scalars(
            select(PaperPosition).where(PaperPosition.account_id == account_id, PaperPosition.status == "OPEN")
        ).all()
        unrealized = sum((Decimal(str(p.unrealized_pnl or 0)) for p in positions), Decimal("0"))
        return realized + unrealized
