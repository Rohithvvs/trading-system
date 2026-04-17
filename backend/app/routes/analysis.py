from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..agents import RouterAgent
from ..db import get_db
from ..schemas import (
    AnalysisRequest,
    AnalysisResponse,
    FullAnalysisResponse,
    RankingsResponse,
    ScreenerRequest,
    ScreenerResponse,
)
from ..utils import sanitize_for_json


router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/technical", response_model=AnalysisResponse)
def technical_analysis(payload: AnalysisRequest, db: Session = Depends(get_db)) -> AnalysisResponse:
    response = RouterAgent(db).technical_only(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/news", response_model=AnalysisResponse)
def news_analysis(payload: AnalysisRequest, db: Session = Depends(get_db)) -> AnalysisResponse:
    response = RouterAgent(db).news_only(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/backtest", response_model=AnalysisResponse)
def backtest_analysis(payload: AnalysisRequest, db: Session = Depends(get_db)) -> AnalysisResponse:
    response = RouterAgent(db).backtest_only(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/final-recommendation", response_model=AnalysisResponse)
def final_recommendation(payload: AnalysisRequest, db: Session = Depends(get_db)) -> AnalysisResponse:
    response = RouterAgent(db).final_recommendation(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/full", response_model=FullAnalysisResponse)
def full_analysis(payload: AnalysisRequest, db: Session = Depends(get_db)) -> FullAnalysisResponse:
    response = RouterAgent(db).full_analysis(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/rankings", response_model=RankingsResponse)
def rankings(payload: AnalysisRequest, db: Session = Depends(get_db)) -> RankingsResponse:
    response = RouterAgent(db).rankings(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/screener/full", response_model=ScreenerResponse)
def screener_full(payload: ScreenerRequest, db: Session = Depends(get_db)) -> ScreenerResponse:
    response = RouterAgent(db).screener_full(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))
