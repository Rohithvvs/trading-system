from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Any
from ..db.session import get_db
from ..services.walk_forward_service import WalkForwardService
from ..models.walk_forward import WalkForwardSummary, VetoHistory

router = APIRouter(prefix="/api/walk-forward", tags=["Walk Forward Evaluation"])

@router.post("/evaluate", response_model=dict)
async def evaluate_symbol_walk_forward(symbol: str, min_windows: int = 4, db: AsyncSession = Depends(get_db)) -> Any:
    """
    Trigger a walk-forward optimization and out-of-sample backtest comparison
    between Champion and Challenger strategy overlays for a given NSE stock.
    """
    service = WalkForwardService(db)
    result = await service.run_walk_forward_evaluation(symbol, min_windows=min_windows)
    
    if "summary" not in result:
        # Failsafe inconclusive response
        raise HTTPException(
            status_code=400,
            detail=result.get("reason", "Evaluation could not be performed due to insufficient historical candles.")
        )
        
    return result

@router.get("/results", response_model=list)
async def get_walk_forward_history(symbol: str | None = None, db: AsyncSession = Depends(get_db)) -> Any:
    """
    Retrieve stored walk-forward rolling window summaries.
    """
    stmt = select(WalkForwardSummary)
    if symbol:
        stmt = stmt.where(WalkForwardSummary.symbol == symbol)
    stmt = stmt.order_by(WalkForwardSummary.id.desc())
    
    results = (await db.scalars(stmt)).all()
    return [
        {
            "id": r.id,
            "symbol": r.symbol,
            "window_label": r.window_label,
            "champ_net_return": r.champ_net_return,
            "chal_net_return": r.chal_net_return,
            "champ_trade_count": r.champ_trade_count,
            "chal_trade_count": r.chal_trade_count,
            "veto_count": r.veto_count,
            "veto_rate": r.veto_rate,
            "champ_expectancy": r.champ_expectancy,
            "chal_expectancy": r.chal_expectancy,
            "champ_profit_factor": r.champ_profit_factor,
            "chal_profit_factor": r.chal_profit_factor,
            "champ_drawdown": r.champ_drawdown,
            "chal_drawdown": r.chal_drawdown,
            "verdict": r.verdict,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in results
    ]

@router.get("/vetoes", response_model=list)
async def get_veto_statistics(symbol: str | None = None, db: AsyncSession = Depends(get_db)) -> Any:
    """
    Retrieve individual trade veto records and gate statistics.
    """
    stmt = select(VetoHistory)
    if symbol:
        stmt = stmt.where(VetoHistory.symbol == symbol)
    stmt = stmt.order_by(VetoHistory.id.desc())
    
    results = (await db.scalars(stmt)).all()
    return [
        {
            "id": r.id,
            "window_label": r.window_label,
            "scan_date": r.scan_date.isoformat() if r.scan_date else None,
            "symbol": r.symbol,
            "gate_name": r.gate_name,
            "original_signal": r.original_signal,
            "challenger_signal": r.challenger_signal,
            "veto_triggered": r.veto_triggered,
            "reason": r.reason,
            "engine_version": r.engine_version,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in results
    ]
