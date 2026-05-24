from __future__ import annotations

from ..schemas import AnalysisMode, OHLCVPoint, TechnicalAnalysisResult
from ..services.technical_analysis_service import TechnicalAnalysisService


class TechnicalAnalysisAgent:
    def __init__(self) -> None:
        self.service = TechnicalAnalysisService()

    def run_bulk(self, candles_dict: dict[str, list[OHLCVPoint]], mode: AnalysisMode) -> dict[str, TechnicalAnalysisResult]:
        return self.service.analyze_bulk(candles_dict, mode)
