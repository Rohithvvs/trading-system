import pytest
import pandas as pd
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock

from app.schemas import FinalRecommendation, RecommendationReasoning
from app.services.market_permission_service import MarketPermissionService
from app.agents.orchestrator_agent import OrchestratorAgent
from app.models.analysis import AnalysisHistory
from sqlalchemy import select

# Helper to create daily index candles
def create_mock_daily_candles(start_date: datetime, count: int, closes: list[float]) -> pd.DataFrame:
    dates = [start_date - timedelta(days=i) for i in range(count)]
    dates.reverse()
    
    data = []
    for i, dt in enumerate(dates):
        price = closes[i]
        data.append({
            "open": price * 0.99,
            "high": price * 1.01,
            "low": price * 0.98,
            "close": price,
            "volume": 50000
        })
    df = pd.DataFrame(data, index=dates)
    return df

@pytest.mark.anyio
@patch("app.services.market_permission_service.MarketPermissionService._load_candles")
async def test_market_regime_favorable(mock_load):
    # FAVORABLE: Nifty bullish (close > ema50), VIX low (<18), Breadth healthy (>= 50%)
    scan_date = datetime(2026, 7, 10)
    
    # 60 days of stable/rising prices
    nifty_closes = [10000.0] * 50 + [10100.0] * 10
    vix_closes = [15.0] * 60
    bench_closes = [100.0] * 50 + [105.0] * 10 # bullish bench
    
    nifty_df = create_mock_daily_candles(scan_date, 60, nifty_closes)
    vix_df = create_mock_daily_candles(scan_date, 60, vix_closes)
    bench_df = create_mock_daily_candles(scan_date, 60, bench_closes)
    
    def side_effect(symbol, is_index=False):
        if "NIFTY50" in symbol:
            return nifty_df
        if "INDIAVIX" in symbol:
            return vix_df
        # Return bench stock
        return bench_df
        
    mock_load.side_effect = side_effect
    
    service = MarketPermissionService()
    result = await service.evaluate_market_permission(scan_date)
    
    assert result.market_state == "FAVORABLE"
    assert result.trend_state == "BULLISH"
    assert result.volatility_state == "NORMAL"
    assert result.breadth_state == "HEALTHY"
    assert result.new_entry_allowed is True
    assert result.risk_multiplier == 1.0
    assert result.manual_review_flag is False

@pytest.mark.anyio
@patch("app.services.market_permission_service.MarketPermissionService._load_candles")
async def test_market_regime_cautious_vix_elevated(mock_load):
    # CAUTIOUS: VIX elevated (18-22), Nifty bullish, Breadth healthy
    scan_date = datetime(2026, 7, 10)
    
    nifty_closes = [10000.0] * 50 + [10100.0] * 10
    vix_closes = [15.0] * 50 + [20.0] * 10  # elevated VIX
    bench_closes = [100.0] * 50 + [101.0] * 10
    
    nifty_df = create_mock_daily_candles(scan_date, 60, nifty_closes)
    vix_df = create_mock_daily_candles(scan_date, 60, vix_closes)
    bench_df = create_mock_daily_candles(scan_date, 60, bench_closes)
    
    def side_effect(symbol, is_index=False):
        if "NIFTY50" in symbol:
            return nifty_df
        if "INDIAVIX" in symbol:
            return vix_df
        return bench_df
        
    mock_load.side_effect = side_effect
    
    service = MarketPermissionService()
    result = await service.evaluate_market_permission(scan_date)
    
    assert result.market_state == "CAUTIOUS"
    assert result.volatility_state == "ELEVATED"
    assert result.new_entry_allowed is True
    assert result.risk_multiplier == 0.5

