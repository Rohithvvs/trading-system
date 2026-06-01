from __future__ import annotations

from sqlalchemy.orm import Session

from ..schemas import (
    AnalysisRequest,
    AnalysisResponse,
    FullAnalysisResponse,
    RankingsResponse,
    ScreenerRequest,
    ScreenerResponse,
)
from ..utils import get_logger
from .orchestrator_agent import OrchestratorAgent


class RouterAgent:
    def __init__(self, db: Session) -> None:
        self.logger = get_logger("app.router")
        self.orchestrator = OrchestratorAgent(db)

    def analyze_stocks(self, request: AnalysisRequest) -> AnalysisResponse:
        return self.orchestrator.run_partial(request)

    def technical_only(self, request: AnalysisRequest) -> AnalysisResponse:
        return self.orchestrator.run_partial(request)

    def news_only(self, request: AnalysisRequest) -> AnalysisResponse:
        return self.orchestrator.run_partial(request)

    def backtest_only(self, request: AnalysisRequest) -> AnalysisResponse:
        return self.orchestrator.run_partial(request)

    def final_recommendation(self, request: AnalysisRequest) -> AnalysisResponse:
        return self.orchestrator.run_partial(request)

    async def full_analysis(self, request: AnalysisRequest) -> FullAnalysisResponse:
        self.logger.info(
            "Router dispatch | flow=full_analysis | symbols=%s | mode=%s",
            ",".join(request.symbols),
            request.mode.value,
        )
        return await self.orchestrator.run_full(request)

    def rankings(self, request: AnalysisRequest) -> RankingsResponse:
        return self.orchestrator.run_partial(request).rankings

    async def screener_full(self, request: ScreenerRequest, progress_callback=None) -> ScreenerResponse:
        self.logger.info(
            "Router dispatch | flow=screener_full | custom_symbols=%s | top_n=%s | lookback=%s",
            len(request.symbols),
            request.top_n,
            request.timeframe.lookback_window,
        )
        return await self.orchestrator.run_screener(request, progress_callback)
