from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..agents import RouterAgent
from ..db import get_db
from ..db.scan_store import load_latest_scan, save_latest_scan
from ..schemas import (
    AnalysisRequest,
    AnalysisResponse,
    FullAnalysisResponse,
    RankingsResponse,
    ScreenerRequest,
    ScreenerResponse,
)
import logging

from ..utils import sanitize_for_json
from app.services import candle_store
from ..utils import get_logger
from fastapi import HTTPException
from app.services.fyers_service import (
    FyersAuthExpiredError,
    FyersAuthInvalidError,
    FyersRateLimitError,
    FyersAPIError,
)


router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = get_logger("app.routes.analysis")


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
    logger.info(
        "API ENTRY | endpoint=/analysis/full | symbols=%s | mode=%s | intraday=%s | swing=%s | lookback=%s",
        len(payload.symbols),
        payload.mode.value,
        payload.timeframe.intraday,
        payload.timeframe.swing,
        payload.timeframe.lookback_window,
    )
    response = RouterAgent(db).full_analysis(payload)
    logger.info(
        "API EXIT | endpoint=/analysis/full | analyzed=%s | generated_at=%s",
        len(response.items),
        response.generated_at.isoformat(),
    )
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/rankings", response_model=RankingsResponse)
def rankings(payload: AnalysisRequest, db: Session = Depends(get_db)) -> RankingsResponse:
    response = RouterAgent(db).rankings(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/screener/full", response_model=ScreenerResponse)
def screener_full(payload: ScreenerRequest, db: Session = Depends(get_db)) -> ScreenerResponse:
    # Ensure candle cache DB exists before running a potentially large scan
    try:
        candle_store.init_db()
    except Exception:
        logger.warning("Failed to initialize candle cache DB (continuing)")

    logger.info(
        "API ENTRY | endpoint=/analysis/screener/full | mode=%s | top_n=%s | lookback=%s | swing=%s | custom_symbols=%s",
        payload.mode.value,
        payload.top_n,
        payload.timeframe.lookback_window,
        payload.timeframe.swing,
        len(payload.symbols),
    )
    try:
        response = RouterAgent(db).screener_full(payload)
        result = sanitize_for_json(response.model_dump(mode="json"))
        save_latest_scan(result)
        logger.info(
            "API EXIT | endpoint=/analysis/screener/full | scanned=%s | valid=%s | eligible=%s | matched=%s | shortlisted=%s | buy=%s | watch=%s | data_source=%s | stopped_at=%s",
            response.scanned_symbols,
            len(response.data_valid_symbols),
            len(response.eligible_symbols),
            len(response.matched_symbols),
            len(response.shortlisted_symbols),
            len(response.buy_candidate_symbols),
            len(response.watch_candidate_symbols),
            response.data_source,
            response.stopped_at_stage,
        )
        return JSONResponse(content=result)

    except FyersAuthExpiredError as e:
        raise HTTPException(status_code=401, detail={
            "error_type": "FYERS_TOKEN_EXPIRED",
            "message": str(e),
            "action": "Please re-authenticate with Fyers and restart the backend.",
        })

    except FyersAuthInvalidError as e:
        raise HTTPException(status_code=401, detail={
            "error_type": "FYERS_TOKEN_INVALID",
            "message": str(e),
            "action": "Check your Fyers API credentials in the config file.",
        })

    except FyersRateLimitError as e:
        raise HTTPException(status_code=429, detail={
            "error_type": "FYERS_RATE_LIMIT",
            "message": str(e),
            "action": "Wait 60 seconds and try again.",
        })

    except FyersAPIError as e:
        raise HTTPException(status_code=502, detail={
            "error_type": "FYERS_API_ERROR",
            "message": str(e),
            "action": "Check backend logs for details.",
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "error_type": "SCANNER_ERROR",
            "message": str(e),
            "action": "Check backend logs for details.",
        })


@router.get("/scan/latest")
def get_latest_scan():
    data = load_latest_scan()
    logger = logging.getLogger("scan.db")
    if data is None:
        logger.info("API /scan/latest | available=False | DB is empty")
    else:
        items = data.get("items", [])
        logger.info("API /scan/latest | available=True | stocks=%s", len(items))
    if data is None:
        return {"available": False}
    return {"available": True, **data}