@pytest.mark.anyio
@patch("app.services.market_permission_service.MarketPermissionService._load_candles")
async def test_market_regime_highrisk_bearish_trend(mock_load):
    # HIGHRISK: Nifty bearish (close < ema50)
    scan_date = datetime(2026, 7, 10)
    
    nifty_closes = [10000.0] * 50 + [9000.0] * 10  # Nifty drops below EMA
    vix_closes = [15.0] * 60
    bench_closes = [100.0] * 60
    
    nifty_df = create_mock_daily_candles(scan_date, 60, nifty_closes)
    vix_df = create_mock_daily_candles(scan_date, 60, vix_closes)
    bench_df = create_mock_daily_candles(scan_date, 60, bench_closes)
    
    def side_effect(symbol, is_index=False):
        if "NIFTY50" in symbol:
            return nifty_df
        if "INDIAVIX" in symbol:
            return vix_df
        return bench_df
        
    mock_load.side_effect = side_effect
    
    service = MarketPermissionService()
    result = await service.evaluate_market_permission(scan_date)
    
    assert result.market_state == "HIGHRISK"
    assert result.trend_state == "BEARISH"
    assert result.new_entry_allowed is False
    assert result.risk_multiplier == 0.0

@pytest.mark.anyio
@patch("app.services.market_permission_service.MarketPermissionService._load_candles")
async def test_market_regime_defensive_extreme_vix(mock_load):
    # DEFENSIVE: Extreme VIX (>= 30)
    scan_date = datetime(2026, 7, 10)
    
    nifty_closes = [10000.0] * 50 + [10100.0] * 10
    vix_closes = [15.0] * 50 + [32.0] * 10  # extreme VIX
    bench_closes = [100.0] * 50 + [101.0] * 10
    
    nifty_df = create_mock_daily_candles(scan_date, 60, nifty_closes)
    vix_df = create_mock_daily_candles(scan_date, 60, vix_closes)
    bench_df = create_mock_daily_candles(scan_date, 60, bench_closes)
    
    def side_effect(symbol, is_index=False):
        if "NIFTY50" in symbol:
            return nifty_df
        if "INDIAVIX" in symbol:
            return vix_df
        return bench_df
        
    mock_load.side_effect = side_effect
    
    service = MarketPermissionService()
    result = await service.evaluate_market_permission(scan_date)
    
    assert result.market_state == "DEFENSIVE"
    assert result.volatility_state == "EXTREME"
    assert result.new_entry_allowed is False
    assert result.risk_multiplier == 0.0
    assert result.manual_review_flag is True

@pytest.mark.anyio
@patch("app.services.market_permission_service.MarketPermissionService._load_candles")
async def test_market_regime_defensive_stale_data(mock_load):
    # DEFENSIVE: Nifty 50 data is stale (> 5 days old)
    scan_date = datetime(2026, 7, 10)
    
    nifty_closes = [10000.0] * 50 + [10100.0] * 10
    vix_closes = [15.0] * 60
    bench_closes = [100.0] * 50 + [101.0] * 10
    
    # Last candle of Nifty is on 2026-07-02 (8 calendar days stale)
    nifty_df = create_mock_daily_candles(datetime(2026, 7, 2), 60, nifty_closes)
    vix_df = create_mock_daily_candles(scan_date, 60, vix_closes)
    bench_df = create_mock_daily_candles(scan_date, 60, bench_closes)
    
    def side_effect(symbol, is_index=False):
        if "NIFTY50" in symbol:
            return nifty_df
        if "INDIAVIX" in symbol:
            return vix_df
        return bench_df
        
    mock_load.side_effect = side_effect
    
    service = MarketPermissionService()
    result = await service.evaluate_market_permission(scan_date)
    
    assert result.market_state == "DEFENSIVE"
    assert result.data_quality_flags["nifty_data_fresh"] is False
    assert result.new_entry_allowed is False

@pytest.mark.anyio
@patch("app.services.market_permission_service.MarketPermissionService._load_candles")
async def test_market_regime_fallback_missing_vix(mock_load):
    # Fallback: VIX missing (triggers CAUTIOUS due to missing volatility indicator)
    scan_date = datetime(2026, 7, 10)
    
    nifty_closes = [10000.0] * 50 + [10100.0] * 10
    bench_closes = [100.0] * 50 + [101.0] * 10
    
    nifty_df = create_mock_daily_candles(scan_date, 60, nifty_closes)
    bench_df = create_mock_daily_candles(scan_date, 60, bench_closes)
    
    def side_effect(symbol, is_index=False):
        if "NIFTY50" in symbol:
            return nifty_df
        if "INDIAVIX" in symbol:
            return pd.DataFrame()  # empty VIX
        return bench_df
        
    mock_load.side_effect = side_effect
    
    service = MarketPermissionService()
    result = await service.evaluate_market_permission(scan_date)
    
    assert result.market_state == "CAUTIOUS"
    assert result.volatility_state == "UNKNOWN"
    assert result.data_quality_flags["vix_data_present"] is False
    assert result.new_entry_allowed is True

