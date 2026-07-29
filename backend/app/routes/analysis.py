from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
import asyncio
import json
import time
from sqlalchemy.ext.asyncio import AsyncSession

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

from ..utils import sanitize_for_json, safe_int
from ..services import candle_store
from ..utils import get_logger
from fastapi import HTTPException
from ..services.fyers_service import (
    FyersAuthExpiredError,
    FyersAuthInvalidError,
    FyersRateLimitError,
    FyersAPIError,
    FyersService,
)

from ..services.market_info_service import MarketInfoService
from ..services.workstation_service import WorkstationService



router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = get_logger("app.routes.analysis")


@router.post("/technical", response_model=AnalysisResponse)
def technical_analysis(payload: AnalysisRequest, db: AsyncSession = Depends(get_db)) -> AnalysisResponse:
    response = RouterAgent(db).technical_only(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/news", response_model=AnalysisResponse)
def news_analysis(payload: AnalysisRequest, db: AsyncSession = Depends(get_db)) -> AnalysisResponse:
    response = RouterAgent(db).news_only(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/backtest", response_model=AnalysisResponse)
def backtest_analysis(payload: AnalysisRequest, db: AsyncSession = Depends(get_db)) -> AnalysisResponse:
    response = RouterAgent(db).backtest_only(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/final-recommendation", response_model=AnalysisResponse)
def final_recommendation(payload: AnalysisRequest, db: AsyncSession = Depends(get_db)) -> AnalysisResponse:
    response = RouterAgent(db).final_recommendation(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/full", response_model=FullAnalysisResponse)
async def full_analysis(payload: AnalysisRequest, db: AsyncSession = Depends(get_db)) -> FullAnalysisResponse:
    logger.info(
        "API ENTRY | endpoint=/analysis/full | symbols=%s | mode=%s | intraday=%s | swing=%s | lookback=%s",
        len(payload.symbols),
        payload.mode.value,
        payload.timeframe.intraday,
        payload.timeframe.swing,
        payload.timeframe.lookback_window,
    )
    response = await RouterAgent(db).full_analysis(payload)
    logger.info(
        "API EXIT | endpoint=/analysis/full | analyzed=%s | generated_at=%s",
        len(response.items),
        response.generated_at.isoformat(),
    )
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/rankings", response_model=RankingsResponse)
def rankings(payload: AnalysisRequest, db: AsyncSession = Depends(get_db)) -> RankingsResponse:
    response = RouterAgent(db).rankings(payload)
    return JSONResponse(content=sanitize_for_json(response.model_dump(mode="json")))


@router.post("/screener/full")
async def screener_full(payload: ScreenerRequest):
    logger.info(
        "[SCAN] API ENTRY | endpoint=/analysis/screener/full | mode=%s | top_n=%s | lookback=%s | swing=%s | custom_symbols=%s",
        payload.mode.value,
        payload.top_n,
        payload.timeframe.lookback_window,
        payload.timeframe.swing,
        len(payload.symbols),
    )

    q: asyncio.Queue = asyncio.Queue(maxsize=200)

    # Seed the queue immediately so the SSE stream has something to send as soon
    # as the client connects — never leave the UI at "Connecting data feed..."
    # with no server events while the lock/DB is still starting.
    await q.put(
        {
            "stage": "Connecting data feed...",
            "progress": 1,
            "heartbeat": True,
        }
    )

    from ..services.scan_execution_service import ScanExecutionService
    from ..services.lock_service import LockAcquisitionError

    try:
        await ScanExecutionService.execute_scan(payload, progress_queue=q, trigger_source="ui")
        logger.info("[SCAN] Worker started; opening SSE stream")
    except LockAcquisitionError as lock_exc:
        logger.warning("[SCAN] Lock denied | reason=%s", lock_exc)
        return JSONResponse(
            status_code=200,
            content={
                "status": "scan_in_progress",
                "message": str(lock_exc) or "Scan is already in progress.",
            },
        )
    except Exception as start_exc:
        logger.exception("[SCAN] Failed to start scan worker: %s", start_exc)
        await q.put(
            {
                "status": "error",
                "message": f"Failed to start scanner: {start_exc}",
            }
        )

    async def event_stream():
        """SSE generator with server-side heartbeat to prevent proxy timeouts.

        Yields structured progress events (not only comment keepalives) so the
        frontend can leave "Connecting data feed..." and show real stages.
        """
        import time as _time

        last_yield_time = _time.monotonic()
        HEARTBEAT_INTERVAL = 5.0
        idle_ticks = 0

        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_INTERVAL)
                idle_ticks = 0
                if "status" in msg and msg["status"] in ("complete", "error"):
                    if "elapsed_sec" not in msg:
                        msg["elapsed_sec"] = round(_time.monotonic() - last_yield_time, 1)
                    yield f"event: result\ndata: {json.dumps(msg)}\n\n"
                    break
                else:
                    if "heartbeat" not in msg:
                        msg["heartbeat"] = True
                    if not msg.get("stage"):
                        msg["stage"] = "Scanning..."
                    yield f"event: progress\ndata: {json.dumps(msg)}\n\n"
                    last_yield_time = _time.monotonic()
            except asyncio.TimeoutError:
                idle_ticks += 1
                # Prefer a real progress event over a silent SSE comment so the
                # UI updates instead of freezing at Connecting data feed...
                wait_msg = {
                    "stage": (
                        "Waiting for broker response..."
                        if idle_ticks >= 6
                        else "Connecting data feed..."
                    ),
                    "progress": min(5 + idle_ticks, 12),
                    "heartbeat": True,
                    "idle_ticks": idle_ticks,
                }
                if idle_ticks >= 6:
                    logger.warning(
                        "[SCAN] SSE idle %ss — still waiting for worker progress",
                        idle_ticks * HEARTBEAT_INTERVAL,
                    )
                yield f"event: progress\ndata: {json.dumps(wait_msg)}\n\n"
                # Comment keepalive for proxies that ignore event frames
                yield f": heartbeat {_time.time():.0f}\n\n"
                last_yield_time = _time.monotonic()

    response = StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )
    return response


@router.get("/symbol/{symbol}/detail")
async def symbol_detail(symbol: str, db: AsyncSession = Depends(get_db)):
    """Run a single-symbol full analysis and return enriched fields used by the frontend detail page.

    This endpoint runs the same full analysis flow but also computes additional derived
    metrics (52-week high/low, ATR + volatility class, Bollinger status, weekly alignment,
    backtest extended metrics, corporate events when available, and supertrend flip points).
    """
    from ..schemas import AnalysisRequest, TimeframeConfig, AnalysisMode

    cfg = TimeframeConfig()
    req = AnalysisRequest(symbols=[symbol.strip().upper()], mode=AnalysisMode.swing, timeframe=cfg)
    start_t = time.time()
    try:
        logger.info("SYMBOL_DETAIL_START | symbol=%s", symbol)
        response = await RouterAgent(db).full_analysis(req)

        if not response.items:
            return JSONResponse(content={"error": "no_data"})

        item = response.items[0]
        ohlcv = item.ohlcv or []

        # Parallel execution for faster response
        import asyncio as _asyncio

        async def _compute_52wk():
            return _calculate_52_week_range(ohlcv)

        async def _compute_tech_extras():
            return _build_technical_extras(symbol, item, ohlcv)

        async def _compute_backtest_extras():
            return _build_backtest_extras(item.backtests or [])

        async def _fetch_company_info():
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
            except Exception:
                pass
            return company_info

        (
            (year52_high, year52_low),
            tech_extra,
            backtest_extra,
            company_info,
        ) = await _asyncio.gather(
            _compute_52wk(),
            _compute_tech_extras(),
            _compute_backtest_extras(),
            _fetch_company_info(),
        )

        news_extra = {"corporate_events": company_info.get("corporate_events") if isinstance(company_info, dict) else None, "social_sentiment": item.news_sentiment_score}

        # Build research payload (may be heavy - run in background if needed)
        research_payload = {}
        try:
            from ..services.research_service import ResearchService

            research_payload = ResearchService().build(
                symbol=symbol,
                item=item,
                ohlcv=ohlcv,
                company_info=company_info if isinstance(company_info, dict) else {},
                tech_extra=tech_extra if isinstance(tech_extra, dict) else {},
                backtest_extra=backtest_extra if isinstance(backtest_extra, dict) else {},
            )
        except Exception as research_err:
            logger.exception("research payload failed for %s: %s", symbol, research_err)
            research_payload = {
                "error": "research_unavailable",
                "message": str(research_err),
                "disclaimer": "Research module failed; existing analysis fields remain available.",
            }

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
            "research": research_payload,
        })

        elapsed = int((time.time() - start_t) * 1000)
        logger.info("SYMBOL_DETAIL_COMPLETE | symbol=%s | duration_ms=%s | has_research=%s", symbol, elapsed, bool(research_payload.get("swing_score")))

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
        logger.exception("Research failed for symbol=%s: %s", symbol, str(e))
        raise HTTPException(status_code=500, detail={
            "error_type": "SCANNER_ERROR",
            "message": "Unable to load research. Please retry. If the issue persists, check your broker connection.",
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
                    "volume": safe_int(point.volume, field="volume"),
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


CACHE_KEY_ANALYSIS_SCAN_LATEST = "analysis:scan:latest:v1"
ENDPOINT_ANALYSIS_SCAN_LATEST = "/analysis/scan/latest"


@router.get("/scan/latest")
async def get_latest_scan(
    request: Request,
    force: bool = Query(default=False, description="Force refresh cache"),
    db: AsyncSession = Depends(get_db),
):
    from ..services.scanner_cache_service import scanner_cache_service, wants_force_refresh
    from ..services.latest_scan_service import LatestScanService
    from ..config.settings import settings
    from ..observability.metrics import (
        record_scanner_cache_force_refresh,
        record_scanner_cache_hit,
        record_scanner_cache_miss,
        record_unified_latest_fallback,
    )

    force_refresh = wants_force_refresh(force, request.headers.get("cache-control"))
    cache_enabled = settings.is_scanner_latest_cache_enabled()
    scan_logger = logging.getLogger("scan.db")

    # Record force once at the route boundary (covers unified + legacy; no double-count).
    if force_refresh and cache_enabled:
        record_scanner_cache_force_refresh(ENDPOINT_ANALYSIS_SCAN_LATEST)

    if settings.is_scanner_unified_latest_enabled():
        try:
            service = LatestScanService(db)
            payload, cache_status = await service.get_latest_scan(
                format_type="analysis",
                force=force_refresh,
                cache_enabled=cache_enabled,
            )
            return Response(
                content=payload,
                media_type="application/json",
                headers={"X-Cache-Status": cache_status},
            )
        except Exception as exc:
            record_unified_latest_fallback(ENDPOINT_ANALYSIS_SCAN_LATEST)
            logger.error(
                "Unified GET /analysis/scan/latest failed, falling back to legacy path | err=%s",
                exc,
                exc_info=True,
            )

    async def produce_json() -> str:
        data = await load_latest_scan()
        if data is None:
            scan_logger.info("API /scan/latest | available=False | DB is empty")
            empty_payload = json.dumps({"available": False})
            if cache_enabled:
                await scanner_cache_service.set_latest_scan(
                    CACHE_KEY_ANALYSIS_SCAN_LATEST, empty_payload, ttl_seconds=10
                )
            return empty_payload

        items = data.get("items", [])
        scan_logger.info("API /scan/latest | available=True | stocks=%s", len(items))
        serialized_payload = json.dumps({"available": True, **data})
        if cache_enabled:
            await scanner_cache_service.set_latest_scan(
                CACHE_KEY_ANALYSIS_SCAN_LATEST, serialized_payload
            )
        return serialized_payload

    payload, cache_status = await scanner_cache_service.resolve_latest_scan(
        CACHE_KEY_ANALYSIS_SCAN_LATEST,
        produce_json,
        force=force_refresh,
        cache_enabled=cache_enabled,
    )

    if cache_status == "HIT":
        record_scanner_cache_hit(ENDPOINT_ANALYSIS_SCAN_LATEST)
    elif cache_status in ("MISS", "FALLBACK"):
        record_scanner_cache_miss(ENDPOINT_ANALYSIS_SCAN_LATEST)

    return Response(
        content=payload,
        media_type="application/json",
        headers={"X-Cache-Status": cache_status},
    )


@router.get("/symbol/{symbol}/light")
async def symbol_detail_light(symbol: str, db: AsyncSession = Depends(get_db)):
    """Lightweight research data for prefetching. Returns company name, price, and mini chart data only.
    Fast response (<500ms) for instant navigation feel.
    """
    from ..schemas import AnalysisRequest, TimeframeConfig, AnalysisMode

    cfg = TimeframeConfig(lookback_window=60)
    req = AnalysisRequest(symbols=[symbol.strip().upper()], mode=AnalysisMode.swing, timeframe=cfg)
    start_t = time.time()
    try:
        response = await RouterAgent(db).full_analysis(req)
        elapsed = int((time.time() - start_t) * 1000)
        logger.info("SYMBOL_LIGHT_COMPLETE | symbol=%s | duration_ms=%s", symbol, elapsed)

        if not response.items:
            return JSONResponse(content={"symbol": symbol, "error": "no_data"})

        item = response.items[0]
        ohlcv = item.ohlcv or []
        last_candle = ohlcv[-1] if ohlcv else None

        mini_chart = []
        if len(ohlcv) > 0:
            step = max(1, len(ohlcv) // 40)
            mini_chart = [
                {"t": str(p.timestamp), "c": float(p.close)}
                for p in ohlcv[::step][-40:]
                if hasattr(p, "close") and p.close
            ]

        payload = {
            "symbol": symbol,
            "ltp": float(last_candle.close) if last_candle and hasattr(last_candle, "close") else None,
            "change_pct": None,
            "company_name": None,
            "mini_chart": mini_chart,
        }

        try:
            from ..services.fyers_service import FyersService
            quote = await FyersService.shared().fetch_quote(symbol)
            if quote:
                payload["ltp"] = quote.get("ltp", payload["ltp"])
                payload["change_pct"] = quote.get("change_pct")
        except Exception:
            pass

        try:
            mis = MarketInfoService()
            profile = mis.get_company_profile(symbol)
            if profile:
                payload["company_name"] = profile.get("company_name") or profile.get("short_name") or profile.get("name")
        except Exception:
            pass

        return JSONResponse(content=sanitize_for_json(payload))
    except Exception as exc:
        logger.warning("SYMBOL_LIGHT_FAILED | symbol=%s | error=%s", symbol, str(exc)[:120])
        return JSONResponse(content={"symbol": symbol, "error": str(exc)[:120]})


@router.post("/symbol/batch-light")
async def symbol_batch_light(payload: dict, db: AsyncSession = Depends(get_db)):
    """Batch lightweight research data for multiple symbols. Used for preheating frontend cache."""
    symbols = payload.get("symbols", [])
    if not symbols or not isinstance(symbols, list):
        return JSONResponse(content={"symbols": []})
    symbols = [s.strip().upper() for s in symbols[:20]]

    from ..services.fyers_service import FyersService as _FyersService
    from ..services.market_info_service import MarketInfoService as _MarketInfoService

    fyers = _FyersService.shared()
    mis = _MarketInfoService()
    results = []

    for sym in symbols:
        try:
            item = {"symbol": sym, "ltp": None, "change_pct": None, "company_name": None}
            quote = await fyers.fetch_quote(sym)
            if quote:
                item["ltp"] = quote.get("ltp")
                item["change_pct"] = quote.get("change_pct")
            try:
                profile = mis.get_company_profile(sym)
                if profile:
                    item["company_name"] = profile.get("company_name") or profile.get("short_name") or profile.get("name")
            except Exception:
                pass
            results.append(item)
        except Exception:
            results.append({"symbol": sym, "ltp": None, "change_pct": None, "company_name": None})

    return JSONResponse(content={"symbols": results})


@router.get("/candidates/today")
async def get_today_candidates(db: AsyncSession = Depends(get_db)):
    from ..models.analysis import ScannedCandidate
    from sqlalchemy import select
    from datetime import datetime, timezone
    
    today = datetime.now(timezone.utc).date()
    start_of_today = datetime.combine(today, datetime.min.time())
    
    res = await db.scalars(
        select(ScannedCandidate)
        .where(ScannedCandidate.scanned_at >= start_of_today)
        .order_by(ScannedCandidate.screener_score.desc())
    )
    candidates = res.all()
    
    return JSONResponse(content=[{
        "id": c.id,
        "symbol": c.symbol,
        "scanned_at": c.scanned_at.isoformat(),
        "screener_name": c.screener_name,
        "technical_score": c.technical_score,
        "technical_signal": c.technical_signal,
        "screener_score": c.screener_score,
        "matched": c.matched
    } for c in candidates])
