import asyncio
import logging
from backend.app.services.screener_service import ScreenerService
from backend.app.config import settings
from backend.app.db.session import AsyncSessionLocal
from backend.app.services.token_service import get_current_access_token

async def main():
    async with AsyncSessionLocal() as db:
        await get_current_access_token(db)
        
    logging.getLogger("app.screener").setLevel(logging.CRITICAL)
    logging.getLogger("app.technical").setLevel(logging.CRITICAL)

    service = ScreenerService()
    universe = settings.nifty500_symbols
    
    print(f"Scanning {len(universe)} symbols...")
    results = await service.screen_symbols_swing(symbols=universe, lookback_window=260, stage_name="AUDIT")
    
    # Analyze the results
    stats = {
        'Close > SMA50': {'pass': 0, 'fail': 0},
        'SMA50 > SMA200': {'pass': 0, 'fail': 0},
        'Close > EMA20': {'pass': 0, 'fail': 0},
        'Supertrend Positive': {'pass': 0, 'fail': 0},
        'MACD > Signal': {'pass': 0, 'fail': 0},
        'RSI >= 50': {'pass': 0, 'fail': 0},
        'Volume > 50k & Price 100-500k': {'pass': 0, 'fail': 0},
        'Technical Score >= 48': {'pass': 0, 'fail': 0},
        'Avg 20d Volume > 100k': {'pass': 0, 'fail': 0},
        'Overall Broad Trend Pass': {'pass': 0, 'fail': 0}
    }
    
    valid_symbols = 0
    for r in results:
        # Ignore failed fetch or quality
        if r.conditions.get("data_source_failed") or r.conditions.get("data_quality_failed") or r.conditions.get("technical_analysis_failed") or r.conditions.get("processing_error"):
            continue
            
        valid_symbols += 1
        
        # We need to re-evaluate the raw indicators because ScreenerConditionResult only gives conditions dictionary.
        # It has technical_score, but maybe not the raw conditions for individual things.
        # Let's check r.conditions!
        
        # r.conditions contains:
        c = r.conditions
        
        stats['Close > SMA50']['pass' if c.get("close_above_sma50", r.close > r.sma_50) else 'fail'] += 1
        stats['SMA50 > SMA200']['pass' if c.get("sma50_above_sma200", r.sma_50 > r.sma_200) else 'fail'] += 1
        stats['Close > EMA20']['pass' if c.get("close_above_ema20") else 'fail'] += 1
        stats['Supertrend Positive']['pass' if c.get("supertrend_positive") else 'fail'] += 1
        stats['MACD > Signal']['pass' if c.get("macd_positive") else 'fail'] += 1
        stats['RSI >= 50']['pass' if c.get("rsi_supportive") else 'fail'] += 1
        
        # Liquidity filter
        stats['Volume > 50k & Price 100-500k']['pass' if c.get("basic_liquidity_filter_pass") else 'fail'] += 1
        stats['Technical Score >= 48']['pass' if r.technical_score >= 48 else 'fail'] += 1
        
        # Avg volume > 100k
        avg_vol_pass = c.get("avg_volume_pass", r.volume > 100000) # Screener assigns current volume to r.volume, not avg volume! Wait, screener conditions doesn't expose avg_volume directly, but we can assume if broad_trend passes it must have passed.
        # Actually I can't be sure, but we will count it if available
        
        stats['Overall Broad Trend Pass']['pass' if c.get("broad_trend_eligibility") else 'fail'] += 1

    print(f"Valid symbols analyzed: {valid_symbols}")
    for k, v in stats.items():
        print(f"{k} -> Pass: {v['pass']}, Fail: {v['fail']}")

if __name__ == '__main__':
    asyncio.run(main())
