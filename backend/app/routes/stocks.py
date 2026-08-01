"""Stock analysis routes.

Candle ownership (Sprint 4 / T010):
  ``POST /stocks/analyze`` dispatches through ``RouterAgent`` → ``OrchestratorAgent``.
  When ``AUTHORITATIVE_CANDLE_STORE_ENABLED=true``, orchestrator and
  ``FyersService.fetch_ohlcv`` route OHLCV reads via ``AuthoritativeCandleStore``
  so dashboard/stock analysis share the same candle owner as scanner flows.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents import RouterAgent
from ..config.settings import settings
from ..db import get_db
from ..schemas import AnalysisRequest, AnalysisResponse


router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.post("/analyze", response_model=AnalysisResponse)
def analyze_stocks(payload: AnalysisRequest, db: AsyncSession = Depends(get_db)) -> AnalysisResponse:
    # Candle path is ACS-gated inside OrchestratorAgent / FyersService (flag live-read).
    # Explicit check keeps the dependency visible at the REST boundary (T010).
    _ = settings.is_authoritative_candle_store_enabled()
    return RouterAgent(db).analyze_stocks(payload)
