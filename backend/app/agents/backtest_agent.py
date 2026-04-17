from __future__ import annotations

from ..schemas import AnalysisMode, BacktestResult, OHLCVPoint
from ..services.backtest_service import BacktestService


class BacktestAgent:
    def __init__(self) -> None:
        self.service = BacktestService()

    def run(self, symbol: str, mode: AnalysisMode, candles: list[OHLCVPoint]) -> BacktestResult:
        return self.service.run(symbol, mode, candles)
