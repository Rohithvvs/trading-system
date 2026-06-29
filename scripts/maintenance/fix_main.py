import sys
import asyncio

content = open('backend/app/main.py').read()

# Make sure we import SessionLocal
if 'from .db.session import AsyncSessionLocal, SessionLocal' not in content:
    content = content.replace('from .db.session import AsyncSessionLocal', 'from .db.session import AsyncSessionLocal, SessionLocal')

old_code = """                    # Check price alerts as well
                    try:
                        alerts = await service.get_active_alerts()
                        for a in alerts:
                            try:
                                ltp = await asyncio.to_thread(fyers.fetch_ltp, a.symbol)
                                if ltp is None:
                                    candles = await asyncio.to_thread(
                                        fyers.fetch_ohlcv, a.symbol, AnalysisMode.swing, "1d", 2
                                    )
                                    if candles and len(candles) > 0:
                                        ltp = candles[-1].close
                                    else:
                                        logger.warning("No price data available for alert %s; skipping", a.symbol)
                                        continue
                                if a.condition == ">=" and ltp >= a.target_price:
                                    await service.trigger_alert(a.id, ltp)
                                elif a.condition == "<=" and ltp <= a.target_price:
                                    await service.trigger_alert(a.id, ltp)
                            except Exception:
                                logger.exception("Error monitoring alert %s", a.symbol)
                    except Exception:
                        logger.exception("Failed to check price alerts")"""

new_code = """                    # Check price alerts as well
                    try:
                        def _get_alerts():
                            with SessionLocal() as s:
                                # We map the sqlalchemy models to dictionaries so we don't hold the session
                                return [{"id": x.id, "symbol": x.symbol, "condition": x.condition, "target_price": x.target_price} for x in PaperTradingService(s).get_active_alerts()]
                        
                        alerts = await asyncio.to_thread(_get_alerts)
                        for a in alerts:
                            try:
                                ltp_coro = fyers.fetch_ltp(a["symbol"])
                                if asyncio.iscoroutine(ltp_coro): ltp = await ltp_coro
                                else: ltp = ltp_coro

                                if ltp is None:
                                    candles = await asyncio.to_thread(
                                        fyers.fetch_ohlcv, a["symbol"], AnalysisMode.swing, "1d", 2
                                    )
                                    if candles and len(candles) > 0:
                                        ltp = candles[-1].close
                                    else:
                                        logger.warning("No price data available for alert %s; skipping", a["symbol"])
                                        continue
                                if a["condition"] == ">=" and ltp >= a["target_price"]:
                                    def _trigger(aid, val):
                                        with SessionLocal() as s:
                                            PaperTradingService(s).trigger_alert(aid, val)
                                    await asyncio.to_thread(_trigger, a["id"], ltp)
                                elif a["condition"] == "<=" and ltp <= a["target_price"]:
                                    def _trigger(aid, val):
                                        with SessionLocal() as s:
                                            PaperTradingService(s).trigger_alert(aid, val)
                                    await asyncio.to_thread(_trigger, a["id"], ltp)
                            except Exception:
                                logger.exception("Error monitoring alert %s", a["symbol"])
                    except Exception:
                        logger.exception("Failed to check price alerts")"""

content = content.replace(old_code, new_code)

with open('backend/app/main.py', 'w') as f:
    f.write(content)
