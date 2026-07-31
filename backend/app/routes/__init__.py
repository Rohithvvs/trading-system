from fastapi import APIRouter

from .analysis import router as analysis_router
from .health import router as health_router
from .paper_trading import router as paper_trading_router
from .settings import router as settings_router
from .stocks import router as stocks_router
from .test_diagnostics import router as test_diagnostics_router
from .token import router as token_router, internal_router
from .broker_tokens import router as broker_tokens_router
from .workstation import router as workstation_router
from .logs import router as logs_router
from .scanner import router as scanner_router
from .system import router as system_router
from .diagnostics import router as diagnostics_router
from .governance import governance_router
from .analytics import router as analytics_router
# Preserve existing governance command-routing router (GET /api/v1/governance/routes)
# declared in app.governance.router; the new governance_router above extends it
# with promotion / kill-switch / attribution endpoints under the same prefix.
from ..governance.router import governance_router as command_routing_governance_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(stocks_router)
api_router.include_router(analysis_router)
api_router.include_router(paper_trading_router)
api_router.include_router(token_router)
api_router.include_router(internal_router)
api_router.include_router(broker_tokens_router)
api_router.include_router(settings_router)
api_router.include_router(workstation_router)
api_router.include_router(test_diagnostics_router)
api_router.include_router(logs_router)
api_router.include_router(scanner_router)
api_router.include_router(system_router)
api_router.include_router(diagnostics_router)
api_router.include_router(governance_router)
api_router.include_router(analytics_router)
api_router.include_router(command_routing_governance_router)

