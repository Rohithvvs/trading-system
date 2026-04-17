from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..agents import RouterAgent
from ..db import get_db
from ..schemas import AnalysisRequest, AnalysisResponse


router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.post("/analyze", response_model=AnalysisResponse)
def analyze_stocks(payload: AnalysisRequest, db: Session = Depends(get_db)) -> AnalysisResponse:
    return RouterAgent(db).analyze_stocks(payload)
