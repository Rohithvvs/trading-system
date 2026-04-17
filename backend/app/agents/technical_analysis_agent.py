from __future__ import annotations

from ..schemas import AnalysisMode, OHLCVPoint, TechnicalAnalysisResult
from ..services.technical_analysis_service import TechnicalAnalysisService


class TechnicalAnalysisAgent:
    def __init__(self) -> None:
        self.service = TechnicalAnalysisService()

    def run(self, symbol: str, candles: list[OHLCVPoint], mode: AnalysisMode) -> TechnicalAnalysisResult:
        return self.service.analyze(symbol, candles, mode)
