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
from ..services import candle_store
from ..utils import get_logger
from fastapi import HTTPException
from ..services.fyers_service import (
    FyersAuthExpiredError,
    FyersAuthInvalidError,
    FyersRateLimitError,
    FyersAPIError,
)

from ..services.technical_analysis_service import TechnicalAnalysisService
from ..services.market_info_service import MarketInfoService
from ..services.news_service import NewsService
from ..services.backtest_service import BacktestService
from ..services.workstation_service import WorkstationService


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
    try:
        universe = "CUSTOM" if payload.symbols else "NIFTY500"
        WorkstationService(db).record_scan_history(
            result,
            scan_name="Manual Scan",
            mode=payload.mode.value,
            timeframe=payload.timeframe.swing,
            lookback_window=payload.timeframe.lookback_window,
            top_n=payload.top_n,
            universe=universe,
        )
    except Exception:
        logger.exception("Failed to persist scan history snapshot")
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

    # The detail page is a swing-trading view. Running `both` can make the
    # response look empty when intraday candles are unavailable in production,
    # or when an empty 0% intraday backtest is selected over a real swing test.
    cfg = TimeframeConfig()
    req = AnalysisRequest(symbols=[symbol.strip().upper()], mode=AnalysisMode.swing, timeframe=cfg)
    try:
        response = RouterAgent(db).full_analysis(req)

        if not response.items:
            return JSONResponse(content={"error": "no_data"})

        item = response.items[0]

        ohlcv = item.ohlcv or []
        year52_high, year52_low = _calculate_52_week_range(ohlcv)
        tech_extra = _build_technical_extras(symbol, item, ohlcv)

        backtest_extra = _build_backtest_extras(item.backtests or [])

        # Company info & corporate events (best-effort via MarketInfoService)
        company_info = {}
        try:
            mis = MarketInfoService()
            profile = mis.get_company_profile(symbol)
            if profile:
                company_info = profile
        except Exception:
            company_info = {}
        try:
            quote_profile = FyersService().fetch_quote_profile(symbol)
            company_info = {**quote_profile, **{key: value for key, value in company_info.items() if value not in (None, "", {})}}
            year52_high = year52_high or quote_profile.get("year52_high")
            year52_low = year52_low or quote_profile.get("year52_low")
        except Exception:
            pass

        # News fallback & social sentiment already roughly handled by NewsAgent; include corporate events
        news_extra = {"corporate_events": company_info.get("corporate_events") if isinstance(company_info, dict) else None, "social_sentiment": item.news_sentiment_score}

        payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        payload.update({
            "year52_high": year52_high,
            "year52_low": year52_low,
            "52_week_high": year52_high,
            "52_week_low": year52_low,
            "company_name": company_info.get("company_name") if isinstance(company_info, dict) else None,
            "company_description": company_info.get("company_description") if isinstance(company_info, dict) else None,
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


def _calculate_52_week_range(ohlcv: list) -> tuple[float | None, float | None]:
    try:
        highs = [float(point.high) for point in ohlcv[-260:] if getattr(point, "high", None) is not None]
        lows = [float(point.low) for point in ohlcv[-260:] if getattr(point, "low", None) is not None]
        return (max(highs) if highs else None, min(lows) if lows else None)
    except Exception:
        return None, None


def _build_technical_extras(symbol: str, item, ohlcv: list) -> dict:
    if len(ohlcv) < 20:
        return {
            "atr": None,
            "atr_pct": None,
            "atr_class": None,
            "bollinger_status": None,
            "bollinger_position": None,
            "multi_timeframe": {"daily": _swing_signal(item), "weekly": None},
        }

    try:
        import pandas as pd
        from ta.volatility import AverageTrueRange, BollingerBands

        df = pd.DataFrame(
            [
                {
                    "timestamp": point.timestamp,
                    "open": float(point.open),
                    "high": float(point.high),
                    "low": float(point.low),
                    "close": float(point.close),
                    "volume": int(point.volume),
                }
                for point in ohlcv
            ]
        ).dropna(subset=["timestamp", "high", "low", "close"])
        if df.empty or len(df) < 20:
            return {}

        atr_series = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14).average_true_range()
        atr = float(atr_series.iloc[-1])
        close = float(df["close"].iloc[-1])
        atr_pct = (atr / close) * 100 if close else 0.0
        atr_class = "low" if atr_pct < 1.0 else "medium" if atr_pct < 2.0 else "high"

        bb = BollingerBands(close=df["close"], window=20, window_dev=2)
        upper = float(bb.bollinger_hband().iloc[-1])
        lower = float(bb.bollinger_lband().iloc[-1])
        percent = (close - lower) / (upper - lower) if (upper - lower) else 0.5
        if percent < 0:
            bollinger_status = "below_lower"
        elif percent < 0.25:
            bollinger_status = "near_lower"
        elif percent < 0.75:
            bollinger_status = "mid"
        elif percent <= 1.0:
            bollinger_status = "near_upper"
        else:
            bollinger_status = "above_upper"

        weekly_signal = None
        try:
            indexed = df.set_index(pd.to_datetime(df["timestamp"]))
            weekly = indexed.resample("W").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
            if len(weekly) >= 20:
                last_week_close = float(weekly["close"].iloc[-1])
                sma_20 = float(weekly["close"].rolling(20).mean().iloc[-1])
                weekly_signal = "bullish" if last_week_close > sma_20 else "bearish"
            elif len(weekly) >= 2:
                weekly_signal = "bullish" if float(weekly["close"].iloc[-1]) >= float(weekly["close"].iloc[0]) else "bearish"
        except Exception:
            weekly_signal = None

        daily_signal = _swing_signal(item)
        return {
            "atr": round(atr, 4),
            "atr_pct": round(atr_pct, 3),
            "atr_class": atr_class,
            "bollinger_status": bollinger_status,
            "bollinger_position": bollinger_status,
            "multi_timeframe": {"daily": daily_signal, "weekly": weekly_signal},
        }
    except Exception as exc:
        logger.warning("tech_extra failed for symbol=%s error=%s", symbol, str(exc))
        return {}


def _swing_signal(item) -> str | None:
    try:
        swing = next((tech for tech in item.technical if getattr(tech, "mode", None).value == "swing"), None)
        return getattr(swing or item.technical[0], "signal", None) if item.technical else None
    except Exception:
        return None


def _build_backtest_extras(backtests: list) -> dict:
    if not backtests:
        return {}
    try:
        selected = next((test for test in backtests if getattr(getattr(test, "mode", None), "value", None) == "swing"), None) or backtests[0]
        return {
            "mode": getattr(getattr(selected, "mode", None), "value", getattr(selected, "mode", None)),
            "strategy_name": selected.strategy_name,
            "total_return": selected.total_return,
            "avg_return": selected.total_return,
            "cagr": selected.cagr,
            "max_drawdown": selected.max_drawdown,
            "win_rate": selected.win_rate,
            "profit_factor": selected.profit_factor,
            "trade_count": selected.trade_count,
            "total_trades": selected.trade_count,
            "verdict": selected.verdict,
            "equity_curve": selected.equity_curve,
            "monthly_returns": getattr(selected, "monthly_returns", []),
            "sharpe_ratio": getattr(selected, "sharpe_ratio", 0.0),
            "sharpe": getattr(selected, "sharpe_ratio", 0.0),
            "best_trade": getattr(selected, "best_trade", None),
            "worst_trade": getattr(selected, "worst_trade", None),
            "trades": getattr(selected, "trades", []),
        }
    except Exception:
        return {}


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
