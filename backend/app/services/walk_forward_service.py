import pandas as pd
import numpy as np
import statistics
import math
import asyncio
from datetime import datetime, date, timedelta, timezone
from typing import Any
from ta.trend import EMAIndicator
from sqlalchemy.ext.asyncio import AsyncSession

from ..utils.symbol import canonical_symbol, fyers_symbol
from ..services.market_data_service import MarketDataService
from ..services.backtest_service import calculate_transaction_costs, COST_SCENARIOS, PercentEquityPositionSizer
from ..models.walk_forward import WalkForwardSummary, VetoHistory
from ..config import settings
from ..schemas import AnalysisMode
from ..utils import get_logger

logger = get_logger("app.walk_forward")

class WalkForwardService:
    def __init__(self, db_session: AsyncSession = None) -> None:
        self.db = db_session
        self.md_service = MarketDataService()
        self.benchmark_symbols = list(settings.fyers_screener_symbols)

    def _to_ist_trading_date(self, val) -> date:
        import pytz
        if val is None:
            return None
        if isinstance(val, str):
            val = pd.to_datetime(val)
        has_tz = False
        if hasattr(val, "tzinfo") and val.tzinfo is not None:
            has_tz = True
        elif hasattr(val, "tz") and val.tz is not None:
            has_tz = True

        if has_tz:
            tz_kolkata = pytz.timezone("Asia/Kolkata")
            if hasattr(val, "tz_convert"):
                val_ist = val.tz_convert(tz_kolkata)
            else:
                val_ist = val.astimezone(tz_kolkata)
            return val_ist.date()
        else:
            if hasattr(val, "date"):
                return val.date()
            return pd.to_datetime(val).date()

    async def _load_candles(self, symbol: str, is_index: bool = False) -> pd.DataFrame:
        canon = canonical_symbol(symbol)
        df = await self.md_service.load_full_history(canon, "1D")
        if df.empty:
            fyers = fyers_symbol(canon, is_index=is_index)
            df = await self.md_service.load_full_history(fyers, is_index)
        return df.sort_index() if not df.empty else df

    async def _build_market_regime_dataframe(self) -> pd.DataFrame:
        """
        Build a date-aligned dataframe containing:
        - nifty_close, nifty_ema50
        - vix_close
        - breadth_pct (% of benchmark stocks above their EMA50)
        """
        logger.info("Building market regime inputs cache...")
        nifty_df = await self._load_candles("NIFTY50-INDEX", is_index=True)
        vix_df = await self._load_candles("INDIAVIX-INDEX", is_index=True)

        if nifty_df.empty:
            logger.error("NIFTY 50 data is completely missing. Cannot build market regime cache.")
            return pd.DataFrame()

        # Nifty EMA50
        if len(nifty_df) >= 50:
            nifty_df["ema50"] = EMAIndicator(close=nifty_df["close"], window=50).ema_indicator()
        else:
            nifty_df["ema50"] = nifty_df["close"].ewm(span=50, adjust=False).mean()

        nifty_df["trading_date"] = [self._to_ist_trading_date(ts) for ts in nifty_df.index]
        nifty_data = nifty_df[["trading_date", "close", "ema50"]].rename(
            columns={"close": "nifty_close", "ema50": "nifty_ema50"}
        )

        # VIX
        vix_data = pd.DataFrame(columns=["trading_date", "vix_close"])
        if not vix_df.empty:
            vix_df["trading_date"] = [self._to_ist_trading_date(ts) for ts in vix_df.index]
            vix_data = vix_df[["trading_date", "close"]].rename(columns={"close": "vix_close"})

        # Breadth: percentage of benchmark stocks above their EMA50
        async def get_bench_closes(symbol: str) -> pd.DataFrame:
            try:
                df = await self._load_candles(symbol)
                if df.empty or len(df) < 5:
                    return pd.DataFrame()
                df["ema50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
                df["trading_date"] = [self._to_ist_trading_date(ts) for ts in df.index]
                df["above_ema50"] = (df["close"] > df["ema50"]).astype(int)
                return df[["trading_date", "above_ema50"]].rename(columns={"above_ema50": symbol})
            except Exception as e:
                logger.error("Error loading benchmark stock %s: %s", symbol, e)
                return pd.DataFrame()

        bench_tasks = [get_bench_closes(sym) for sym in self.benchmark_symbols]
        bench_dfs = await asyncio.gather(*bench_tasks)
        
        # Merge all breadth indicators
        breadth_df = None
        for b_df in bench_dfs:
            if b_df.empty:
                continue
            if breadth_df is None:
                breadth_df = b_df
            else:
                breadth_df = pd.merge(breadth_df, b_df, on="trading_date", how="outer")

        if breadth_df is not None and not breadth_df.empty:
            # Calculate % above EMA50 for each row (excluding trading_date column)
            cols = [c for c in breadth_df.columns if c != "trading_date"]
            breadth_df["breadth_pct"] = breadth_df[cols].mean(axis=1)
            breadth_data = breadth_df[["trading_date", "breadth_pct"]]
        else:
            breadth_data = pd.DataFrame(columns=["trading_date", "breadth_pct"])

        # Merge Nifty, VIX, and Breadth
        merged = pd.merge(nifty_data, vix_data, on="trading_date", how="left")
        merged = pd.merge(merged, breadth_data, on="trading_date", how="left")
        
        # Forward-fill VIX and Breadth to cover weekend/mismatch anomalies
        merged = merged.sort_values("trading_date").ffill().bfill()
        logger.info("Regime cache built successfully. Count=%d rows", len(merged))
        return merged

    def _simulate_backtest(
        self,
        symbol: str,
        candles_df: pd.DataFrame,
        regime_df: pd.DataFrame,
        use_gating: bool,
        vix_caution: float,
        vix_highrisk: float,
        breadth_caution: float,
        breadth_weak: float,
        window_label: str = None
    ) -> tuple[dict, list[dict]]:
        """
        Simulate the backtest on candles_df.
        Gating rules:
        - Champion: use_gating is False (risk_multiplier=1.0, zero vetoes).
        - Challenger: use_gating is True:
          - CAUTIOUS (VIX >= caution OR breadth < caution): risk_multiplier = 0.5.
          - HIGHRISK/DEFENSIVE (VIX >= highrisk OR breadth < weak OR Nifty < Nifty EMA50): veto new entries.
        """
        net_cash = 100000.0
        net_shares = 0
        net_position_entry_price = 0.0
        net_position_entry_date = None
        net_position_entry_fee = 0.0
        
        trades = []
        vetoed_trades_list = []
        pending_buy = False
        pending_exit = False
        cost_cfg = COST_SCENARIOS["BASE_COST"]
        sizer = PercentEquityPositionSizer(percent=20.0)

        # Merge candles with pre-computed market metrics
        df = pd.merge(candles_df, regime_df, on="trading_date", how="left").sort_values("trading_date").reset_index(drop=True)
        n_candles = len(df)
        
        # Strategy indicators
        if n_candles >= 50:
            df["ema_fast"] = EMAIndicator(close=df["close"], window=20).ema_indicator()
            df["ema_slow"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
        else:
            df["ema_fast"] = df["close"].ewm(span=20, adjust=False).mean()
            df["ema_slow"] = df["close"].ewm(span=50, adjust=False).mean()
        
        df["rsi"] = df["close"].rolling(14).mean() # simplified RSI for simulator
        df["avg_volume"] = df["volume"].rolling(20).mean()

        gated_new_entry_allowed = True
        gated_risk_multiplier = 1.0
        gated_reason = ""
        was_vetoed_on_current_signal = False

        for i in range(n_candles):
            row = df.iloc[i]
            
            # Warmed up check
            if i < 50 or pd.isna(row["ema_slow"]):
                continue

            # 1. Execute pending orders at candle open (using gated conditions saved from day i-1 close)
            if pending_buy and net_shares == 0:
                entry_price = float(row["open"])
                
                # Check gate permission (evaluated at the signal close i-1)
                if use_gating and not gated_new_entry_allowed:
                    # Vetoed!
                    if not was_vetoed_on_current_signal:
                        vetoed_trades_list.append({
                            "window_label": window_label,
                            "scan_date": pd.to_datetime(row["trading_date"]),
                            "symbol": symbol,
                            "gate_name": "MarketPermissionEngine",
                            "original_signal": "BUY",
                            "challenger_signal": "WATCH",
                            "veto_triggered": True,
                            "reason": gated_reason,
                            "engine_version": "1.0.0"
                        })
                        was_vetoed_on_current_signal = True
                    pending_buy = False
                else:
                    exec_price = entry_price * (1 + cost_cfg["slippage_rate"])
                    # Apply risk multiplier to position sizing
                    sizing_pct = 20.0 * gated_risk_multiplier
                    qty = PercentEquityPositionSizer(percent=sizing_pct).calculate_shares(net_cash, exec_price, AnalysisMode.swing)
                    
                    charges = calculate_transaction_costs("BUY", exec_price, qty, AnalysisMode.swing, cost_cfg)
                    fee = charges["total"]
                    
                    while qty > 0 and (qty * exec_price + fee) > net_cash:
                        qty -= 1
                        charges = calculate_transaction_costs("BUY", exec_price, qty, AnalysisMode.swing, cost_cfg)
                        fee = charges["total"]
                        
                    if qty > 0:
                        net_cash -= (qty * exec_price + fee)
                        net_shares = qty
                        net_position_entry_price = exec_price
                        net_position_entry_date = row["trading_date"]
                        net_position_entry_fee = fee
                        # Reset veto flag on entry
                        was_vetoed_on_current_signal = False
                    pending_buy = False

            elif pending_exit and net_shares > 0:
                exit_price = float(row["open"])
                exec_price = exit_price * (1 - cost_cfg["slippage_rate"])
                
                charges = calculate_transaction_costs("SELL", exec_price, net_shares, AnalysisMode.swing, cost_cfg)
                fee = charges["total"]
                
                exit_val = (net_shares * exec_price) - fee
                net_cash += exit_val
                
                cost_basis = (net_shares * net_position_entry_price) + net_position_entry_fee
                net_pnl = exit_val - cost_basis
                pnl_pct = (net_pnl / cost_basis * 100) if cost_basis > 0 else 0.0
                
                trades.append({
                    "entry_date": str(net_position_entry_date),
                    "exit_date": str(row["trading_date"]),
                    "entry_price": round(net_position_entry_price, 2),
                    "exit_price": round(exec_price, 2),
                    "pnl_percent": round(pnl_pct, 2)
                })
                net_shares = 0
                pending_exit = False

            # 2. Check signal triggers and evaluate market permission regime at candle close
            bullish_entry = bool(
                row["close"] > row["ema_fast"]
                and row["ema_fast"] > row["ema_slow"]
                and row["rsi"] >= 50
                and row["volume"] >= max(row["avg_volume"] or 0, 1) * 0.8
            )
            exit_signal = bool(
                row["close"] < row["ema_fast"]
                or row["rsi"] < 45
            )

            # Resolve market permission regime on this trading date close (day i close) to be used on next-day open i+1
            vix_val = float(row["vix_close"]) if not pd.isna(row["vix_close"]) else 19.0
            breadth_val = float(row["breadth_pct"]) if not pd.isna(row["breadth_pct"]) else 0.45
            nifty_cls = float(row["nifty_close"]) if not pd.isna(row["nifty_close"]) else float(row["close"])
            nifty_ema = float(row["nifty_ema50"]) if not pd.isna(row["nifty_ema50"]) else float(row["ema_slow"])

            nifty_bullish = nifty_cls > nifty_ema

            current_entry_allowed = True
            current_risk_multiplier = 1.0
            current_reason = ""

            if use_gating:
                if vix_val >= 30.0:
                    current_entry_allowed = False
                    current_risk_multiplier = 0.0
                    current_reason = f"DEFENSIVE: extreme VIX {vix_val:.2f}"
                elif vix_val >= vix_highrisk or breadth_val < breadth_weak or not nifty_bullish:
                    current_entry_allowed = False
                    current_risk_multiplier = 0.0
                    if not nifty_bullish:
                        current_reason = "HIGHRISK: Nifty bearish"
                    elif vix_val >= vix_highrisk:
                        current_reason = f"HIGHRISK: VIX {vix_val:.2f} >= highrisk {vix_highrisk}"
                    else:
                        current_reason = f"HIGHRISK: breadth {breadth_val:.2f} < weak {breadth_weak}"
                elif vix_val >= vix_caution or breadth_val < breadth_caution:
                    current_entry_allowed = True
                    current_risk_multiplier = 0.5
                    if vix_val >= vix_caution:
                        current_reason = f"CAUTIOUS: VIX {vix_val:.2f}"
                    else:
                        current_reason = f"CAUTIOUS: breadth {breadth_val:.2f}"

            if net_shares == 0:
                if bullish_entry:
                    pending_buy = True
                    pending_exit = False
                    # Save permission parameters of this signal close for the next open execution
                    gated_new_entry_allowed = current_entry_allowed
                    gated_risk_multiplier = current_risk_multiplier
                    gated_reason = current_reason
                else:
                    # Reset veto state if signal goes off
                    was_vetoed_on_current_signal = False
            else:
                # We have a position, reset veto state
                was_vetoed_on_current_signal = False
                if exit_signal:
                    pending_exit = True
                    pending_buy = False

        # Force exit open positions at last close
        if net_shares > 0:
            final_row = df.iloc[-1]
            exit_price = float(final_row["close"])
            exec_price = exit_price * (1 - cost_cfg["slippage_rate"])
            charges = calculate_transaction_costs("SELL", exec_price, net_shares, AnalysisMode.swing, cost_cfg)
            fee = charges["total"]
            exit_val = (net_shares * exec_price) - fee
            net_cash += exit_val
            cost_basis = (net_shares * net_position_entry_price) + net_position_entry_fee
            net_pnl = exit_val - cost_basis
            pnl_pct = (net_pnl / cost_basis * 100) if cost_basis > 0 else 0.0
            
            trades.append({
                "entry_date": str(net_position_entry_date),
                "exit_date": str(final_row["trading_date"]),
                "entry_price": round(net_position_entry_price, 2),
                "exit_price": round(exec_price, 2),
                "pnl_percent": round(pnl_pct, 2)
            })

        # Calculate metrics
        net_return = round(((net_cash - 100000.0) / 100000.0) * 100, 2)
        trade_count = len(trades)
        wins = [t["pnl_percent"] for t in trades if t["pnl_percent"] > 0]
        losses = [abs(t["pnl_percent"]) for t in trades if t["pnl_percent"] < 0]
        
        win_rate = round((len(wins) / trade_count) * 100, 2) if trade_count else 0.0
        profit_factor = round((sum(wins) / sum(losses)), 2) if losses else round(sum(wins), 2) if wins else 0.0
        expectancy = round(statistics.mean([t["pnl_percent"] for t in trades]), 2) if trade_count else 0.0

        # Simple peak-to-trough max drawdown
        equity = 100000.0
        peak = equity
        max_dd = 0.0
        for t in trades:
            equity *= 1 + (t["pnl_percent"] / 100)
            peak = max(peak, equity)
            max_dd = max(max_dd, ((peak - equity) / peak) * 100)

        metrics = {
            "net_return": net_return,
            "trade_count": trade_count,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "max_drawdown": round(max_dd, 2),
            "veto_count": len(vetoed_trades_list),
            "veto_rate": round(len(vetoed_trades_list) / (trade_count + len(vetoed_trades_list)), 2) if (trade_count + len(vetoed_trades_list)) else 0.0
        }
        return metrics, vetoed_trades_list

    async def run_walk_forward_evaluation(self, symbol: str, min_windows: int = 4) -> dict:
        """
        Main runner:
        1. Loads index cache and stock candles.
        2. Splits into rolling Train (252) and Test (63) windows.
        3. On each Train window, runs small grid optimization of Challenger parameters.
        4. Applies optimized parameters out-of-sample on Test window.
        5. Computes Champion vs Challenger metrics and persists.
        6. Returns summary verdict.
        """
        logger.info("Initializing Walk-Forward Evaluation for symbol=%s", symbol)
        
        # Load data
        regime_df = await self._build_market_regime_dataframe()
        stock_df = await self._load_candles(symbol)

        if regime_df.empty or stock_df.empty or len(stock_df) < (252 + 63):
            logger.error("Insufficient historical data for symbol %s. Stock candles count: %d", symbol, len(stock_df))
            return {
                "verdict": "INCONCLUSIVE",
                "reason": f"Insufficient candles count ({len(stock_df)}) for rolling Train=252/Test=63 splits."
            }

        # Normalize stock timestamps to daily trading dates
        stock_df["trading_date"] = [self._to_ist_trading_date(ts) for ts in stock_df.index]
        stock_df = stock_df.sort_values("trading_date").reset_index(drop=True)

        # rolling windows setup
        total_rows = len(stock_df)
        windows = []
        idx = 0
        while idx + 252 + 63 <= total_rows:
            train_slice = stock_df.iloc[idx : idx + 252]
            test_slice = stock_df.iloc[idx + 252 : idx + 252 + 63]
            windows.append((train_slice, test_slice))
            idx += 63 # slide by test window size

        logger.info("Created %d rolling walk-forward windows", len(windows))

        # Parameter Grid (16 combinations)
        grid = []
        for vix_c in [18.0, 20.0]:
            for vix_hr in [22.0, 25.0]:
                for b_c in [0.4, 0.5]:
                    for b_w in [0.2, 0.3]:
                        grid.append((vix_c, vix_hr, b_c, b_w))

        window_results = []
        all_vetoed_trades = []

        # Run windows
        for w_idx, (train_df, test_df) in enumerate(windows):
            window_label = f"Window {w_idx+1} ({train_df['trading_date'].iloc[0]} to {test_df['trading_date'].iloc[-1]})"
            logger.info("Running %s", window_label)

            # Fit: Optimize Challenger parameters on train_df using net expectancy
            best_opt_params = grid[0]
            best_train_expectancy = -9999.0
            
            for param in grid:
                v_c, v_hr, b_c, b_w = param
                metrics, _ = self._simulate_backtest(
                    symbol=symbol,
                    candles_df=train_df,
                    regime_df=regime_df,
                    use_gating=True,
                    vix_caution=v_c,
                    vix_highrisk=v_hr,
                    breadth_caution=b_c,
                    breadth_weak=b_w
                )
                if metrics["expectancy"] > best_train_expectancy:
                    best_train_expectancy = metrics["expectancy"]
                    best_opt_params = param

            # Evaluate Out-of-Sample on test_df
            v_c, v_hr, b_c, b_w = best_opt_params
            
            # Champion (no gating)
            champ_metrics, _ = self._simulate_backtest(
                symbol=symbol,
                candles_df=test_df,
                regime_df=regime_df,
                use_gating=False,
                vix_caution=v_c,
                vix_highrisk=v_hr,
                breadth_caution=b_c,
                breadth_weak=b_w
            )
            
            # Challenger (with optimized gating parameters)
            chal_metrics, test_vetoes = self._simulate_backtest(
                symbol=symbol,
                candles_df=test_df,
                regime_df=regime_df,
                use_gating=True,
                vix_caution=v_c,
                vix_highrisk=v_hr,
                breadth_caution=b_c,
                breadth_weak=b_w,
                window_label=window_label
            )

            # Evaluate Out-of-sample verdict for this window
            # Criteria: Net Expectancy >= Champion, and Drawdown is not worse by more than 5.0%
            pass_expectancy = chal_metrics["expectancy"] >= champ_metrics["expectancy"]
            pass_dd = chal_metrics["max_drawdown"] <= (champ_metrics["max_drawdown"] + 5.0)
            pass_veto = chal_metrics["veto_rate"] <= 0.40
            
            win_verdict = "PASS" if (pass_expectancy and pass_dd and pass_veto) else "FAIL"

            res = {
                "window_label": window_label,
                "start_date": pd.to_datetime(test_df["trading_date"].iloc[0]),
                "end_date": pd.to_datetime(test_df["trading_date"].iloc[-1]),
                "champ_net_return": champ_metrics["net_return"],
                "chal_net_return": chal_metrics["net_return"],
                "champ_trade_count": champ_metrics["trade_count"],
                "chal_trade_count": chal_metrics["trade_count"],
                "veto_count": chal_metrics["veto_count"],
                "veto_rate": chal_metrics["veto_rate"],
                "champ_expectancy": champ_metrics["expectancy"],
                "chal_expectancy": chal_metrics["expectancy"],
                "champ_profit_factor": champ_metrics["profit_factor"],
                "chal_profit_factor": chal_metrics["profit_factor"],
                "champ_drawdown": champ_metrics["max_drawdown"],
                "chal_drawdown": chal_metrics["max_drawdown"],
                "champ_win_rate": champ_metrics["win_rate"],
                "chal_win_rate": chal_metrics["win_rate"],
                "opt_vix_caution": v_c,
                "opt_vix_highrisk": v_hr,
                "opt_breadth_caution": b_c,
                "opt_breadth_weak": b_w,
                "verdict": win_verdict
            }
            window_results.append(res)
            
            for v in test_vetoes:
                all_vetoed_trades.append(v)

        # Aggregate summary totals
        total_windows = len(window_results)
        passed_windows = sum(1 for w in window_results if w["verdict"] == "PASS")
        avg_champ_return = sum(w["champ_net_return"] for w in window_results) / total_windows
        avg_chal_return = sum(w["chal_net_return"] for w in window_results) / total_windows
        avg_veto_rate = sum(w["veto_rate"] for w in window_results) / total_windows

        # Final Acceptance Framework verdict
        # Criteria:
        # - Veto rate ceiling: average veto rate <= 0.40 (40%)
        # - Positive edge fraction: passed windows >= 65% (0.65)
        # - Average out-of-sample expectancy >= Champion
        overall_passed_pct = passed_windows / total_windows
        
        final_verdict = "FAIL"
        verdict_reasons = []

        if total_windows < min_windows:
            final_verdict = "INCONCLUSIVE"
            verdict_reasons.append(
                f"Insufficient out-of-sample windows ({total_windows} actual vs {min_windows} required minimum). "
                "The walk-forward history is too short for a statistically significant acceptance decision."
            )
        else:
            if avg_veto_rate > 0.40:
                verdict_reasons.append(f"Veto rate of {avg_veto_rate*100:.1f}% exceeds 40.0% ceiling")
            if overall_passed_pct < 0.65:
                verdict_reasons.append(f"Challenger outperformed in only {overall_passed_pct*100:.1f}% of windows (required 65%)")
            
            if not verdict_reasons:
                final_verdict = "PASS"
                verdict_reasons.append("Challenger consistently reduces drawdown risk while maintaining opportunity count and edge")
        
        summary = {
            "symbol": symbol,
            "total_windows": total_windows,
            "passed_windows": passed_windows,
            "passed_windows_pct": round(overall_passed_pct * 100, 2),
            "avg_champ_return": round(avg_champ_return, 2),
            "avg_chal_return": round(avg_chal_return, 2),
            "avg_veto_rate": round(avg_veto_rate, 2),
            "verdict": final_verdict,
            "verdict_reasons": verdict_reasons,
            "warnings": [
                "WARNING: possible survivorship bias present in current-universe scan. point-in-time index membership not enforced.",
                "WARNING: missing event-risk coverage. macro events not active in this iteration.",
                "WARNING: data staleness checks are active. missing data fallbacks are in CAUTIOUS state."
            ]
        }

        # Persist summaries and vetoes to SQLite
        if self.db is not None:
            try:
                for w in window_results:
                    db_w = WalkForwardSummary(
                        symbol=symbol,
                        window_label=w["window_label"],
                        start_date=w["start_date"],
                        end_date=w["end_date"],
                        champ_net_return=w["champ_net_return"],
                        chal_net_return=w["chal_net_return"],
                        champ_trade_count=w["champ_trade_count"],
                        chal_trade_count=w["chal_trade_count"],
                        veto_count=w["veto_count"],
                        veto_rate=w["veto_rate"],
                        champ_expectancy=w["champ_expectancy"],
                        chal_expectancy=w["chal_expectancy"],
                        champ_profit_factor=w["champ_profit_factor"],
                        chal_profit_factor=w["chal_profit_factor"],
                        champ_drawdown=w["champ_drawdown"],
                        chal_drawdown=w["chal_drawdown"],
                        champ_win_rate=w["champ_win_rate"],
                        chal_win_rate=w["chal_win_rate"],
                        opt_vix_caution=w["opt_vix_caution"],
                        opt_vix_highrisk=w["opt_vix_highrisk"],
                        opt_breadth_caution=w["opt_breadth_caution"],
                        opt_breadth_weak=w["opt_breadth_weak"],
                        verdict=w["verdict"]
                    )
                    self.db.add(db_w)

                for v in all_vetoed_trades:
                    db_v = VetoHistory(
                        window_label=v["window_label"],
                        scan_date=v["scan_date"],
                        symbol=v["symbol"],
                        gate_name=v["gate_name"],
                        original_signal=v["original_signal"],
                        challenger_signal=v["challenger_signal"],
                        veto_triggered=v["veto_triggered"],
                        reason=v["reason"],
                        engine_version=v["engine_version"]
                    )
                    self.db.add(db_v)

                await self.db.commit()
                logger.info("Persisted walk-forward summaries and veto statistics to database.")
            except Exception as persist_error:
                logger.error("Failed to persist walk-forward history to database: %s", persist_error)
                await self.db.rollback()

        return {
            "summary": summary,
            "windows": window_results
        }
