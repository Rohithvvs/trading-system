import pytest
from unittest.mock import patch, MagicMock
from backend.app.agents.orchestrator_agent import OrchestratorAgent
from backend.app.schemas.analysis import AnalysisMode, TechnicalAnalysisResult, FundamentalAnalysisResult

@pytest.mark.asyncio
@patch("backend.app.agents.orchestrator_agent.TechnicalAnalysisAgent")
@patch("backend.app.agents.orchestrator_agent.RecommendationAgent")
@patch("backend.app.agents.orchestrator_agent.FundamentalAnalysisAgent")
async def test_orchestrator_service_integration(mock_fund_agent, mock_rec_agent, mock_tech_agent):
    # Setup mocks for internal services communicating with each other
    mock_tech_instance = mock_tech_agent.return_value
    mock_tech_instance.run.return_value = TechnicalAnalysisResult(
        mode=AnalysisMode.swing, score=80.0, signal="BUY", indicators={}, summary=""
    )
    
    mock_fund_instance = mock_fund_agent.return_value
    mock_fund_instance.run.return_value = FundamentalAnalysisResult(
        revenue_growth_pct=10.0, profit_margin_pct=20.0, fundamental_score=70.0, summary=""
    )
    
    from backend.app.schemas.analysis import FinalRecommendation, TradePlan, RecommendationReasoning
    mock_rec_instance = mock_rec_agent.return_value
    
    valid_rec = FinalRecommendation(
        symbol="HDFCBANK.NS",
        action="BUY",
        confidence=85.0,
        score=85.0,
        summary="",
        trade_plans=[TradePlan(
            strategy_name="test",
            mode="swing",
            timeframe="1d",
            setup_type="breakout",
            setup_quality="HIGH",
            bias="LONG",
            entry_low=99.0,
            entry_high=101.0,
            stop_loss=95.0,
            target_1=110.0,
            target_2=120.0,
            risk_reward_ratio=2.0,
            allocation_pct=10.0,
            conditions=[],
            notes="Test plan"
        )],
        reasoning=RecommendationReasoning(
            bullets=[],
            risk_factors=[],
            invalidation_signals=[],
            summary="Test reasoning"
        )
    )
    mock_rec_instance.recommendation_service.build.return_value = valid_rec
    mock_rec_instance.run.return_value = valid_rec
    
    # Run the orchestrator which integrates all services internally
    # We are testing that Orchestrator properly calls the sub-services and aggregates data
    mock_db = MagicMock()
    orchestrator = OrchestratorAgent(mock_db)
    
    # Run the orchestrator which integrates all services internally
    # We are testing that Orchestrator properly calls the sub-services and aggregates data
    with patch.object(orchestrator, 'fyers_service'):
        with patch.object(orchestrator, 'news_agent'):
            orchestrator.news_agent.run.return_value = ([], 0.5, "Neutral", "")
            with patch.object(orchestrator, 'backtest_agent'):
                from backend.app.schemas.analysis import BacktestResult
                orchestrator.backtest_agent.run.return_value = BacktestResult(
                    strategy_name="Test",
                    total_return=15.0,
                    cagr=5.0,
                    max_drawdown=-5.0,
                    win_rate=60.0,
                    profit_factor=1.5,
                    trade_count=10,
                    verdict="PASS",
                    mode="swing",
                    equity_curve=[]
                )
                orchestrator.fyers_service.get_candles_cached.return_value = []
                orchestrator.fyers_service.get_ohlcv_source.return_value = "FYERS_API"
                # analyze_symbol requires asyncio loop (via to_thread in run_full) but is a sync function inside orchestrator
                import asyncio
                import datetime
                from backend.app.schemas.analysis import AnalysisRequest, OHLCVPoint
                request = AnalysisRequest(symbols=["HDFCBANK.NS"], mode=AnalysisMode.swing)
                dummy_candle = OHLCVPoint(timestamp=datetime.datetime(2023, 1, 1), open=100.0, high=105.0, low=95.0, close=101.0, volume=1000)
                bulk_technical = {AnalysisMode.swing: {"HDFCBANK.NS": mock_tech_instance.run.return_value}}
                result = await asyncio.to_thread(orchestrator._analyze_symbol_post_bulk, "HDFCBANK.NS", request, {AnalysisMode.swing: [dummy_candle]}, bulk_technical)
            
    # Verify service-to-service communication was triggered
    mock_fund_instance.run.assert_called()
    mock_rec_instance.run.assert_called()
    
    # Verify DB save was called
    assert mock_db.add.called
