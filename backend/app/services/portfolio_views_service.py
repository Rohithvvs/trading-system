"""Holdings / Positions / Orders views over paper trading data."""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.paper_trading import PaperOrder, PaperPosition, PaperTradeHistory, PaperTradingAccount
from ..models.stock import StockMaster
from ..schemas.retail import (
    HoldingItem,
    HoldingsResponse,
    OrderListItem,
    OrdersPageResponse,
    PositionItem,
    PositionsResponse,
)
from .market_quotes_service import MarketQuotesService


class PortfolioViewsService:
    def __init__(self, db: Session, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id
        self.quotes = MarketQuotesService(db)

    def _account(self) -> PaperTradingAccount | None:
        return self.db.scalar(
            select(PaperTradingAccount).where(PaperTradingAccount.user_id == self.user_id)
        )

    def get_holdings(self) -> HoldingsResponse:
        account = self._account()
        if not account:
            return HoldingsResponse(
                holdings=[],
                total_invested=0,
                total_current_value=0,
                total_pnl=0,
                total_pnl_pct=0,
                todays_pnl=0,
                allocation=[],
                sector_exposure=[],
            )

        positions = list(
            self.db.scalars(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.status == "OPEN",
                )
            ).all()
        )
        symbols = [p.symbol for p in positions]
        quotes = self.quotes.get_quotes_batch(symbols) if symbols else {}
        meta = self._meta(symbols)

        holdings: list[HoldingItem] = []
        total_invested = 0.0
        total_value = 0.0
        todays_pnl = 0.0
        sector_map: dict[str, float] = defaultdict(float)

        for p in positions:
            qty = int(p.qty)
            avg = float(p.avg_entry_price)
            q = quotes.get(p.symbol, {})
            ltp = float(q.get("ltp") or p.current_price or avg)
            invested = qty * avg
            value = qty * ltp
            pnl = value - invested
            pnl_pct = (pnl / invested * 100) if invested else 0
            chg = float(q.get("change") or 0)
            day_pnl = qty * chg
            day_pct = float(q.get("change_pct") or 0)
            sector = meta.get(p.symbol, {}).get("sector") or "Other"
            sector_map[sector] += value
            total_invested += invested
            total_value += value
            todays_pnl += day_pnl
            holdings.append(
                HoldingItem(
                    symbol=p.symbol,
                    qty=qty,
                    avg_price=round(avg, 2),
                    ltp=round(ltp, 2),
                    invested=round(invested, 2),
                    current_value=round(value, 2),
                    pnl=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 2),
                    day_pnl=round(day_pnl, 2),
                    day_pnl_pct=round(day_pct, 2),
                    sector=sector,
                    product_type="CNC",
                )
            )

        total_pnl = total_value - total_invested
        total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0
        allocation = [
            {"symbol": h.symbol, "value": h.current_value, "pct": round(h.current_value / total_value * 100, 2) if total_value else 0}
            for h in holdings
        ]
        sector_exposure = [
            {"sector": s, "value": round(v, 2), "pct": round(v / total_value * 100, 2) if total_value else 0}
            for s, v in sorted(sector_map.items(), key=lambda x: -x[1])
        ]

        return HoldingsResponse(
            holdings=holdings,
            total_invested=round(total_invested, 2),
            total_current_value=round(total_value, 2),
            total_pnl=round(total_pnl, 2),
            total_pnl_pct=round(total_pnl_pct, 2),
            todays_pnl=round(todays_pnl, 2),
            allocation=allocation,
            sector_exposure=sector_exposure,
        )

    def get_positions(self) -> PositionsResponse:
        account = self._account()
        empty = PositionsResponse(open=[], closed=[], intraday=[], carry_forward=[], total_mtm=0, total_risk=0)
        if not account:
            return empty

        open_pos = list(
            self.db.scalars(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.status == "OPEN",
                )
            ).all()
        )
        closed_trades = list(
            self.db.scalars(
                select(PaperTradeHistory)
                .where(PaperTradeHistory.account_id == account.id)
                .order_by(PaperTradeHistory.closed_at.desc())
                .limit(100)
            ).all()
        )

        symbols = [p.symbol for p in open_pos]
        quotes = self.quotes.get_quotes_batch(symbols) if symbols else {}

        open_items: list[PositionItem] = []
        intraday: list[PositionItem] = []
        carry: list[PositionItem] = []
        total_mtm = 0.0
        total_risk = 0.0
        today = datetime.now(timezone.utc).date()

        for p in open_pos:
            q = quotes.get(p.symbol, {})
            ltp = float(q.get("ltp") or p.current_price or p.avg_entry_price)
            qty = int(p.qty)
            avg = float(p.avg_entry_price)
            invested = qty * avg
            upnl = (ltp - avg) * qty
            upnl_pct = (upnl / invested * 100) if invested else 0
            rr = None
            if p.stop_loss and p.target and avg:
                risk = abs(avg - float(p.stop_loss))
                reward = abs(float(p.target) - avg)
                rr = round(reward / risk, 2) if risk else None
                total_risk += risk * qty

            created = p.created_at
            is_intraday = created.date() == today if created else False
            ptype = "INTRADAY" if is_intraday else "CARRY_FORWARD"
            item = PositionItem(
                id=p.id,
                symbol=p.symbol,
                qty=qty,
                avg_entry_price=round(avg, 2),
                current_price=round(ltp, 2),
                unrealized_pnl=round(upnl, 2),
                unrealized_pnl_pct=round(upnl_pct, 2),
                invested_value=round(invested, 2),
                product_type="CNC",
                position_type=ptype,  # type: ignore[arg-type]
                stop_loss=float(p.stop_loss) if p.stop_loss else None,
                target=float(p.target) if p.target else None,
                risk_reward=rr,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            open_items.append(item)
            total_mtm += upnl
            if is_intraday:
                intraday.append(item)
            else:
                carry.append(item)

        closed_items: list[PositionItem] = []
        for t in closed_trades:
            closed_items.append(
                PositionItem(
                    id=t.id,
                    symbol=t.symbol,
                    qty=int(t.qty),
                    avg_entry_price=float(t.entry_price),
                    current_price=float(t.exit_price),
                    unrealized_pnl=float(t.pnl),
                    unrealized_pnl_pct=float(t.pnl_percent),
                    invested_value=float(t.qty) * float(t.entry_price),
                    product_type="CNC",
                    position_type="CLOSED",
                    created_at=t.opened_at,
                    updated_at=t.closed_at,
                )
            )

        return PositionsResponse(
            open=open_items,
            closed=closed_items,
            intraday=intraday,
            carry_forward=carry,
            total_mtm=round(total_mtm, 2),
            total_risk=round(total_risk, 2),
        )

    def get_orders(
        self,
        *,
        status: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> OrdersPageResponse:
        account = self._account()
        if not account:
            return OrdersPageResponse(
                items=[], total=0, page=1, page_size=page_size, pending=0, executed=0, rejected=0, cancelled=0
            )

        q = select(PaperOrder).where(PaperOrder.account_id == account.id)
        if status:
            q = q.where(PaperOrder.status == status.upper())
        if search:
            q = q.where(PaperOrder.symbol.ilike(f"%{search}%"))

        total = self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        rows = list(
            self.db.scalars(
                q.order_by(PaperOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
        )

        def count_status(s: str) -> int:
            return int(
                self.db.scalar(
                    select(func.count()).select_from(PaperOrder).where(
                        PaperOrder.account_id == account.id, PaperOrder.status == s
                    )
                )
                or 0
            )

        items = [
            OrderListItem(
                id=o.id,
                symbol=o.symbol,
                side=o.side,
                type=o.order_type,
                product_type=o.product_type,
                qty=int(o.qty),
                price=float(o.order_price) if o.order_price is not None else None,
                stop_price=float(o.stop_price) if o.stop_price is not None else None,
                status=o.status,
                lifecycle_state=o.lifecycle_state,
                filled_price=float(o.filled_price) if o.filled_price is not None else None,
                created_at=o.created_at,
                filled_at=o.filled_at,
                notes=o.notes,
            )
            for o in rows
        ]

        return OrdersPageResponse(
            items=items,
            total=int(total),
            page=page,
            page_size=page_size,
            pending=count_status("PENDING"),
            executed=count_status("FILLED"),
            rejected=count_status("REJECTED"),
            cancelled=count_status("CANCELLED"),
        )

    def _meta(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        if not symbols:
            return {}
        rows = self.db.scalars(select(StockMaster).where(StockMaster.symbol.in_(symbols))).all()
        return {r.symbol: {"sector": r.sector, "company_name": r.company_name} for r in rows}
