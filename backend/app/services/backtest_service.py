from __future__ import annotations

import math
import logging
import statistics
from abc import ABC, abstractmethod
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD

from ..schemas import AnalysisMode, BacktestResult, OHLCVPoint
from ..utils import get_logger

logger = get_logger("app.backtest")

# ---------------------------------------------------------------------------
# Transaction Cost Configurations
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Execution Model Constants & Normalization
# ---------------------------------------------------------------------------
VALID_EXECUTION_MODELS: frozenset[str] = frozenset({"REALISTIC", "LEGACY"})
_DEFAULT_EXECUTION_MODEL: str = "REALISTIC"


def normalize_execution_model(value: str | None) -> str:
    """Normalize an execution-model string to its canonical form.

    * Case-insensitive matching (``legacy`` → ``LEGACY``).
    * Leading / trailing whitespace is stripped.
    * ``None`` and unrecognised values normalise to ``REALISTIC``
      and emit a **warning**.
    """
    if value is None:
        return _DEFAULT_EXECUTION_MODEL
    cleaned = value.strip()
    if not cleaned:
        return _DEFAULT_EXECUTION_MODEL
    upper = cleaned.upper()
    if upper in VALID_EXECUTION_MODELS:
        return upper
    logger.warning(
        "Unknown execution_model %r – normalising to %s.  Valid values: %s",
        value, _DEFAULT_EXECUTION_MODEL, sorted(VALID_EXECUTION_MODELS),
    )
    return _DEFAULT_EXECUTION_MODEL


COST_SCENARIOS = {
    "LOW_COST": {
        "brokerage_rate": 0.0001,      # 0.01%
        "brokerage_flat": 0.0,
        "stt_rate_buy": 0.001,         # 0.1% for swing/delivery
        "stt_rate_sell": 0.001,        # 0.1% for swing/delivery
        "exc_trans_rate": 0.0000325,   # 0.00325% NSE
        "sebi_rate": 0.000001,         # 0.0001%
        "stamp_duty_rate": 0.00015,     # 0.015% buy only
        "dp_charge": 13.5,
        "gst_rate": 0.18,              # 18% on (brokerage + exchange fee + SEBI fee)
        "slippage_rate": 0.0002,       # 0.02% slippage
    },
    "BASE_COST": {
        "brokerage_rate": 0.0005,      # 0.05%
        "brokerage_flat": 20.0,        # Flat 20 cap (standard discount broker)
        "stt_rate_buy": 0.001,
        "stt_rate_sell": 0.001,
        "exc_trans_rate": 0.0000345,
        "sebi_rate": 0.000001,
        "stamp_duty_rate": 0.00015,
        "dp_charge": 13.5,
        "gst_rate": 0.18,
        "slippage_rate": 0.0005,       # 0.05% slippage
    },
    "STRESS_COST": {
        "brokerage_rate": 0.0010,      # 0.1% full-service rate
        "brokerage_flat": 0.0,
        "stt_rate_buy": 0.001,
        "stt_rate_sell": 0.001,
        "exc_trans_rate": 0.0000345,
        "sebi_rate": 0.000001,
        "stamp_duty_rate": 0.00015,
        "dp_charge": 15.0,
        "gst_rate": 0.18,
        "slippage_rate": 0.0015,       # 0.15% slippage
    }
}

def calculate_transaction_costs(
    side: str,
    price: float,
    quantity: int,
    mode: AnalysisMode,
    config: dict
) -> dict[str, float]:
    """
    Calculate realistic Indian NSE equity transaction costs.
    STT and stamp duty are adjusted for intraday vs swing/delivery mode.
    """
    turnover = price * quantity
    if turnover <= 0 or quantity <= 0:
        return {
            "brokerage": 0.0,
            "stt": 0.0,
            "etc": 0.0,
            "sebi": 0.0,
            "stamp_duty": 0.0,
            "gst": 0.0,
            "dp_charge": 0.0,
            "total": 0.0,
        }

    # Brokerage
    brokerage = config["brokerage_rate"] * turnover
    if config["brokerage_flat"] > 0:
        brokerage = min(brokerage, config["brokerage_flat"])

    is_intraday = (mode == AnalysisMode.intraday)

    # Securities Transaction Tax (STT)
    # delivery/swing: 0.1% on buy & sell; intraday: 0.025% on sell only
    if is_intraday:
        stt = 0.00025 * turnover if side == "SELL" else 0.0
    else:
        stt = config["stt_rate_sell"] * turnover if side == "SELL" else config["stt_rate_buy"] * turnover

    # Exchange transaction charges
    etc = config["exc_trans_rate"] * turnover

    # SEBI charges
    sebi = config["sebi_rate"] * turnover

    # Stamp duty (0.015% delivery buy only, 0.003% intraday buy only)
    if side == "BUY":
        stamp_duty = 0.00003 * turnover if is_intraday else config["stamp_duty_rate"] * turnover
    else:
        stamp_duty = 0.0

    # GST (18% on brokerage, etc, and sebi)
    gst = config["gst_rate"] * (brokerage + etc + sebi)

    # DP charges (only on sell side for delivery/swing, standard flat ₹13.5 per company/day)
    dp = 0.0
    if side == "SELL" and not is_intraday:
        dp = config["dp_charge"]

    total = brokerage + stt + etc + sebi + stamp_duty + gst + dp

    return {
        "brokerage": brokerage,
        "stt": stt,
        "etc": etc,
        "sebi": sebi,
        "stamp_duty": stamp_duty,
        "gst": gst,
        "dp_charge": dp,
        "total": total,
    }

