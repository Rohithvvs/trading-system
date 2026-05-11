from fastapi import APIRouter

from .analysis import router as analysis_router
from .health import router as health_router
from .paper_trading import router as paper_trading_router
from .stocks import router as stocks_router
from .test_diagnostics import router as test_diagnostics_router
from .token import router as token_router
from .workstation import router as workstation_router


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(stocks_router)
api_router.include_router(analysis_router)
api_router.include_router(paper_trading_router)
api_router.include_router(token_router)
api_router.include_router(workstation_router)
api_router.include_router(test_diagnostics_router)
