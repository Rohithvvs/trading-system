from __future__ import annotations

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD

from ..schemas import AnalysisMode, BacktestResult, OHLCVPoint


class BacktestService:
    def run(self, symbol: str, mode: AnalysisMode, candles: list[OHLCVPoint]) -> BacktestResult:
        strategy_name = "ema_rsi_volume" if mode == AnalysisMode.intraday else "sma_rsi_macd"
        if len(candles) < 35:
            return self._empty_result(mode, strategy_name)

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
        fast_window = 9 if mode == AnalysisMode.intraday else 20
        slow_window = 20 if mode == AnalysisMode.intraday else 50
        frame["ema_fast"] = EMAIndicator(close=frame["close"], window=fast_window).ema_indicator()
        frame["ema_slow"] = EMAIndicator(close=frame["close"], window=slow_window).ema_indicator()
        frame["rsi"] = RSIIndicator(close=frame["close"], window=14).rsi()
        macd = MACD(close=frame["close"], window_slow=26, window_fast=12, window_sign=9)
        frame["macd"] = macd.macd()
        frame["macd_signal"] = macd.macd_signal()
        frame["avg_volume"] = frame["volume"].rolling(20).mean()

        equity = 100000.0
        peak_equity = equity
        max_drawdown = 0.0
        position_entry: float | None = None
        trade_returns: list[float] = []
        equity_curve: list[dict[str, float | str]] = []

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

            if position_entry is None and bullish_entry:
                position_entry = float(row["close"])
            elif position_entry is not None and exit_signal:
                trade_return = ((float(row["close"]) - position_entry) / position_entry) * 100
                trade_returns.append(trade_return)
                equity *= 1 + (trade_return / 100)
                position_entry = None
                peak_equity = max(peak_equity, equity)
                if peak_equity:
                    max_drawdown = max(max_drawdown, ((peak_equity - equity) / peak_equity) * 100)
                equity_curve.append({"label": str(row["timestamp"].date()), "equity": round(equity, 2)})

        if position_entry is not None:
            final_close = float(frame["close"].iloc[-1])
            trade_return = ((final_close - position_entry) / position_entry) * 100
            trade_returns.append(trade_return)
            equity *= 1 + (trade_return / 100)
            equity_curve.append({"label": str(frame["timestamp"].iloc[-1].date()), "equity": round(equity, 2)})

        total_return = round(((equity - 100000.0) / 100000.0) * 100, 2)
        trade_count = len(trade_returns)
        wins = [item for item in trade_returns if item > 0]
        losses = [abs(item) for item in trade_returns if item < 0]
        win_rate = round((len(wins) / trade_count) * 100, 2) if trade_count else 0.0
        profit_factor = round((sum(wins) / sum(losses)), 2) if losses else round(sum(wins), 2) if wins else 0.0
        cagr = round(total_return * (252 / max(len(frame), 1)), 2)
        verdict = "favorable" if total_return > 0 and win_rate >= 45 and profit_factor >= 1 else "mixed" if trade_count else "insufficient"
        curve = equity_curve[-10:] or [{"label": "Start", "equity": 100000.0}, {"label": "End", "equity": round(equity, 2)}]

        return BacktestResult(
            mode=mode,
            strategy_name=strategy_name,
            total_return=total_return,
            cagr=cagr,
            max_drawdown=round(max_drawdown, 2),
            win_rate=win_rate,
            profit_factor=profit_factor,
            trade_count=trade_count,
            verdict=verdict,
            equity_curve=curve,
        )

    def _empty_result(self, mode: AnalysisMode, strategy_name: str) -> BacktestResult:
        return BacktestResult(
            mode=mode,
            strategy_name=strategy_name,
            total_return=0.0,
            cagr=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            trade_count=0,
            verdict="insufficient",
            equity_curve=[{"label": "Start", "equity": 100000.0}],
        )
