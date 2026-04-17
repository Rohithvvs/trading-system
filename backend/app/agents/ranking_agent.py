from __future__ import annotations

from ..schemas import RankingsResponse, StockAnalysisResult
from ..services.ranking_service import RankingService


class RankingAgent:
    def __init__(self) -> None:
        self.service = RankingService()

    def run(self, items: list[StockAnalysisResult]) -> RankingsResponse:
        return self.service.rank(items)
