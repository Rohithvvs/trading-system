import pytest
from unittest.mock import MagicMock
from app.agents.orchestrator_agent import OrchestratorAgent
from app.schemas import AnalysisRequest, AnalysisMode, TimeframeConfig

@pytest.mark.asyncio
async def test_run_full_with_missing_symbol_and_empty_candles():
    """Verify that orchestrator gracefully handles missing symbols in prefetched_candles

    and empty candle dictionaries without raising StopIteration or KeyError.
    """
    orchestrator = OrchestratorAgent(db=MagicMock())

    # Request includes 2 symbols: one in prefetched_candles, one completely missing/empty
    request = AnalysisRequest(
        symbols=["IIFLCAPS-EQ", "HCG-EQ"],
        mode=AnalysisMode.swing,
        timeframe=TimeframeConfig(lookback_window=100, intraday="15", swing="1D"),
    )

    prefetched = {
        "IIFLCAPS-EQ": {
            AnalysisMode.swing: []  # empty candle list
        }
        # HCG-EQ intentionally omitted from dictionary
    }

    # Should run to completion without raising StopIteration or KeyError
    response = await orchestrator.run_full(request, prefetched_candles=prefetched)

    assert response is not None
    assert len(response.items) == 2
    symbols_returned = [item.symbol for item in response.items]
    assert "IIFLCAPS-EQ" in symbols_returned
    assert "HCG-EQ" in symbols_returned
