"""
Gap Replay Engine
-----------------
On startup, fetches 1-minute candles for the offline gap period and
replays them to fill missed limit orders and trigger missed exits.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Dict

from sqlalchemy.orm import Session

from app.core.server_state import read_last_shutdown, write_startup_time
from app.models.paper_trading import (
    PaperOrder,
    PaperPosition,
    PaperTradingAccount,
    PaperTradeHistory,
    PaperTransaction,
)
from app.services.fyers_service import FyersService
from app.schemas import AnalysisMode
from app.core.log_manager import trading_logger as logger


MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MIN = 30


def _is_market_hours(dt: datetime) -> bool:
    """Return True if the datetime (aware) falls within NSE market hours in IST."""
    try:
        from zoneinfo import ZoneInfo
        ist = ZoneInfo("Asia/Kolkata")
    except Exception:
        from datetime import timezone, timedelta
        ist = timezone(timedelta(hours=5, minutes=30))
    local = dt.astimezone(ist)
    t = local.time()
    from datetime import time
    return time(MARKET_OPEN_HOUR, MARKET_OPEN_MIN) <= t <= time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MIN)


def run_gap_replay(db: Session, fyers_service: FyersService) -> Dict:
    summary: Dict = {
        "gap_start": None,
        "gap_end": None,
        "orders_filled": [],
        "positions_exited": [],
        "warnings": [],
        "skipped_reason": None,
    }

    last_shutdown = read_last_shutdown()
    now = datetime.now(timezone.utc)

    if last_shutdown is None:
        summary["skipped_reason"] = "First run — no previous shutdown recorded."
        logger.info("[GAP_REPLAY] First run, skipping replay.")
        write_startup_time()
        return summary

    gap_minutes = (now - last_shutdown).total_seconds() / 60.0
    if gap_minutes < 2:
        summary["skipped_reason"] = "Gap too small (< 2 minutes), skipping."
        write_startup_time()
        return summary

    gap_start = last_shutdown
    gap_end = now
    summary["gap_start"] = gap_start.isoformat()
    summary["gap_end"] = gap_end.isoformat()

    logger.info("[GAP_REPLAY] Gap detected: %s → %s (%s minutes)", gap_start.isoformat(), gap_end.isoformat(), int(gap_minutes))

    try:
        accounts = list(db.query(PaperTradingAccount).all())
    except Exception as e:
        logger.error("[GAP_REPLAY] Failed to load accounts: %s", e)
        summary["warnings"].append(f"Failed to load accounts: {e}")
        write_startup_time()
        return summary

    for account in accounts:
        open_positions = list(db.query(PaperPosition).filter(PaperPosition.account_id == account.id, PaperPosition.status == "OPEN").all())
        pending_orders = list(db.query(PaperOrder).filter(PaperOrder.account_id == account.id, PaperOrder.status == "PENDING").all())

        if not open_positions and not pending_orders:
            continue

        symbols = {p.symbol for p in open_positions} | {o.symbol for o in pending_orders}

        logger.info("[GAP_REPLAY] Account %s: positions=%s pending_orders=%s symbols=%s", account.id, len(open_positions), len(pending_orders), list(symbols))

        for symbol in symbols:
            try:
                # Determine lookback days — fetch at least 1-2 days so FYERS history returns intraday candles
                lookback_days = max(1, ceil(gap_minutes / (60 * 24)) + 1)
                candles = fyers_service.fetch_ohlcv(symbol, AnalysisMode.intraday, "1m", lookback_days, allow_mock=False)

                if not candles:
                    warning = f"{symbol}: No candle data for gap period — verify manually"
                    summary["warnings"].append(warning)
                    logger.warning("[GAP_REPLAY] %s", warning)
                    continue

                # Filter candles to gap period and market hours
                market_candles = [c for c in candles if c.timestamp >= gap_start and c.timestamp <= gap_end and _is_market_hours(c.timestamp)]
                market_candles.sort(key=lambda c: c.timestamp)

                if not market_candles:
                    logger.info("[GAP_REPLAY] %s: No market-hour candles inside gap", symbol)
                    summary["warnings"].append(f"{symbol}: Gap was outside market hours — no replay needed")
                    continue

                # Replay pending LIMIT BUY orders
                for order in [o for o in pending_orders if o.symbol == symbol and o.side == "BUY"]:
                    for candle in market_candles:
                        candle_low = float(candle.low)
                        candle_time = candle.timestamp
                        if order.order_price is None:
                            continue
                        if candle_low <= float(order.order_price):
                            fill_price = float(order.order_price)
                            cost = fill_price * int(order.qty)
                            if account.cash_balance >= cost:
                                order.status = "FILLED"
                                order.filled_price = fill_price
                                order.filled_at = candle_time

                                existing_pos = db.query(PaperPosition).filter(PaperPosition.account_id == account.id, PaperPosition.symbol == symbol, PaperPosition.status == "OPEN").first()
                                if existing_pos:
                                    total_cost = (existing_pos.avg_entry_price * existing_pos.qty) + cost
                                    existing_pos.qty = existing_pos.qty + order.qty
                                    existing_pos.avg_entry_price = total_cost / existing_pos.qty
                                    existing_pos.stop_loss = order.stop_loss
                                    existing_pos.target = order.target
                                    existing_pos.updated_at = candle_time
                                else:
                                    new_pos = PaperPosition(
                                        account_id=account.id,
                                        status="OPEN",
                                        symbol=symbol,
                                        qty=order.qty,
                                        avg_entry_price=fill_price,
                                        current_price=fill_price,
                                        stop_loss=order.stop_loss,
                                        target=order.target,
                                        notes=order.notes,
                                    )
                                    # set created_at/updated_at to candle_time if possible
                                    try:
                                        new_pos.created_at = candle_time
                                        new_pos.updated_at = candle_time
                                    except Exception:
                                        pass
                                    db.add(new_pos)

                                account.cash_balance = float(account.cash_balance) - float(cost)

                                # record transaction for BUY
                                try:
                                    tx = PaperTransaction(
                                        account_id=int(account.id),
                                        timestamp=candle_time,
                                        symbol=symbol,
                                        action="BUY",
                                        qty=int(order.qty),
                                        price=float(fill_price),
                                        amount=-float(fill_price) * int(order.qty),
                                        balance_after=float(account.cash_balance),
                                    )
                                    db.add(tx)
                                except Exception:
                                    logger.exception("[GAP_REPLAY] Failed to add BUY transaction for %s", symbol)

                                msg = f"OFFLINE_FILL | symbol={symbol} | side=BUY | qty={order.qty} | fill_price={fill_price} | candle_time={candle_time.isoformat()}"
                                summary["orders_filled"].append(msg)
                                logger.info("[GAP_REPLAY] %s", msg)
                                # refresh open_positions list
                                open_positions = list(db.query(PaperPosition).filter(PaperPosition.account_id == account.id, PaperPosition.status == "OPEN").all())
                            else:
                                order.status = "REJECTED"
                                logger.warning("[GAP_REPLAY] %s: Offline fill rejected — insufficient funds", symbol)
                            break

                # Replay open positions for target/stop hits
                for pos in [p for p in open_positions if p.symbol == symbol]:
                    target_hit = None
                    stop_hit = None
                    for candle in market_candles:
                        c_high = float(candle.high)
                        c_low = float(candle.low)
                        c_time = candle.timestamp
                        if pos.target and target_hit is None and c_high >= float(pos.target):
                            target_hit = (c_time, float(pos.target))
                        if pos.stop_loss and stop_hit is None and c_low <= float(pos.stop_loss):
                            stop_hit = (c_time, float(pos.stop_loss))

                    exit_time = None
                    exit_price = None
                    exit_reason = None

                    if target_hit and stop_hit:
                        if target_hit[0] <= stop_hit[0]:
                            exit_time, exit_price, exit_reason = target_hit[0], target_hit[1], "TARGET_HIT"
                        else:
                            exit_time, exit_price, exit_reason = stop_hit[0], stop_hit[1], "STOPLOSS_HIT"
                    elif target_hit:
                        exit_time, exit_price, exit_reason = target_hit[0], target_hit[1], "TARGET_HIT"
                    elif stop_hit:
                        exit_time, exit_price, exit_reason = stop_hit[0], stop_hit[1], "STOPLOSS_HIT"

                    if exit_price is not None:
                        pnl = (exit_price - pos.avg_entry_price) * pos.qty
                        # create a filled SELL order representing the exit
                        try:
                            exit_order = PaperOrder(
                                account_id=account.id,
                                symbol=pos.symbol,
                                side="SELL",
                                order_type="MARKET",
                                product_type="CNC",
                                qty=pos.qty,
                                order_price=exit_price,
                                status="FILLED",
                                notes=f"Offline auto-exit: {exit_reason}",
                                filled_price=exit_price,
                                filled_at=exit_time,
                            )
                            db.add(exit_order)
                        except Exception:
                            logger.exception("[GAP_REPLAY] Failed to add exit order for %s", pos.symbol)

                        # create trade history
                        try:
                            trade = PaperTradeHistory(
                                account_id=account.id,
                                symbol=pos.symbol,
                                qty=pos.qty,
                                entry_price=pos.avg_entry_price,
                                exit_price=exit_price,
                                pnl=pnl,
                                pnl_percent=((exit_price - pos.avg_entry_price) / pos.avg_entry_price * 100) if pos.avg_entry_price else 0.0,
                                notes=pos.notes,
                                source_signal=pos.source_signal,
                                source_score=pos.source_score,
                                source_confidence=pos.source_confidence,
                                opened_at=pos.created_at,
                                closed_at=exit_time,
                                exit_reason=exit_reason,
                            )
                            db.add(trade)
                        except Exception:
                            logger.exception("[GAP_REPLAY] Failed to add trade history for %s", pos.symbol)

                        # credit account and delete position
                        try:
                            account.cash_balance = float(account.cash_balance) + float(exit_price) * int(pos.qty)
                        except Exception:
                            logger.exception("[GAP_REPLAY] Failed to credit account for %s", pos.symbol)

                        # transaction record
                        try:
                            tx = PaperTransaction(
                                account_id=int(account.id),
                                timestamp=exit_time,
                                symbol=pos.symbol,
                                action="AUTO_EXIT",
                                qty=int(pos.qty),
                                price=float(exit_price),
                                amount=float(exit_price) * int(pos.qty),
                                balance_after=float(account.cash_balance),
                            )
                            db.add(tx)
                        except Exception:
                            logger.exception("[GAP_REPLAY] Failed to add AUTO_EXIT transaction for %s", pos.symbol)

                        try:
                            db.delete(pos)
                        except Exception:
                            logger.exception("[GAP_REPLAY] Failed to delete position %s after offline exit", pos.symbol)

                        msg = f"OFFLINE_EXIT | symbol={pos.symbol} | exit_price={exit_price} | reason={exit_reason} | pnl={round(pnl,2)} | hit_at={exit_time.isoformat()}"
                        summary["positions_exited"].append(msg)
                        logger.info("[GAP_REPLAY] %s", msg)

            except Exception as e:
                warning = f"{symbol}: Gap replay failed — {e}"
                summary["warnings"].append(warning)
                logger.error("[GAP_REPLAY] ERROR for %s: %s", symbol, e)

    try:
        db.commit()
        logger.info("[GAP_REPLAY] Committed. Filled=%s Exited=%s Warnings=%s", len(summary["orders_filled"]), len(summary["positions_exited"]), len(summary["warnings"]))
    except Exception as e:
        db.rollback()
        logger.error("[GAP_REPLAY] Commit failed: %s", e)
        summary["warnings"].append(f"Commit failed: {e}")

    write_startup_time()
    return summary