@pytest.mark.anyio
@patch("app.services.market_permission_service.MarketPermissionService._load_candles")
async def test_market_permission_lookahead_bias(mock_load):
    # Prove no look-ahead bias: future candles (dated after scan_date) must be excluded
    scan_date = datetime(2026, 7, 10)
    
    # Daily Nifty closes
    # On 2026-07-10 (scan day): 10100.0 (bullish close > 10020 EMA)
    # On 2026-07-11 (future day): 8000.0 (extreme crash, would make trend BEARISH if leaked)
    
    start_date_utc = pd.Timestamp("2026-07-09 18:30:00", tz="UTC")  # IST: 2026-07-10
    future_date_utc = pd.Timestamp("2026-07-10 18:30:00", tz="UTC") # IST: 2026-07-11 (future day)
    
    timestamps = [start_date_utc - pd.Timedelta(days=i) for i in range(59)]
    timestamps.reverse()
    timestamps.append(future_date_utc) # append future crash day
    
    closes = [10000.0] * 49 + [10100.0] * 10 + [8000.0]  # future day crashes
    
    nifty_df = pd.DataFrame({
        "open": closes,
        "high": closes,
        "low": closes,
        "close": closes,
        "volume": [1000] * 60
    }, index=timestamps)
    
    # Also add a future VIX candle that is extreme (35.0) which would trigger DEFENSIVE if leaked
    vix_closes = [15.0] * 59 + [35.0]
    vix_df = pd.DataFrame({
        "open": vix_closes,
        "high": vix_closes,
        "low": vix_closes,
        "close": vix_closes,
        "volume": [100] * 60
    }, index=timestamps)
    
    bench_df = create_mock_daily_candles(scan_date, 60, [100.0] * 50 + [101.0] * 10)
    
    def side_effect(symbol, is_index=False):
        if "NIFTY50" in symbol:
            return nifty_df
        if "INDIAVIX" in symbol:
            return vix_df
        return bench_df
        
    mock_load.side_effect = side_effect
    
    service = MarketPermissionService()
    result = await service.evaluate_market_permission(scan_date)
    
    # If future candles (dated 2026-07-11 in IST) are correctly excluded:
    # - The trend state must remain BULLISH (close on 2026-07-10 is 10100.0)
    # - VIX must remain NORMAL (15.0 on 2026-07-10) and not trigger DEFENSIVE (VIX 35.0 on 2026-07-11)
    assert result.trend_state == "BULLISH"
    assert result.volatility_state == "NORMAL"
    assert result.market_state == "FAVORABLE"


@pytest.mark.anyio
@patch("app.services.market_permission_service.MarketPermissionService._load_candles")
async def test_market_regime_stale_vix_data(mock_load):
    # Stale VIX data beyond tolerance (6 calendar days stale)
    scan_date = datetime(2026, 7, 10)
    
    nifty_closes = [10000.0] * 50 + [10100.0] * 10
    vix_closes = [15.0] * 60
    bench_closes = [100.0] * 50 + [101.0] * 10
    
    # VIX last candle date is 2026-07-04 (6 days stale relative to 2026-07-10)
    nifty_df = create_mock_daily_candles(scan_date, 60, nifty_closes)
    vix_df = create_mock_daily_candles(datetime(2026, 7, 4), 60, vix_closes)
    bench_df = create_mock_daily_candles(scan_date, 60, bench_closes)
    
    def side_effect(symbol, is_index=False):
        if "NIFTY50" in symbol:
            return nifty_df
        if "INDIAVIX" in symbol:
            return vix_df
        return bench_df
        
    mock_load.side_effect = side_effect
    
    service = MarketPermissionService()
    result = await service.evaluate_market_permission(scan_date)
    
    # Stale VIX should force volatility_state to UNKNOWN, data_quality_flags["vix_data_fresh"] to False,
    # and degrade overall market_state to CAUTIOUS instead of FAVORABLE.
    assert result.market_state == "CAUTIOUS"
    assert result.volatility_state == "UNKNOWN"
    assert result.data_quality_flags["vix_data_fresh"] is False
    assert result.new_entry_allowed is True
    assert result.risk_multiplier == 0.5


