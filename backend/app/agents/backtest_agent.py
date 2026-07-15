from __future__ import annotations

from ..schemas import AnalysisMode, BacktestResult, OHLCVPoint
from ..services.backtest_service import BacktestService


class BacktestAgent:
    def __init__(self) -> None:
        self.service = BacktestService()

    def run(
        self,
        symbol: str,
        mode: AnalysisMode,
        candles: list[OHLCVPoint],
        cost_scenario: str = "BASE_COST",
        position_sizing_pct: float = 20.0,
        execution_model: str = "REALISTIC",
        composite_uses_realistic: bool = True,
        skip_on_missing_next_bar: bool = True,
        feat008_enabled: bool = True,
    ) -> BacktestResult:
        return self.service.run(
            symbol, mode, candles, cost_scenario,
            position_sizing_pct, execution_model, composite_uses_realistic,
            skip_on_missing_next_bar=skip_on_missing_next_bar,
            feat008_enabled=feat008_enabled,
        )
