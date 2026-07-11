"""
User-scoped Daily Analytics for Paper Trading.

All calculations use the authenticated user's paper account only.
Never aggregates across users.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.paper_trading import (
    PaperAlert,
    PaperDailyJournal,
    PaperOrder,
    PaperPosition,
    PaperTradeHistory,
    PaperTradingAccount,
)
from ..services.paper_trading_service import PaperTradingService
from ..utils import get_logger
from ..utils.money import as_float, dec

IST = ZoneInfo("Asia/Kolkata")

# Lightweight sector map for Nifty-style cash symbols (display only)
_SECTOR_MAP: dict[str, str] = {
    "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking", "KOTAKBANK": "Banking",
    "AXISBANK": "Banking", "INDUSINDBK": "Banking", "BANKBARODA": "Banking", "PNB": "Banking",
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT", "TECHM": "IT", "LTIM": "IT",
    "PERSISTENT": "IT", "COFORGE": "IT", "MPHASIS": "IT",
    "MARUTI": "Auto", "TATAMOTORS": "Auto", "M&M": "Auto", "BAJAJ-AUTO": "Auto", "HEROMOTOCO": "Auto",
    "EICHERMOT": "Auto", "ASHOKLEY": "Auto", "TVSMOTOR": "Auto",
    "RELIANCE": "Energy", "ONGC": "Energy", "NTPC": "Energy", "POWERGRID": "Energy", "BPCL": "Energy",
    "IOC": "Energy", "GAIL": "Energy", "ADANIGREEN": "Energy",
    "BAJFINANCE": "Finance", "BAJAJFINSV": "Finance", "HDFCLIFE": "Finance", "SBILIFE": "Finance",
    "ICICIPRULI": "Finance", "PFC": "Finance", "RECLTD": "Finance",
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma", "DIVISLAB": "Pharma",
    "APOLLOHOSP": "Pharma", "AUROPHARMA": "Pharma", "LUPIN": "Pharma",
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG", "BRITANNIA": "FMCG",
    "DABUR": "FMCG", "MARICO": "FMCG", "GODREJCP": "FMCG", "TATACONSUM": "FMCG",
}


def _norm_sym(symbol: str) -> str:
    s = (symbol or "").upper().replace("NSE:", "").replace("-EQ", "").strip()
    return s


def _sector_for(symbol: str) -> str:
    return _SECTOR_MAP.get(_norm_sym(symbol), "Others")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _to_ist(dt: datetime) -> datetime:
    return _aware(dt).astimezone(IST)  # type: ignore[union-attr]


def _parse_range(
    period: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[datetime, datetime, str]:
    """Return (start_utc, end_utc, label) for filtering closed trades / activity."""
    now_ist = datetime.now(IST)
    today = now_ist.date()

    if period == "custom" and start_date and end_date:
        s = date.fromisoformat(start_date)
        e = date.fromisoformat(end_date)
        start_ist = datetime.combine(s, time.min, tzinfo=IST)
        end_ist = datetime.combine(e + timedelta(days=1), time.min, tzinfo=IST)
        return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc), f"{start_date} → {end_date}"

    if period == "yesterday":
        d = today - timedelta(days=1)
        start_ist = datetime.combine(d, time.min, tzinfo=IST)
        end_ist = datetime.combine(today, time.min, tzinfo=IST)
        label = d.isoformat()
    elif period == "week":
        start = today - timedelta(days=today.weekday())  # Monday
        start_ist = datetime.combine(start, time.min, tzinfo=IST)
        end_ist = now_ist + timedelta(seconds=1)
        label = f"Week of {start.isoformat()}"
    elif period == "month":
        start = today.replace(day=1)
        start_ist = datetime.combine(start, time.min, tzinfo=IST)
        end_ist = now_ist + timedelta(seconds=1)
        label = start.strftime("%Y-%m")
    else:  # today (default)
        start_ist = datetime.combine(today, time.min, tzinfo=IST)
        end_ist = now_ist + timedelta(seconds=1)
        label = today.isoformat()
        period = "today"

    return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc), label


class DailyAnalyticsService:
    def __init__(self, db: Session, user_id) -> None:
        self.db = db
        self.user_id = user_id
        self.logger = get_logger("app.daily_analytics")
        self._pts = PaperTradingService(db, user_id=user_id)

    def _account(self) -> PaperTradingAccount:
        return self._pts._get_or_create_account()

    def build(
        self,
        period: str = "today",
        start_date: str | None = None,
        end_date: str | None = None,
        include_ai: bool = True,
    ) -> dict[str, Any]:
        account = self._account()
        start_utc, end_utc, range_label = _parse_range(period, start_date, end_date)

        trades = self._trades_in_range(account.id, start_utc, end_utc)
        orders = self._orders_in_range(account.id, start_utc, end_utc)
        positions = self._open_positions(account.id)

        overview = self._overview(account, trades, orders, positions)
        trade_summary = self._trade_summary(trades, orders)
        performance = self._performance(account, trades)
        portfolio = self._portfolio(account, positions)
        sector = self._sector_analysis(trades, positions)
        symbols = self._symbol_performance(trades, positions)
        best = self._best_trade(trades)
        worst = self._worst_trade(trades)
        risk = self._risk(account, positions, trades)
        time_analysis = self._time_analysis(trades, orders)
        score = self._trading_score(overview, performance, trade_summary)
        emotional = self._emotional(score, performance, risk)
        journal = self._get_journal(account.id, range_label if period == "today" else date.today().isoformat() if period != "custom" else (start_date or date.today().isoformat()))
        charts = self._charts(trades, positions, sector, account)
        market = self._market_context()
        ai = self._ai_insights(overview, performance, best, worst, risk, emotional, include_ai)

        return {
            "account_id": account.id,
            "period": period if period != "custom" or not start_date else "custom",
            "range_label": range_label,
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overview": overview,
            "trading_score": score,
            "trade_summary": trade_summary,
            "performance": performance,
            "portfolio": portfolio,
            "sector_analysis": sector,
            "symbol_performance": symbols,
            "best_trade": best,
            "worst_trade": worst,
            "risk_analysis": risk,
            "time_analysis": time_analysis,
            "emotional_analysis": emotional,
            "journal": journal,
            "ai_insights": ai,
            "market_context": market,
            "charts": charts,
        }

    def _trades_in_range(self, account_id: int, start: datetime, end: datetime) -> list[PaperTradeHistory]:
        rows = list(
            self.db.scalars(
                select(PaperTradeHistory)
                .where(PaperTradeHistory.account_id == account_id)
                .order_by(PaperTradeHistory.closed_at.desc())
            )
        )
        out = []
        for t in rows:
            closed = _aware(t.closed_at)
            if closed and start <= closed < end:
                out.append(t)
        return out

    def _orders_in_range(self, account_id: int, start: datetime, end: datetime) -> list[PaperOrder]:
        rows = list(
            self.db.scalars(select(PaperOrder).where(PaperOrder.account_id == account_id))
        )
        out = []
        for o in rows:
            created = _aware(o.created_at)
            filled = _aware(o.filled_at)
            if created and start <= created < end:
                out.append(o)
            elif filled and start <= filled < end and o not in out:
                out.append(o)
        return out

    def _open_positions(self, account_id: int) -> list[PaperPosition]:
        return list(
            self.db.scalars(
                select(PaperPosition).where(
                    PaperPosition.account_id == account_id,
                    PaperPosition.status == "OPEN",
                )
            )
        )

    def _overview(
        self,
        account: PaperTradingAccount,
        trades: list[PaperTradeHistory],
        orders: list[PaperOrder],
        positions: list[PaperPosition],
    ) -> dict[str, Any]:
        wins = [t for t in trades if float(t.pnl or 0) > 0]
        losses = [t for t in trades if float(t.pnl or 0) < 0]
        gross_profit = sum(float(t.pnl) for t in wins)
        gross_loss = abs(sum(float(t.pnl) for t in losses))
        realized = sum(float(t.pnl or 0) for t in trades)
        unrealized = sum(float(p.unrealized_pnl or 0) for p in positions)
        capital = float(account.starting_balance or 1_000_000)
        invested = sum(float(dec(p.avg_entry_price) * dec(p.qty)) for p in positions)
        cash = float(account.cash_balance or 0)

        largest_winner = max(wins, key=lambda t: float(t.pnl)) if wins else None
        largest_loser = min(losses, key=lambda t: float(t.pnl)) if losses else None

        return {
            "todays_profit": round(gross_profit, 2),
            "todays_loss": round(gross_loss, 2),
            "todays_return_pct": round((realized / capital) * 100, 2) if capital else 0.0,
            "todays_realized_pnl": round(realized, 2),
            "todays_unrealized_pnl": round(unrealized, 2),
            "trades_executed": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "open_positions": len(positions),
            "closed_positions": len(trades),
            "capital_used": round(invested, 2),
            "cash_remaining": round(cash, 2),
            "largest_winner": round(float(largest_winner.pnl), 2) if largest_winner else 0.0,
            "largest_loser": round(float(largest_loser.pnl), 2) if largest_loser else 0.0,
            "average_win": round(gross_profit / len(wins), 2) if wins else 0.0,
            "average_loss": round(gross_loss / len(losses), 2) if losses else 0.0,
        }

    def _trade_summary(self, trades: list[PaperTradeHistory], orders: list[PaperOrder]) -> dict[str, Any]:
        executed = [o for o in orders if o.status == "FILLED"]
        pending = [o for o in orders if o.status == "PENDING"]
        cancelled = [o for o in orders if o.status == "CANCELLED"]
        rejected = [o for o in orders if o.status == "REJECTED"]
        hold_mins = []
        sizes = []
        for t in trades:
            opened = _aware(t.opened_at)
            closed = _aware(t.closed_at)
            if opened and closed:
                hold_mins.append((closed - opened).total_seconds() / 60.0)
            sizes.append(float(dec(t.qty) * dec(t.entry_price)))
        return {
            "total_trades": len(trades),
            "executed_orders": len(executed),
            "pending_orders": len(pending),
            "cancelled_orders": len(cancelled),
            "rejected_orders": len(rejected),
            "average_holding_minutes": round(sum(hold_mins) / len(hold_mins), 1) if hold_mins else 0.0,
            "average_position_size": round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
        }

    def _performance(self, account: PaperTradingAccount, trades: list[PaperTradeHistory]) -> dict[str, Any]:
        wins = [float(t.pnl) for t in trades if float(t.pnl or 0) > 0]
        losses = [float(t.pnl) for t in trades if float(t.pnl or 0) < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        net = gross_profit - gross_loss
        n = len(trades)
        win_rate = (len(wins) / n * 100) if n else 0.0
        loss_rate = (len(losses) / n * 100) if n else 0.0
        avg_win = (gross_profit / len(wins)) if wins else 0.0
        avg_loss = (gross_loss / len(losses)) if losses else 0.0
        pf = (gross_profit / gross_loss) if gross_loss > 1e-9 else (None if not wins else 99.0)
        rr = (avg_win / avg_loss) if avg_loss > 1e-9 else None
        expectancy = ((win_rate / 100) * avg_win) - ((loss_rate / 100) * avg_loss) if n else 0.0

        # Equity curve / drawdown from chronological trades
        equity = float(account.starting_balance or 1_000_000)
        peak = equity
        max_dd = 0.0
        returns: list[float] = []
        sorted_trades = sorted(trades, key=lambda t: _aware(t.closed_at) or datetime.min.replace(tzinfo=timezone.utc))
        for t in sorted_trades:
            pnl = float(t.pnl or 0)
            equity += pnl
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)
            if peak > 0:
                returns.append(pnl / float(account.starting_balance or 1_000_000))

        sharpe = None
        sortino = None
        if len(returns) >= 2:
            mean_r = sum(returns) / len(returns)
            var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
            std = math.sqrt(var) if var > 0 else 0.0
            if std > 1e-12:
                sharpe = round((mean_r / std) * math.sqrt(252), 2)
            downside = [r for r in returns if r < 0]
            if downside:
                dvar = sum(r ** 2 for r in downside) / len(downside)
                dstd = math.sqrt(dvar) if dvar > 0 else 0.0
                if dstd > 1e-12:
                    sortino = round((mean_r / dstd) * math.sqrt(252), 2)

        recovery = round(net / max_dd, 2) if max_dd > 1e-9 else None

        return {
            "net_profit": round(net, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(pf, 2) if pf is not None else None,
            "average_win": round(avg_win, 2),
            "average_loss": round(avg_loss, 2),
            "win_rate": round(win_rate, 2),
            "loss_rate": round(loss_rate, 2),
            "risk_reward_ratio": round(rr, 2) if rr is not None else None,
            "expectancy": round(expectancy, 2),
            "recovery_factor": recovery,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "maximum_drawdown": round(max_dd, 2),
        }

    def _portfolio(self, account: PaperTradingAccount, positions: list[PaperPosition]) -> dict[str, Any]:
        cash = float(account.cash_balance or 0)
        invested = sum(float(dec(p.avg_entry_price) * dec(p.qty)) for p in positions)
        unrealized = sum(float(p.unrealized_pnl or 0) for p in positions)
        equity = cash + invested + unrealized
        start = float(account.starting_balance or 1_000_000)
        return {
            "portfolio_value": round(equity, 2),
            "cash_balance": round(cash, 2),
            "invested_amount": round(invested, 2),
            "allocation_pct": round((invested / equity) * 100, 2) if equity else 0.0,
            "utilization_pct": round((invested / start) * 100, 2) if start else 0.0,
        }

    def _sector_analysis(self, trades: list[PaperTradeHistory], positions: list[PaperPosition]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"trades": 0, "allocation": 0.0, "profit": 0.0, "loss": 0.0})
        for t in trades:
            sec = _sector_for(t.symbol)
            buckets[sec]["trades"] += 1
            pnl = float(t.pnl or 0)
            if pnl >= 0:
                buckets[sec]["profit"] += pnl
            else:
                buckets[sec]["loss"] += abs(pnl)
        for p in positions:
            sec = _sector_for(p.symbol)
            buckets[sec]["allocation"] += float(dec(p.avg_entry_price) * dec(p.qty))
        return [
            {
                "sector": k,
                "trades": int(v["trades"]),
                "allocation": round(v["allocation"], 2),
                "profit": round(v["profit"], 2),
                "loss": round(v["loss"], 2),
            }
            for k, v in sorted(buckets.items(), key=lambda x: x[1]["allocation"] + x[1]["profit"], reverse=True)
        ]

    def _symbol_performance(
        self, trades: list[PaperTradeHistory], positions: list[PaperPosition]
    ) -> list[dict[str, Any]]:
        rows = []
        for t in trades:
            opened = _aware(t.opened_at)
            closed = _aware(t.closed_at)
            hold = ((closed - opened).total_seconds() / 60.0) if opened and closed else 0.0
            rows.append({
                "symbol": t.symbol,
                "entry": round(float(t.entry_price), 2),
                "exit": round(float(t.exit_price), 2),
                "current_price": round(float(t.exit_price), 2),
                "quantity": int(dec(t.qty)),
                "return_pct": round(float(t.pnl_percent or 0), 2),
                "holding_time_minutes": round(hold, 1),
                "pnl": round(float(t.pnl or 0), 2),
                "status": "CLOSED",
            })
        for p in positions:
            invested = float(dec(p.avg_entry_price) * dec(p.qty))
            upnl = float(p.unrealized_pnl or 0)
            ret = (upnl / invested * 100) if invested else 0.0
            opened = _aware(p.created_at)
            hold = ((datetime.now(timezone.utc) - opened).total_seconds() / 60.0) if opened else 0.0
            rows.append({
                "symbol": p.symbol,
                "entry": round(float(p.avg_entry_price), 2),
                "exit": None,
                "current_price": round(float(p.current_price or 0), 2),
                "quantity": int(dec(p.qty)),
                "return_pct": round(ret, 2),
                "holding_time_minutes": round(hold, 1),
                "pnl": round(upnl, 2),
                "status": "OPEN",
            })
        rows.sort(key=lambda r: r["pnl"], reverse=True)
        return rows

    def _best_trade(self, trades: list[PaperTradeHistory]) -> dict[str, Any] | None:
        if not trades:
            return None
        t = max(trades, key=lambda x: float(x.pnl or 0))
        opened = _aware(t.opened_at)
        closed = _aware(t.closed_at)
        hold = ((closed - opened).total_seconds() / 60.0) if opened and closed else 0.0
        return {
            "symbol": t.symbol,
            "entry": round(float(t.entry_price), 2),
            "exit": round(float(t.exit_price), 2),
            "profit": round(float(t.pnl or 0), 2),
            "return_pct": round(float(t.pnl_percent or 0), 2),
            "holding_time_minutes": round(hold, 1),
            "reason": t.exit_reason or t.notes or "Target / manual exit",
        }

    def _worst_trade(self, trades: list[PaperTradeHistory]) -> dict[str, Any] | None:
        if not trades:
            return None
        t = min(trades, key=lambda x: float(x.pnl or 0))
        opened = _aware(t.opened_at)
        closed = _aware(t.closed_at)
        hold = ((closed - opened).total_seconds() / 60.0) if opened and closed else 0.0
        pnl = float(t.pnl or 0)
        mistake = "Stop-loss or adverse move"
        if hold < 5:
            mistake = "Very short hold — possible impulsive exit"
        elif pnl < 0 and t.exit_reason and "STOP" in str(t.exit_reason).upper():
            mistake = "Stop-loss hit — review entry timing / size"
        return {
            "symbol": t.symbol,
            "entry": round(float(t.entry_price), 2),
            "exit": round(float(t.exit_price), 2),
            "loss": round(pnl, 2),
            "return_pct": round(float(t.pnl_percent or 0), 2),
            "holding_time_minutes": round(hold, 1),
            "mistake": mistake,
        }

    def _risk(self, account: PaperTradingAccount, positions: list[PaperPosition], trades: list[PaperTradeHistory]) -> dict[str, Any]:
        sizes = [float(dec(p.avg_entry_price) * dec(p.qty)) for p in positions]
        start = float(account.starting_balance or 1_000_000)
        equity = float(account.cash_balance or 0) + sum(sizes) + sum(float(p.unrealized_pnl or 0) for p in positions)
        largest = max(sizes) if sizes else 0.0
        smallest = min(sizes) if sizes else 0.0
        exposure = sum(sizes)
        concentration = (largest / equity * 100) if equity else 0.0
        risk_pct = (largest / start * 100) if start else 0.0
        return {
            "largest_position": round(largest, 2),
            "smallest_position": round(smallest, 2),
            "risk_pct": round(risk_pct, 2),
            "exposure": round(exposure, 2),
            "capital_concentration": round(concentration, 2),
        }

    def _time_analysis(self, trades: list[PaperTradeHistory], orders: list[PaperOrder]) -> list[dict[str, Any]]:
        buckets = ["09:15", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00"]
        # Map hour -> bucket label
        def bucket_for(dt: datetime) -> str:
            h = _to_ist(dt).hour
            m = _to_ist(dt).minute
            if h < 10 or (h == 9 and m >= 15):
                if h == 9:
                    return "09:15"
            mapping = {10: "10:00", 11: "11:00", 12: "12:00", 13: "13:00", 14: "14:00", 15: "15:00"}
            if h in mapping:
                return mapping[h]
            if h < 9:
                return "09:15"
            return "15:00"

        counts: dict[str, int] = {b: 0 for b in buckets}
        pnl_map: dict[str, float] = {b: 0.0 for b in buckets}
        for t in trades:
            closed = _aware(t.closed_at)
            if not closed:
                continue
            b = bucket_for(closed)
            if b not in counts:
                counts[b] = 0
                pnl_map[b] = 0.0
            counts[b] += 1
            pnl_map[b] += float(t.pnl or 0)
        for o in orders:
            created = _aware(o.created_at)
            if not created:
                continue
            b = bucket_for(created)
            if b not in counts:
                counts[b] = 0
                pnl_map[b] = 0.0
            # orders count only if no trade already counted — still count order activity
            counts[b] += 0  # trades already counted; show order fills via trades primarily
        return [{"slot": b, "trades": counts.get(b, 0), "pnl": round(pnl_map.get(b, 0.0), 2)} for b in buckets]

    def _trading_score(self, overview: dict, performance: dict, summary: dict) -> dict[str, Any]:
        score = 50.0
        wr = performance.get("win_rate") or 0
        score += min(25, wr * 0.25)
        pf = performance.get("profit_factor")
        if pf is not None:
            score += min(15, max(0, (pf - 1) * 10))
        if performance.get("net_profit", 0) > 0:
            score += 10
        elif performance.get("net_profit", 0) < 0:
            score -= 10
        if overview.get("losing_trades", 0) > overview.get("winning_trades", 0) * 2:
            score -= 10
        if summary.get("cancelled_orders", 0) > summary.get("executed_orders", 0):
            score -= 5
        score = max(0, min(100, round(score)))
        if score >= 90:
            label = "Excellent"
        elif score >= 75:
            label = "Good"
        elif score >= 55:
            label = "Average"
        else:
            label = "Poor"
        return {"score": score, "label": label}

    def _emotional(self, score: dict, performance: dict, risk: dict) -> dict[str, Any]:
        base = score.get("score", 50)
        wr = performance.get("win_rate") or 0
        conc = risk.get("capital_concentration") or 0
        return {
            "discipline": min(100, max(0, int(base * 0.9 + (10 if wr >= 50 else 0)))),
            "patience": min(100, max(0, int(70 if (performance.get("expectancy") or 0) >= 0 else 40))),
            "risk_control": min(100, max(0, int(90 - min(40, conc / 2)))),
            "execution_quality": min(100, max(0, int(base))),
            "consistency": min(100, max(0, int(wr + 20))),
        }

    def _charts(
        self,
        trades: list[PaperTradeHistory],
        positions: list[PaperPosition],
        sector: list[dict],
        account: PaperTradingAccount,
    ) -> dict[str, Any]:
        sorted_t = sorted(trades, key=lambda t: _aware(t.closed_at) or datetime.min.replace(tzinfo=timezone.utc))
        equity = float(account.starting_balance or 1_000_000)
        equity_curve = []
        for t in sorted_t:
            equity += float(t.pnl or 0)
            closed = _aware(t.closed_at)
            equity_curve.append({
                "t": closed.isoformat() if closed else None,
                "equity": round(equity, 2),
                "pnl": round(float(t.pnl or 0), 2),
            })
        hourly = self._time_analysis(trades, [])
        win_loss = {
            "wins": len([t for t in trades if float(t.pnl or 0) > 0]),
            "losses": len([t for t in trades if float(t.pnl or 0) < 0]),
        }
        capital_usage = {
            "cash": round(float(account.cash_balance or 0), 2),
            "invested": round(sum(float(dec(p.avg_entry_price) * dec(p.qty)) for p in positions), 2),
        }
        return {
            "equity_curve": equity_curve,
            "hourly_pnl": hourly,
            "trade_distribution": win_loss,
            "sector_allocation": [{"name": s["sector"], "value": s["allocation"]} for s in sector if s["allocation"] > 0],
            "capital_usage": capital_usage,
            "win_loss_ratio": win_loss,
        }

    def _market_context(self) -> dict[str, Any]:
        """Best-effort market context; never blocks daily analytics if data unavailable."""
        try:
            from ..services.workstation_service import WorkstationService
            # Lightweight placeholder — avoid heavy FYERS fan-out on every load
            return {
                "nifty": None,
                "bank_nifty": None,
                "vix": None,
                "market_breadth": None,
                "sector_strength": None,
                "note": "Market context loads best-effort; open Workstation for live indices.",
            }
        except Exception:
            return {
                "nifty": None,
                "bank_nifty": None,
                "vix": None,
                "market_breadth": None,
                "sector_strength": None,
                "note": "Unavailable",
            }

    def _ai_insights(
        self,
        overview: dict,
        performance: dict,
        best: dict | None,
        worst: dict | None,
        risk: dict,
        emotional: dict,
        include_ai: bool,
    ) -> dict[str, Any]:
        fallback = self._heuristic_ai(overview, performance, best, worst, risk, emotional)
        if not include_ai:
            return fallback
        try:
            from ..services.llm_service import LLMService
            llm = LLMService()
            ctx = {
                "overview": overview,
                "performance": performance,
                "best_trade": best,
                "worst_trade": worst,
                "risk": risk,
                "emotional": emotional,
            }
            # Reuse groq path via build_reasoning-style call if available
            if hasattr(llm, "build_daily_journal_insights"):
                out = llm.build_daily_journal_insights(ctx)
                if out:
                    return out
            # Generic: use build_reasoning with synthetic symbol
            parsed = llm.build_reasoning("DAILY_PAPER", ctx)
            if parsed and parsed.get("summary"):
                return {
                    "summary": parsed.get("summary"),
                    "strengths": parsed.get("bullets", [])[:3],
                    "weaknesses": parsed.get("risk_factors", [])[:3],
                    "mistakes": parsed.get("invalidation_signals", [])[:3],
                    "suggestions": fallback["suggestions"],
                    "risk_observations": parsed.get("risk_factors", [])[:2],
                    "confidence_score": fallback["confidence_score"],
                    "recommendations": fallback["recommendations"],
                    "source": "llm",
                }
        except Exception as exc:
            self.logger.warning("Daily AI insights fallback | error=%s", exc)
        return fallback

    def _heuristic_ai(
        self,
        overview: dict,
        performance: dict,
        best: dict | None,
        worst: dict | None,
        risk: dict,
        emotional: dict,
    ) -> dict[str, Any]:
        net = performance.get("net_profit") or 0
        wr = performance.get("win_rate") or 0
        strengths = []
        weaknesses = []
        if wr >= 50:
            strengths.append(f"Win rate at {wr}% is solid for the selected period.")
        if net > 0:
            strengths.append(f"Net profit of ₹{net} shows positive expectancy today.")
        if emotional.get("risk_control", 0) >= 70:
            strengths.append("Risk control scores well — position concentration is managed.")
        if not strengths:
            strengths.append("Journal the session and protect capital for the next session.")

        if wr < 40 and overview.get("trades_executed", 0) > 0:
            weaknesses.append("Win rate is low — review entry criteria and filters.")
        if (risk.get("capital_concentration") or 0) > 40:
            weaknesses.append("Capital is concentrated in a large position — diversify size.")
        if net < 0:
            weaknesses.append("Session is underwater — reduce size until edge returns.")
        if not weaknesses:
            weaknesses.append("No major red flags; keep process discipline.")

        mistakes = []
        if worst:
            mistakes.append(f"{worst.get('symbol')}: {worst.get('mistake')}")
        else:
            mistakes.append("No closed losing trades to review yet.")

        suggestions = [
            "Define max risk per trade before market open.",
            "Avoid adding to losers without a written plan.",
            "Review largest winner setup and replicate conditions.",
            "Use hard stop-loss on every new paper position.",
            "Limit overlapping correlated sector bets.",
        ]
        conf = min(95, max(35, int(50 + wr * 0.3 + (10 if net > 0 else -10))))
        return {
            "summary": (
                f"Period P&L ₹{overview.get('todays_realized_pnl', 0)} realized "
                f"({overview.get('trades_executed', 0)} closed). "
                f"Win rate {wr}%, net ₹{net}."
            ),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "mistakes": mistakes,
            "suggestions": suggestions[:5],
            "risk_observations": [
                f"Exposure ₹{risk.get('exposure', 0)}; concentration {risk.get('capital_concentration', 0)}%.",
                f"Largest position risk ~{risk.get('risk_pct', 0)}% of starting capital.",
            ],
            "confidence_score": conf,
            "recommendations": suggestions[:5],
            "source": "heuristic",
        }

    def _get_journal(self, account_id: int, journal_date: str) -> dict[str, Any]:
        # Normalize to YYYY-MM-DD if range label has more text
        m = re.match(r"(\d{4}-\d{2}-\d{2})", journal_date or "")
        jdate = m.group(1) if m else date.today().isoformat()
        row = self.db.scalar(
            select(PaperDailyJournal).where(
                PaperDailyJournal.account_id == account_id,
                PaperDailyJournal.journal_date == jdate,
            )
        )
        if not row:
            return {
                "journal_date": jdate,
                "observations": "",
                "mistakes": "",
                "lessons": "",
                "tomorrow_plan": "",
                "updated_at": None,
            }
        return {
            "journal_date": row.journal_date,
            "observations": row.observations or "",
            "mistakes": row.mistakes or "",
            "lessons": row.lessons or "",
            "tomorrow_plan": row.tomorrow_plan or "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def save_journal(
        self,
        journal_date: str | None = None,
        observations: str | None = None,
        mistakes: str | None = None,
        lessons: str | None = None,
        tomorrow_plan: str | None = None,
    ) -> dict[str, Any]:
        account = self._account()
        jdate = journal_date or date.today().isoformat()
        m = re.match(r"(\d{4}-\d{2}-\d{2})", jdate)
        jdate = m.group(1) if m else date.today().isoformat()
        row = self.db.scalar(
            select(PaperDailyJournal).where(
                PaperDailyJournal.account_id == account.id,
                PaperDailyJournal.journal_date == jdate,
            )
        )
        if not row:
            row = PaperDailyJournal(account_id=account.id, journal_date=jdate)
            self.db.add(row)
        if observations is not None:
            row.observations = observations
        if mistakes is not None:
            row.mistakes = mistakes
        if lessons is not None:
            row.lessons = lessons
        if tomorrow_plan is not None:
            row.tomorrow_plan = tomorrow_plan
        row.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(row)
        return self._get_journal(account.id, jdate)