@pytest.mark.anyio
@patch("app.services.market_permission_service.MarketPermissionService._load_candles")
async def test_market_regime_vix_staleness_boundary(mock_load):
    # VIX staleness exactly at threshold (5 calendar days stale)
    scan_date = datetime(2026, 7, 10)
    
    nifty_closes = [10000.0] * 50 + [10100.0] * 10
    vix_closes = [15.0] * 60
    bench_closes = [100.0] * 50 + [101.0] * 10
    
    # VIX last candle date is 2026-07-05 (exactly 5 days stale relative to 2026-07-10)
    nifty_df = create_mock_daily_candles(scan_date, 60, nifty_closes)
    vix_df = create_mock_daily_candles(datetime(2026, 7, 5), 60, vix_closes)
    bench_df = create_mock_daily_candles(scan_date, 60, bench_closes)
    
    def side_effect(symbol, is_index=False):
        if "NIFTY50" in symbol:
            return nifty_df
        if "INDIAVIX" in symbol:
            return vix_df
        return bench_df
        
    mock_load.side_effect = side_effect
    
    service = MarketPermissionService()
    result = await service.evaluate_market_permission(scan_date)
    
    # Exactly 5 days stale should be considered fresh (within tolerance).
    # Since other metrics are favorable, overall state should be FAVORABLE, not CAUTIOUS.
    assert result.market_state == "FAVORABLE"
    assert result.volatility_state == "NORMAL"
    assert result.data_quality_flags["vix_data_fresh"] is True
    assert result.new_entry_allowed is True
    assert result.risk_multiplier == 1.0


@pytest.mark.anyio
async def test_database_persistence_market_regime(db):
    agent = OrchestratorAgent(db)
    
    # Register/get watched stock
    stock_id = await agent._get_or_create_stock("INFY")
    
    from app.schemas.analysis import BacktestResult, MarketRegimeResult
    backtest = BacktestResult(
        mode="swing",
        strategy_name="regime_test_strat",
        total_return=15.0,
        cagr=12.0,
        max_drawdown=4.0,
        win_rate=0.7,
        profit_factor=1.8,
        trade_count=8,
        verdict="Bullish",
        equity_curve=[]
    )
    
    recommendation = FinalRecommendation(
        action="BUY",
        confidence=0.90,
        score=90.0,
        reasoning=RecommendationReasoning(bullets=["Ok"], risk_factors=[], invalidation_signals=[]),
        trade_plans=[],
        summary="Regime test"
    )
    
    regime = MarketRegimeResult(
        market_state="FAVORABLE",
        trend_state="BULLISH",
        breadth_state="HEALTHY",
        volatility_state="NORMAL",
        data_quality_flags={"nifty_data_present": True},
        reasons=["All metrics healthy"],
        new_entry_allowed=True,
        risk_multiplier=1.0,
        manual_review_flag=False
    )
    
    # Persist
    await agent._persist_analysis(
        stock_id=stock_id,
        mode="swing",
        technical_score=90.0,
        sentiment_score=0.5,
        backtest=backtest,
        recommendation=recommendation,
        market_regime=regime
    )
    
    # Query database and assert
    stmt = select(AnalysisHistory).where(AnalysisHistory.stock_id == stock_id).order_by(AnalysisHistory.id.desc()).limit(1)
    db_result = (await db.scalars(stmt)).first()
    
    assert db_result is not None
    assert db_result.market_state == "FAVORABLE"
    assert db_result.market_trend_state == "BULLISH"
    assert db_result.market_breadth_state == "HEALTHY"
    assert db_result.market_volatility_state == "NORMAL"
    assert db_result.market_new_entry_allowed is True
    assert db_result.market_risk_multiplier == 1.0
