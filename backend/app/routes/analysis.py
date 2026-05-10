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
from backend.app.services import candle_store 
from ..utils import get_logger
from fastapi import HTTPException
from backend.app.services.fyers_service import (
    FyersAuthExpiredError,
    FyersAuthInvalidError,
    FyersRateLimitError,
    FyersAPIError,
)

from ..services.technical_analysis_service import TechnicalAnalysisService
from ..services.market_info_service import MarketInfoService
from ..services.news_service import NewsService
from ..services.backtest_service import BacktestService


router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = get_logger("backend.app.routes.analysis")


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


@router.get("/symbol/{symbol}/detail")
def symbol_detail(symbol: str, db: Session = Depends(get_db)):
    """Run a single-symbol full analysis and return enriched fields used by the frontend detail page.

    This endpoint runs the same full analysis flow but also computes additional derived
    metrics (52-week high/low, ATR + volatility class, Bollinger status, weekly alignment,
    backtest extended metrics, corporate events when available, and supertrend flip points).
    """
    from ..schemas import AnalysisRequest, TimeframeConfig, AnalysisMode

    cfg = TimeframeConfig()
    req = AnalysisRequest(symbols=[symbol.strip().upper()], mode=AnalysisMode.both, timeframe=cfg)
    try:
        response = RouterAgent(db).full_analysis(req)

        if not response.items:
            return JSONResponse(content={"error": "no_data"})

        item = response.items[0]

        # Compute 52-week high/low (approx 260 trading days)
        try:
            ohlcv = item.ohlcv or []
            highs = [p.high for p in ohlcv[-260:]] if ohlcv else []
            lows = [p.low for p in ohlcv[-260:]] if ohlcv else []
            year52_high = max(highs) if highs else None
            year52_low = min(lows) if lows else None
        except Exception:
            year52_high = None
            year52_low = None

        # Technical extras: ATR and Bollinger (computed from primary ohlcv)
        tech_extra: dict = {}
        try:
            df_rows = []
            for p in item.ohlcv:
                df_rows.append({"timestamp": p.timestamp, "open": p.open, "high": p.high, "low": p.low, "close": p.close, "volume": p.volume})
            import pandas as pd
            df = pd.DataFrame(df_rows)
            if not df.empty:
                from ta.volatility import AverageTrueRange, BollingerBands

                atr = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14).average_true_range().iloc[-1]
                close = float(df["close"].iloc[-1])
                atr_pct = (atr / close) * 100 if close else 0.0
                if atr_pct < 1.0:
                    atr_class = "low"
                elif atr_pct < 2.0:
                    atr_class = "medium"
                else:
                    atr_class = "high"

                bb = BollingerBands(close=df["close"], window=20, window_dev=2)
                upper = float(bb.bollinger_hband().iloc[-1])
                lower = float(bb.bollinger_lband().iloc[-1])
                percent = (close - lower) / (upper - lower) if (upper - lower) != 0 else 0.5
                if percent < 0:
                    bb_status = "below_lower"
                elif percent < 0.25:
                    bb_status = "near_lower"
                elif percent < 0.75:
                    bb_status = "mid"
                elif percent <= 1.0:
                    bb_status = "near_upper"
                else:
                    bb_status = "above_upper"

                # Weekly alignment: resample to weekly OHLC and run a quick trend check
                if not df.empty:
                    df.set_index("timestamp", inplace=True)
                    weekly = df.resample("W").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
                    daily_signal = item.technical[0].signal if item.technical else "unknown"
                    weekly_signal = "unknown"
                    if not weekly.empty:
                        last_week_close = weekly["close"].iloc[-1]
                        sma_20 = weekly["close"].rolling(20).mean().iloc[-1] if len(weekly) >= 20 else None
                        if sma_20 is not None:
                            weekly_signal = "bullish" if last_week_close > sma_20 else "bearish"

                tech_extra = {
                    "atr": round(float(atr), 4) if df is not None and not df.empty else None,
                    "atr_pct": round(float(atr_pct), 3) if df is not None and not df.empty else None,
                    "atr_class": atr_class,
                    "bollinger_status": bb_status,
                    "multi_timeframe": {"daily": daily_signal, "weekly": weekly_signal},
                }
        except Exception:
            tech_extra = {}

        # Backtest extras: the backtest result already includes extended metrics from service
        backtest_extra: dict = {}
        try:
            backtests = item.backtests or []
            if backtests:
                # take swing/backtest if available
                best = max(backtests, key=lambda b: getattr(b, "total_return", 0))
                backtest_extra = {
                    "total_return": best.total_return,
                    "cagr": best.cagr,
                    "max_drawdown": best.max_drawdown,
                    "win_rate": best.win_rate,
                    "profit_factor": best.profit_factor,
                    "trade_count": best.trade_count,
                    "equity_curve": best.equity_curve,
                    "monthly_returns": getattr(best, "monthly_returns", []),
                    "sharpe_ratio": getattr(best, "sharpe_ratio", 0.0),
                    "best_trade": getattr(best, "best_trade", None),
                    "worst_trade": getattr(best, "worst_trade", None),
                }
        except Exception:
            backtest_extra = {}

        # Company info & corporate events (best-effort via MarketInfoService)
        company_info = {}
        try:
            mis = MarketInfoService()
            profile = mis.get_company_profile(symbol)
            if profile:
                company_info = profile
        except Exception:
            company_info = {}

        # News fallback & social sentiment already roughly handled by NewsAgent; include corporate events
        news_extra = {"corporate_events": company_info.get("corporate_events") if isinstance(company_info, dict) else None, "social_sentiment": item.news_sentiment_score}

        payload = item.model_dump() if hasattr(item, "model_dump") else item
        payload.update({
            "year52_high": year52_high,
            "year52_low": year52_low,
            "sector": company_info.get("sector") if isinstance(company_info, dict) else None,
            "industry": company_info.get("industry") if isinstance(company_info, dict) else None,
            "market_cap": company_info.get("market_cap") if isinstance(company_info, dict) else None,
            "technical_extras": tech_extra,
            "backtest_extras": backtest_extra,
            "news_extras": news_extra,
        })

        return JSONResponse(content=sanitize_for_json(payload))

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
        logger.exception("Error in /symbol/%s/detail: %s", symbol, str(e))
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