def calculate_cagr(
    initial_equity: float,
    ending_equity: float,
    annualization_days: int,
    trading_days_per_year: int = 252,
) -> float | None:
    if initial_equity <= 0 or ending_equity <= 0 or annualization_days <= 1:
        return None
    try:
        val = ((ending_equity / initial_equity) ** (trading_days_per_year / annualization_days) - 1) * 100
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Position Sizing Model
# ---------------------------------------------------------------------------
class PositionSizer(ABC):
    @abstractmethod
    def calculate_shares(self, equity: float, price: float, mode: AnalysisMode) -> int:
        """
        Calculate number of shares to purchase based on equity and price.
        """
        pass

class PercentEquityPositionSizer(PositionSizer):
    def __init__(self, percent: float = 20.0) -> None:
        self.percent = percent

    def calculate_shares(self, equity: float, price: float, mode: AnalysisMode) -> int:
        if equity <= 0 or price <= 0:
            return 0
        allocated_capital = equity * (self.percent / 100.0)
        return int(allocated_capital // price)


# ---------------------------------------------------------------------------
# Backtest Service
# ---------------------------------------------------------------------------
class BacktestService:
    def run(
        self,
        symbol: str,
        mode: AnalysisMode,
        candles: list[OHLCVPoint],
        cost_scenario: str = "BASE_COST",
        position_sizing_pct: float = 20.0,
        execution_model: str = "REALISTIC",
        composite_uses_realistic: bool = True,
        skip_on_missing_next_bar: bool = False,
        feat008_enabled: bool = True,
        stop_loss_pct: float | None = None,
        target_pct: float | None = None,
    ) -> BacktestResult:
        execution_model = normalize_execution_model(execution_model)
        strategy_name = "ema_rsi_volume" if mode == AnalysisMode.intraday else "sma_rsi_macd"
        if len(candles) < 35:
            return self._empty_result(mode, strategy_name, cost_scenario, position_sizing_pct, feat008_enabled)

        frame = pd.DataFrame(
            {
                "timestamp": [candle.timestamp for candle in candles],
                "open": [candle.open for candle in candles],
                "high": [candle.high for candle in candles],
                "low": [candle.low for candle in candles],
                "close": [candle.close for candle in candles],
                "volume": [candle.volume for candle in candles],
            }
        )
        
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        frame = frame.ffill().bfill()
        
        fast_window = 9 if mode == AnalysisMode.intraday else 20
        slow_window = 20 if mode == AnalysisMode.intraday else 50
        frame["ema_fast"] = EMAIndicator(close=frame["close"], window=fast_window).ema_indicator()
        frame["ema_slow"] = EMAIndicator(close=frame["close"], window=slow_window).ema_indicator()
        frame["rsi"] = RSIIndicator(close=frame["close"], window=14).rsi()
        macd = MACD(close=frame["close"], window_slow=26, window_fast=12, window_sign=9)
        frame["macd"] = macd.macd()
        frame["macd_signal"] = macd.macd_signal()
        frame["avg_volume"] = frame["volume"].rolling(20).mean()

        # Compute unique trading days count for annualization using dt.normalize()
        annualization_days = frame["timestamp"].dt.normalize().nunique()

        # ===================================================================
        # PASS 1: Old/Champion simulation (same-day close, 100% deployment, zero cost)
        # ===================================================================
        gross_equity = 100000.0
        gross_peak_equity = gross_equity
        gross_max_drawdown = 0.0
        gross_position_entry = None
        gross_position_entry_date = None
        gross_trades: list[dict] = []

        for index, row in frame.iterrows():
            if index < slow_window or pd.isna(row["ema_slow"]) or pd.isna(row["rsi"]) or pd.isna(row["macd_signal"]):
                continue

            bullish_entry = bool(
                row["close"] > row["ema_fast"]
                and row["ema_fast"] > row["ema_slow"]
                and row["macd"] > row["macd_signal"]
                and row["rsi"] >= 50
                and row["volume"] >= max(row["avg_volume"] or 0, 1) * 0.8
            )
            exit_signal = bool(
                row["close"] < row["ema_fast"]
                or row["macd"] < row["macd_signal"]
                or row["rsi"] < 45
            )

            if gross_position_entry is None:
                if bullish_entry:
                    gross_position_entry = float(row["close"])
                    gross_position_entry_date = row["timestamp"]
            else:
                if exit_signal:
                    exit_price = float(row["close"])
                    trade_return = ((exit_price - gross_position_entry) / gross_position_entry) * 100
                    gross_trades.append({
                        "entry_date": str(gross_position_entry_date.date()) if gross_position_entry_date is not None else str(row["timestamp"].date()),
                        "exit_date": str(row["timestamp"].date()),
                        "entry_price": round(gross_position_entry, 2),
                        "exit_price": round(exit_price, 2),
                        "pnl_percent": round(trade_return, 2),
                    })
                    gross_equity *= 1 + (trade_return / 100)
                    gross_position_entry = None
                    gross_position_entry_date = None

            # Calculate mark-to-market equity for gross drawdown tracking (standardized methodology)
            if gross_position_entry is not None:
                gross_mtm = gross_equity * (float(row["close"]) / gross_position_entry)
            else:
                gross_mtm = gross_equity

            gross_peak_equity = max(gross_peak_equity, gross_mtm)
            gross_max_drawdown = max(gross_max_drawdown, ((gross_peak_equity - gross_mtm) / gross_peak_equity) * 100)

        if gross_position_entry is not None:
            final_close = float(frame["close"].iloc[-1])
            trade_return = ((final_close - gross_position_entry) / gross_position_entry) * 100
            gross_trades.append({
                "entry_date": str(gross_position_entry_date.date()) if gross_position_entry_date is not None else str(frame["timestamp"].iloc[-1].date()),
                "exit_date": str(frame["timestamp"].iloc[-1].date()),
                "entry_price": round(gross_position_entry, 2),
                "exit_price": round(final_close, 2),
                "pnl_percent": round(trade_return, 2),
            })
            gross_equity *= 1 + (trade_return / 100)
            gross_peak_equity = max(gross_peak_equity, gross_equity)
            gross_max_drawdown = max(gross_max_drawdown, ((gross_peak_equity - gross_equity) / gross_peak_equity) * 100)

        # Compute Pass 1 gross metrics
        gross_total_return = round(((gross_equity - 100000.0) / 100000.0) * 100, 2)
        gross_trade_count = len(gross_trades)
        gross_wins = [t["pnl_percent"] for t in gross_trades if t["pnl_percent"] > 0]
        gross_losses = [abs(t["pnl_percent"]) for t in gross_trades if t["pnl_percent"] < 0]
        gross_win_rate = round((len(gross_wins) / gross_trade_count) * 100, 2) if gross_trade_count else 0.0
        gross_profit_factor = round((sum(gross_wins) / sum(gross_losses)), 2) if gross_losses else round(sum(gross_wins), 2) if gross_wins else 0.0
        
        gross_cagr_val = calculate_cagr(100000.0, gross_equity, annualization_days)
        gross_cagr = round(gross_cagr_val, 2) if gross_cagr_val is not None else None
        
        gross_sharpe = 0.0
        try:
            if gross_trade_count > 1:
                mean_ret = statistics.mean([t["pnl_percent"] for t in gross_trades])
                stdev = statistics.stdev([t["pnl_percent"] for t in gross_trades])
                if stdev > 0:
                    gross_sharpe = round((mean_ret / stdev) * math.sqrt(max(1, gross_trade_count)), 3)
        except Exception:
            gross_sharpe = 0.0


        # ===================================================================
        # PASS 2: Challenger/Realistic simulation (next-day open, costs, sizing)
        # ===================================================================
        net_cash = 100000.0
        net_shares = 0
        net_position_entry_price = 0.0
        net_position_entry_date = None
        net_position_entry_fee = 0.0
        net_trades: list[dict] = []
        net_equity_curve: list[dict[str, float | str]] = []
        net_peak_equity = net_cash
        net_max_drawdown = 0.0
        
        total_costs = 0.0
        total_slippage = 0.0
        
        cost_cfg = COST_SCENARIOS.get(cost_scenario, COST_SCENARIOS["BASE_COST"])
        sizer = PercentEquityPositionSizer(percent=position_sizing_pct)
        n_candles = len(frame)

        # Pending order state variables
        pending_buy = False
        pending_exit = False
        trades_skipped = 0
        trades_skipped_error = 0

        # FEAT-008 Batch 3 per-trade audit tracking
        net_position_raw_entry = 0.0
        entry_signal_timestamp = None
        entry_signal_close = None
        exit_signal_timestamp = None
        exit_signal_close = None
        trade_counter = 0

        for i in range(n_candles):
            row = frame.iloc[i]
            
            # Warmed up check
            if i < slow_window or pd.isna(row["ema_slow"]) or pd.isna(row["rsi"]) or pd.isna(row["macd_signal"]):
                label = row["timestamp"].isoformat() if mode == AnalysisMode.intraday else str(row["timestamp"].date())
                net_equity_curve.append({"label": label, "equity": round(net_cash, 2)})
                continue

            # 1. Execute pending orders at the START of iteration i using row["open"]
            if pending_buy and net_shares == 0:
                trade_idx = len(net_trades)
                try:
                    entry_price = float(row["open"])
                    entry_date = row["timestamp"]

                    # Apply slippage
                    execution_buy_price = entry_price * (1 + cost_cfg["slippage_rate"])
                    qty = sizer.calculate_shares(net_cash, execution_buy_price, mode)

                    # TEMPORARY_ASSUMPTION: Assume delivery charges (swing mode) at entry since we cannot prove same-session exit yet.
                    if qty > 0:
                        charges_dict = calculate_transaction_costs("BUY", execution_buy_price, qty, AnalysisMode.swing, cost_cfg)
                        entry_fee = charges_dict["total"]

                        # Adjust quantity to fit in cash including fees
                        while qty > 0 and (qty * execution_buy_price + entry_fee) > net_cash:
                            qty -= 1
                            charges_dict = calculate_transaction_costs("BUY", execution_buy_price, qty, AnalysisMode.swing, cost_cfg)
                            entry_fee = charges_dict["total"]

                        if qty > 0:
                            net_cash -= (qty * execution_buy_price + entry_fee)
                            net_shares = qty
                            net_position_entry_price = execution_buy_price
                            net_position_entry_date = entry_date
                            net_position_entry_fee = entry_fee
                            net_position_raw_entry = entry_price
                            total_costs += entry_fee
                            total_slippage += (execution_buy_price - entry_price) * qty
                            logger.info(
                                "REALISTIC ENTRY | symbol=%s | qty=%d | raw_price=%.2f | exec_price=%.2f | cost=%.2f | date=%s",
                                symbol, qty, entry_price, execution_buy_price, entry_fee, entry_date.date()
                            )
                except Exception as exc:
                    trades_skipped_error += 1
                    logger.error(
                        "TRADE FAULT | Entry execution failed | symbol=%s | trade_index=%d | date=%s | %s: %s",
                        symbol, trade_idx, row["timestamp"], type(exc).__name__, exc,
                    )
                finally:
                    pending_buy = False

            elif pending_exit and net_shares > 0:
                trade_idx = len(net_trades)
                try:
                    exit_price = float(row["open"])
                    exit_date = row["timestamp"]

                    # Apply slippage
                    execution_sell_price = exit_price * (1 - cost_cfg["slippage_rate"])

                    # TEMPORARY_ASSUMPTION: We can only use intraday cost model if we prove same-session open + close.
                    is_same_session = (net_position_entry_date.date() == exit_date.date())
                    actual_mode = AnalysisMode.intraday if (mode == AnalysisMode.intraday and is_same_session) else AnalysisMode.swing

                    # Retroactively adjust entry fee if same-session is proven
                    if is_same_session and mode == AnalysisMode.intraday:
                        entry_charges_retro = calculate_transaction_costs("BUY", net_position_entry_price, net_shares, AnalysisMode.intraday, cost_cfg)
                        retro_entry_fee = entry_charges_retro["total"]
                        entry_charges_orig = calculate_transaction_costs("BUY", net_position_entry_price, net_shares, AnalysisMode.swing, cost_cfg)
                        orig_entry_fee = entry_charges_orig["total"]

                        cost_difference = orig_entry_fee - retro_entry_fee
                        if cost_difference > 0:
                            net_cash += cost_difference
                            total_costs -= cost_difference
                            net_position_entry_fee = retro_entry_fee
                            logger.info("RETROACTIVE COST ADJUSTMENT | Same-session trade. Refunded delivery fee difference: %.2f", cost_difference)

                    charges_dict = calculate_transaction_costs("SELL", execution_sell_price, net_shares, actual_mode, cost_cfg)
                    exit_fee = charges_dict["total"]

                    exit_value = (net_shares * execution_sell_price) - exit_fee
                    net_cash += exit_value

                    trade_cost_basis = (net_shares * net_position_entry_price) + net_position_entry_fee
                    trade_net_pnl = exit_value - trade_cost_basis
                    trade_return = (trade_net_pnl / trade_cost_basis * 100) if trade_cost_basis > 0 else 0.0

                    trade_counter += 1
                    legacy_pnl = round(((exit_signal_close - entry_signal_close) / entry_signal_close) * 100, 2) if entry_signal_close is not None and exit_signal_close is not None else None
                    net_trades.append({
                        "trade_id": trade_counter,
                        "entry_candle_signal": str(entry_signal_timestamp.date()) if entry_signal_timestamp is not None else None,
                        "entry_fill_candle": str(entry_date.date()) if entry_date is not None else None,
                        "raw_entry": round(net_position_raw_entry, 2),
                        "effective_entry": round(net_position_entry_price, 2),
                        "exit_fill_candle": str(exit_date.date()) if exit_date is not None else None,
                        "raw_exit": round(exit_price, 2),
                        "effective_exit": round(execution_sell_price, 2),
                        "legacy_pnl_pct": legacy_pnl,
                        "fill_skipped_reason": None,
                        "entry_date": str(net_position_entry_date.date()) if net_position_entry_date else str(exit_date.date()),
                        "exit_date": str(exit_date.date()),
                        "entry_price": round(net_position_entry_price, 2),
                        "exit_price": round(execution_sell_price, 2),
                        "pnl_percent": round(trade_return, 2),
                    })
                    exit_signal_timestamp = None
                    exit_signal_close = None

                    total_costs += exit_fee
                    total_slippage += (exit_price - execution_sell_price) * net_shares
                    logger.info(
                        "REALISTIC EXIT | symbol=%s | qty=%d | raw_price=%.2f | exec_price=%.2f | cost=%.2f | pnl=%.2f%% | date=%s",
                        symbol, net_shares, exit_price, execution_sell_price, exit_fee, trade_return, exit_date.date()
                    )
                except Exception as exc:
                    trades_skipped_error += 1
                    logger.error(
                        "TRADE FAULT | Exit execution failed | symbol=%s | trade_index=%d | date=%s | %s: %s",
                        symbol, trade_idx, row["timestamp"], type(exc).__name__, exc,
                    )
                finally:
                    net_shares = 0
                    net_position_entry_price = 0.0
                    net_position_entry_date = None
                    net_position_entry_fee = 0.0
                    pending_exit = False

            # FEAT-008 — Intrabar stop-loss / target check (conservative ordering)
            # FEAT-008 Batch 2 — Gap execution: overnight gap-down / gap-up fills at open[T+1]
            intrabar_enabled = stop_loss_pct is not None and target_pct is not None
            if intrabar_enabled and net_shares > 0:
                trade_idx = len(net_trades)
                try:
                    stop_price = net_position_entry_price * (1 - abs(stop_loss_pct) / 100.0)
                    target_price = net_position_entry_price * (1 + abs(target_pct) / 100.0)

                    candle_open = float(row["open"])
                    gap_stop_hit = candle_open <= stop_price
                    gap_target_hit = candle_open >= target_price

                    if gap_stop_hit:
                        exit_price = candle_open
                        exit_reason = "stop_loss"
                    elif gap_target_hit:
                        exit_price = candle_open
                        exit_reason = "target"
                    else:
                        candle_low = float(row["low"])
                        candle_high = float(row["high"])
                        stop_hit = candle_low <= stop_price
                        target_hit = candle_high >= target_price

                        if stop_hit or target_hit:
                            if stop_hit and target_hit:
                                exit_price = stop_price
                                exit_reason = "stop_loss"
                            elif stop_hit:
                                exit_price = stop_price
                                exit_reason = "stop_loss"
                            else:
                                exit_price = target_price
                                exit_reason = "target"
                        else:
                            exit_price = None

                    if exit_price is not None:
                        exit_date = row["timestamp"]
                        execution_sell_price = exit_price * (1 - cost_cfg["slippage_rate"])

                        is_same_session = (net_position_entry_date.date() == exit_date.date())
                        actual_mode = AnalysisMode.intraday if (mode == AnalysisMode.intraday and is_same_session) else AnalysisMode.swing

                        if is_same_session and mode == AnalysisMode.intraday:
                            entry_charges_retro = calculate_transaction_costs("BUY", net_position_entry_price, net_shares, AnalysisMode.intraday, cost_cfg)
                            retro_entry_fee = entry_charges_retro["total"]
                            entry_charges_orig = calculate_transaction_costs("BUY", net_position_entry_price, net_shares, AnalysisMode.swing, cost_cfg)
                            orig_entry_fee = entry_charges_orig["total"]
                            cost_difference = orig_entry_fee - retro_entry_fee
                            if cost_difference > 0:
                                net_cash += cost_difference
                                total_costs -= cost_difference
                                net_position_entry_fee = retro_entry_fee

                        charges_dict = calculate_transaction_costs("SELL", execution_sell_price, net_shares, actual_mode, cost_cfg)
                        exit_fee = charges_dict["total"]

                        exit_value = (net_shares * execution_sell_price) - exit_fee
                        net_cash += exit_value

                        trade_cost_basis = (net_shares * net_position_entry_price) + net_position_entry_fee
                        trade_net_pnl = exit_value - trade_cost_basis
                        trade_return = (trade_net_pnl / trade_cost_basis * 100) if trade_cost_basis > 0 else 0.0

                        trade_counter += 1
                        net_trades.append({
                            "trade_id": trade_counter,
                            "entry_candle_signal": str(entry_signal_timestamp.date()) if entry_signal_timestamp is not None else None,
                            "entry_fill_candle": str(net_position_entry_date.date()) if net_position_entry_date else None,
                            "raw_entry": round(net_position_raw_entry, 2),
                            "effective_entry": round(net_position_entry_price, 2),
                            "exit_fill_candle": str(exit_date.date()) if exit_date is not None else None,
                            "raw_exit": round(exit_price, 2),
                            "effective_exit": round(execution_sell_price, 2),
                            "legacy_pnl_pct": None,
                            "fill_skipped_reason": None,
                            "entry_date": str(net_position_entry_date.date()) if net_position_entry_date else str(exit_date.date()),
                            "exit_date": str(exit_date.date()),
                            "entry_price": round(net_position_entry_price, 2),
                            "exit_price": round(execution_sell_price, 2),
                            "pnl_percent": round(trade_return, 2),
                            "exit_reason": exit_reason,
                        })
                        exit_signal_timestamp = None
                        exit_signal_close = None

                        total_costs += exit_fee
                        total_slippage += (exit_price - execution_sell_price) * net_shares
                        logger.info(
                            "%s %s | symbol=%s | qty=%d | exit_price=%.2f | exec_price=%.2f | pnl=%.2f%% | date=%s",
                            "GAP" if (gap_stop_hit or gap_target_hit) else "INTRABAR",
                            exit_reason.upper(), symbol, net_shares, exit_price, execution_sell_price, trade_return, exit_date.date()
                        )

                        net_shares = 0
                        net_position_entry_price = 0.0
                        net_position_entry_date = None
                        net_position_entry_fee = 0.0
                        pending_buy = False
                        pending_exit = False

                        net_peak_equity = max(net_peak_equity, net_cash)
                        net_max_drawdown = max(net_max_drawdown, ((net_peak_equity - net_cash) / net_peak_equity) * 100)
                        label = exit_date.isoformat() if mode == AnalysisMode.intraday else str(exit_date.date())
                        net_equity_curve.append({"label": label, "equity": round(net_cash, 2)})

                        continue
                except Exception as exc:
                    trades_skipped_error += 1
                    logger.error(
                        "TRADE FAULT | Intrabar exit execution failed | symbol=%s | trade_index=%d | date=%s | %s: %s",
                        symbol, trade_idx, row["timestamp"], type(exc).__name__, exc,
                    )
                    net_shares = 0
                    net_position_entry_price = 0.0
                    net_position_entry_date = None
                    net_position_entry_fee = 0.0
                    pending_buy = False
                    pending_exit = False

            # 2. Update mark-to-market and record equity curve for the current row i (at row close)
            current_value = net_cash
            if net_shares > 0:
                current_value += net_shares * float(row["close"])
            
            net_peak_equity = max(net_peak_equity, current_value)
            net_max_drawdown = max(net_max_drawdown, ((net_peak_equity - current_value) / net_peak_equity) * 100)
            label = row["timestamp"].isoformat() if mode == AnalysisMode.intraday else str(row["timestamp"].date())
            net_equity_curve.append({"label": label, "equity": round(current_value, 2)})

            # 3. Evaluate signals at the end of iteration i (using row close/indicators)
            bullish_entry = bool(
                row["close"] > row["ema_fast"]
                and row["ema_fast"] > row["ema_slow"]
                and row["macd"] > row["macd_signal"]
                and row["rsi"] >= 50
                and row["volume"] >= max(row["avg_volume"] or 0, 1) * 0.8
            )
            exit_signal = bool(
                row["close"] < row["ema_fast"]
                or row["macd"] < row["macd_signal"]
                or row["rsi"] < 45
            )

            if net_shares == 0:
                if bullish_entry:
                    pending_buy = True
                    pending_exit = False
                    entry_signal_timestamp = row["timestamp"]
                    entry_signal_close = float(row["close"])
            else:
                if exit_signal:
                    pending_exit = True
                    pending_buy = False
                    exit_signal_timestamp = row["timestamp"]
                    exit_signal_close = float(row["close"])

        if skip_on_missing_next_bar:
            # FEAT-008: When the next execution bar does not exist, skip
            # the trade instead of inventing a synthetic fill.  Pending
            # orders that cannot execute and open positions that cannot be
            # exited are both counted as skipped.
            if pending_buy and net_shares == 0:
                trades_skipped += 1
                logger.info(
                    "skip_on_missing_next_bar | Pending buy order at end of data with no next bar. "
                    "Entry skipped. | symbol=%s",
                    symbol,
                )
                pending_buy = False
            if net_shares > 0:
                trades_skipped += 1
                reason = "pending exit" if pending_exit else "open position"
                logger.info(
                    "skip_on_missing_next_bar | Position still open at end of data with no next bar. "
                    "%s skipped – no synthetic fill. | symbol=%s | qty=%d | last_close=%.2f",
                    reason, symbol, net_shares, float(frame.iloc[-1]["close"]),
                )
                net_shares = 0
                net_position_entry_fee = 0.0
                pending_exit = False
        elif net_shares > 0:
            # Backward-compatible: force-close at final candle close
            trade_idx = len(net_trades)
            try:
                final_row = frame.iloc[-1]
                exit_price = float(final_row["close"])
                exit_date = final_row["timestamp"]

                execution_sell_price = exit_price * (1 - cost_cfg["slippage_rate"])
                # Swing mode (delivery) used since held overnight
                charges_dict = calculate_transaction_costs("SELL", execution_sell_price, net_shares, AnalysisMode.swing, cost_cfg)
                exit_fee = charges_dict["total"]

                exit_value = (net_shares * execution_sell_price) - exit_fee
                net_cash += exit_value

                trade_cost_basis = (net_shares * net_position_entry_price) + net_position_entry_fee
                trade_net_pnl = exit_value - trade_cost_basis
                trade_return = (trade_net_pnl / trade_cost_basis * 100) if trade_cost_basis > 0 else 0.0

                trade_counter += 1
                net_trades.append({
                    "trade_id": trade_counter,
                    "entry_candle_signal": str(entry_signal_timestamp.date()) if entry_signal_timestamp is not None else None,
                    "entry_fill_candle": str(net_position_entry_date.date()) if net_position_entry_date else None,
                    "raw_entry": round(net_position_raw_entry, 2),
                    "effective_entry": round(net_position_entry_price, 2),
                    "exit_fill_candle": str(exit_date.date()) if exit_date is not None else None,
                    "raw_exit": round(exit_price, 2),
                    "effective_exit": round(execution_sell_price, 2),
                    "legacy_pnl_pct": None,
                    "fill_skipped_reason": "force_close_end_of_data",
                    "entry_date": str(net_position_entry_date.date()) if net_position_entry_date else str(exit_date.date()),
                    "exit_date": str(exit_date.date()),
                    "entry_price": round(net_position_entry_price, 2),
                    "exit_price": round(execution_sell_price, 2),
                    "pnl_percent": round(trade_return, 2),
                })
                exit_signal_timestamp = None
                exit_signal_close = None

                total_costs += exit_fee
                total_slippage += (exit_price - execution_sell_price) * net_shares
                logger.warning(
                    "TEMPORARY_ASSUMPTION | Position still open at end of backtest. Forcing exit at final candle close | symbol=%s | qty=%d | close=%.2f | date=%s",
                    symbol, net_shares, exit_price, exit_date.date()
                )
                net_shares = 0
                net_position_entry_fee = 0.0

                net_peak_equity = max(net_peak_equity, net_cash)
                net_max_drawdown = max(net_max_drawdown, ((net_peak_equity - net_cash) / net_peak_equity) * 100)
                if net_equity_curve:
                    label = exit_date.isoformat() if mode == AnalysisMode.intraday else str(exit_date.date())
                    net_equity_curve[-1] = {"label": label, "equity": round(net_cash, 2)}
            except Exception as exc:
                trades_skipped_error += 1
                logger.error(
                    "TRADE FAULT | Force-close execution failed | symbol=%s | trade_index=%d | date=%s | %s: %s",
                    symbol, trade_idx, final_row["timestamp"], type(exc).__name__, exc,
                )
                net_shares = 0
                net_position_entry_fee = 0.0

        # Compute Pass 2 net metrics
        total_return = round(((net_cash - 100000.0) / 100000.0) * 100, 2)
        trade_count = len(net_trades)
        wins = [t["pnl_percent"] for t in net_trades if t["pnl_percent"] > 0]
        losses = [abs(t["pnl_percent"]) for t in net_trades if t["pnl_percent"] < 0]
        win_rate = round((len(wins) / trade_count) * 100, 2) if trade_count else 0.0
        profit_factor = round((sum(wins) / sum(losses)), 2) if losses else round(sum(wins), 2) if wins else 0.0
        
        cagr_val = calculate_cagr(100000.0, net_cash, annualization_days)
        cagr = round(cagr_val, 2) if cagr_val is not None else None
        cagr_warning = "INSUFFICIENT_PERIOD_FOR_CAGR" if annualization_days <= 1 else None
        
        sharpe = 0.0
        try:
            if trade_count > 1:
                mean_ret = statistics.mean([t["pnl_percent"] for t in net_trades])
                stdev = statistics.stdev([t["pnl_percent"] for t in net_trades])
                if stdev > 0:
                    sharpe = round((mean_ret / stdev) * math.sqrt(max(1, trade_count)), 3)
        except Exception:
            sharpe = 0.0

        verdict = "favorable" if total_return > 0 and win_rate >= 45 and profit_factor >= 1 else "mixed" if trade_count else "insufficient"

        # Compute monthly returns heatmap (sum of pnl_percent by month)
        monthly_returns: dict[str, float] = {}
        for t in net_trades:
            m = t["exit_date"][:7]  # YYYY-MM
            monthly_returns[m] = monthly_returns.get(m, 0.0) + t["pnl_percent"]
        monthly_list = [{"month": k, "return": round(v, 2)} for k, v in sorted(monthly_returns.items())]

        best_trade = max(net_trades, key=lambda t: t["pnl_percent"]) if net_trades else None
        worst_trade = min(net_trades, key=lambda t: t["pnl_percent"]) if net_trades else None

        # Remove hard-coded blind truncation from core engine to preserve full curve visibility
        curve = net_equity_curve if net_equity_curve else [{"label": "Start", "equity": 100000.0}, {"label": "End", "equity": round(net_cash, 2)}]

        # ===================================================================
        # FEAT-008 — Execution model routing
        # ===================================================================
        # Both Pass 1 (gross) and Pass 2 (net) always run.  Both metric
        # sets are permanently retained so shadow comparison, rollback
        # validation, and auditability always have complete data:
        #
        #   execution_model == REALISTIC:
        #     Primary fields (total_return, win_rate, cagr, costs, etc.)
        #     come from Pass 2 (realistic) metrics.
        #
        #   execution_model == LEGACY:
        #     Primary fields come from Pass 1 (gross/legacy) metrics.
        #     Costs and slippage are zero (legacy model has none).
        #
        #   gross_* fields (gross_total_return, gross_win_rate, etc.)
        #     → ALWAYS legacy (Pass 1).  Never overwritten.
        #
        # composite_uses_realistic controls which metric feeds the
        # recommendation composite score at the orchestrator level.
        # ===================================================================

        if execution_model == "LEGACY":
            primary_total_return = gross_total_return
            primary_cagr = gross_cagr
            primary_max_drawdown = round(gross_max_drawdown, 2)
            primary_win_rate = gross_win_rate
            primary_profit_factor = gross_profit_factor
            primary_trade_count = gross_trade_count
            primary_sharpe = gross_sharpe
            primary_total_costs = 0.0
            primary_total_slippage = 0.0
            primary_verdict = (
                "favorable"
                if gross_total_return > 0 and gross_win_rate >= 45 and gross_profit_factor >= 1
                else "mixed" if gross_trade_count else "insufficient"
            )
            primary_trades = gross_trades
            primary_best_trade = max(gross_trades, key=lambda t: t["pnl_percent"]) if gross_trades else None
            primary_worst_trade = min(gross_trades, key=lambda t: t["pnl_percent"]) if gross_trades else None
            gross_monthly: dict[str, float] = {}
            for t in gross_trades:
                m = t["exit_date"][:7]
                gross_monthly[m] = gross_monthly.get(m, 0.0) + t["pnl_percent"]
            primary_monthly_list = [{"month": k, "return": round(v, 2)} for k, v in sorted(gross_monthly.items())]
            primary_equity_curve = curve
            feat008_score_used = "legacy"
        else:
            primary_cagr = cagr
            primary_max_drawdown = round(net_max_drawdown, 2)
            primary_win_rate = win_rate
            primary_profit_factor = profit_factor
            primary_trade_count = trade_count
            primary_sharpe = sharpe
            primary_total_costs = total_costs
            primary_total_slippage = total_slippage
            primary_verdict = verdict
            primary_trades = net_trades
            primary_best_trade = best_trade
            primary_worst_trade = worst_trade
            primary_monthly_list = monthly_list
            primary_equity_curve = curve
            primary_total_return = total_return
            feat008_score_used = "realistic"

        # ===================================================================
        # FEAT-008 — Metadata fields
        # ===================================================================
        feat008_slippage_bps: float | None = None
        feat008_brokerage_bps: float | None = None
        feat008_statutory_bps: float | None = None
        feat008_cost_bps: float | None = None
        if cost_cfg:
            slippage_rate = cost_cfg.get("slippage_rate", 0)
            brokerage_rate = cost_cfg.get("brokerage_rate", 0)
            statutory_rate = (
                cost_cfg.get("stt_rate_buy", 0)
                + cost_cfg.get("exc_trans_rate", 0)
                + cost_cfg.get("sebi_rate", 0)
                + cost_cfg.get("stamp_duty_rate", 0)
            )
            total_rate = slippage_rate + brokerage_rate + statutory_rate
            feat008_slippage_bps = round(slippage_rate * 10000, 2)
            feat008_brokerage_bps = round(brokerage_rate * 10000, 2)
            feat008_statutory_bps = round(statutory_rate * 10000, 2)
            feat008_cost_bps = round(total_rate * 10000, 2)

        total_skipped = trades_skipped + trades_skipped_error
        skip_parts = []
        if trades_skipped > 0:
            skip_parts.append("no next execution bar available")
        if trades_skipped_error > 0:
            skip_parts.append("execution errors")
        skip_note = f" ({'; '.join(skip_parts)})" if skip_parts else ""

        # LEGACY mode does not perform next-bar execution — no skipped trades
        if execution_model == "LEGACY":
            total_skipped = 0
            skip_note = ""

        feat008_expl = (
            f"Backtest executed in {execution_model} mode. "
            f"{'Same-candle-close fills, zero costs.' if execution_model == 'LEGACY' else 'Next-bar-open fills, costs applied.' if execution_model == 'REALISTIC' else f'Execution model: {execution_model}.'} "
            f"{primary_trade_count} trades simulated, {total_skipped} skipped{skip_note}. "
            f"Win rate {primary_win_rate}% (legacy reported {gross_win_rate}%), "
            f"profit factor {primary_profit_factor} (legacy reported {gross_profit_factor})."
        )

        return BacktestResult(
            mode=mode,
            strategy_name=strategy_name,
            total_return=primary_total_return,
            cagr=primary_cagr,
            max_drawdown=primary_max_drawdown,
            win_rate=primary_win_rate,
            profit_factor=primary_profit_factor,
            trade_count=primary_trade_count,
            verdict=primary_verdict,
            equity_curve=primary_equity_curve,
            trades=primary_trades,
            monthly_returns=primary_monthly_list,
            sharpe_ratio=round(primary_sharpe, 3) if isinstance(primary_sharpe, float) else 0.0,
            best_trade=primary_best_trade,
            worst_trade=primary_worst_trade,
            # Realism Foundation metrics (always from Pass 1)
            gross_total_return=gross_total_return,
            gross_cagr=gross_cagr,
            gross_max_drawdown=round(gross_max_drawdown, 2),
            gross_win_rate=gross_win_rate,
            gross_profit_factor=gross_profit_factor,
            gross_sharpe_ratio=gross_sharpe,
            cost_scenario=cost_scenario,
            total_transaction_costs=round(primary_total_costs, 2),
            total_slippage=round(primary_total_slippage, 2),
            position_sizing_pct=position_sizing_pct,
            cagr_warning=cagr_warning,
            # FEAT-008 metadata
            feat008_enabled=feat008_enabled,
            feat008_execution_model=execution_model,
            feat008_slippage_bps=feat008_slippage_bps,
            feat008_brokerage_bps=feat008_brokerage_bps,
            feat008_statutory_bps=feat008_statutory_bps,
            feat008_total_cost_bps_per_side=feat008_cost_bps,
            feat008_trades_simulated=primary_trade_count,
            feat008_trades_skipped=total_skipped,
            feat008_win_rate=primary_win_rate,
            feat008_profit_factor=primary_profit_factor,
            feat008_legacy_win_rate=gross_win_rate,
            feat008_legacy_profit_factor=gross_profit_factor,
            feat008_score_used=feat008_score_used,
            feat008_explanation=feat008_expl,
        )

    def _empty_result(
        self,
        mode: AnalysisMode,
        strategy_name: str,
        cost_scenario: str = "BASE_COST",
        position_sizing_pct: float = 20.0,
        feat008_enabled: bool = True,
    ) -> BacktestResult:
        # FEAT-008 cost metadata from active cost scenario
        cost_cfg = COST_SCENARIOS.get(cost_scenario, COST_SCENARIOS["BASE_COST"])
        slippage_rate = cost_cfg.get("slippage_rate", 0)
        brokerage_rate = cost_cfg.get("brokerage_rate", 0)
        statutory_rate = (
            cost_cfg.get("stt_rate_buy", 0)
            + cost_cfg.get("exc_trans_rate", 0)
            + cost_cfg.get("sebi_rate", 0)
            + cost_cfg.get("stamp_duty_rate", 0)
        )
        total_rate = slippage_rate + brokerage_rate + statutory_rate
        feat008_slippage_bps = round(slippage_rate * 10000, 2)
        feat008_brokerage_bps = round(brokerage_rate * 10000, 2)
        feat008_statutory_bps = round(statutory_rate * 10000, 2)
        feat008_cost_bps = round(total_rate * 10000, 2)

        return BacktestResult(
            mode=mode,
            strategy_name=strategy_name,
            total_return=0.0,
            cagr=None,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            trade_count=0,
            verdict="insufficient",
            equity_curve=[{"label": "Start", "equity": 100000.0}],
            trades=[],
            monthly_returns=[],
            sharpe_ratio=0.0,
            best_trade=None,
            worst_trade=None,
            gross_total_return=0.0,
            gross_cagr=None,
            gross_max_drawdown=0.0,
            gross_win_rate=0.0,
            gross_profit_factor=0.0,
            gross_sharpe_ratio=0.0,
            cost_scenario=cost_scenario,
            total_transaction_costs=0.0,
            total_slippage=0.0,
            position_sizing_pct=position_sizing_pct,
            cagr_warning="INSUFFICIENT_PERIOD_FOR_CAGR",
            # FEAT-008 metadata
            feat008_enabled=feat008_enabled,
            feat008_execution_model="LEGACY",
            feat008_total_cost_bps_per_side=feat008_cost_bps,
            feat008_trades_simulated=0,
            feat008_trades_skipped=0,
            feat008_win_rate=0.0,
            feat008_profit_factor=0.0,
            feat008_legacy_win_rate=0.0,
            feat008_legacy_profit_factor=0.0,
            feat008_score_used="legacy",
            feat008_slippage_bps=feat008_slippage_bps,
            feat008_brokerage_bps=feat008_brokerage_bps,
            feat008_statutory_bps=feat008_statutory_bps,
            feat008_explanation="Insufficient data (< 35 candles). No backtest performed.",
        )
