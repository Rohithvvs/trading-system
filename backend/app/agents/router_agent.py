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
from .orchestrator_agent import OrchestratorAgent


class RouterAgent:
    def __init__(self, db: Session) -> None:
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

    def full_analysis(self, request: AnalysisRequest) -> FullAnalysisResponse:
        return self.orchestrator.run_full(request)

    def rankings(self, request: AnalysisRequest) -> RankingsResponse:
        return self.orchestrator.run_partial(request).rankings

    def screener_full(self, request: ScreenerRequest) -> ScreenerResponse:
        return self.orchestrator.run_screener(request)
