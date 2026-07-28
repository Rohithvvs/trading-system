import pytest
from datetime import datetime, timezone
from app.schemas.scan_aggregate import ScanAggregateResult, ScanCandidateDTO, SingleWriteResult


def test_scan_candidate_dto_creation():
    candidate = ScanCandidateDTO(
        symbol="NSE:RELIANCE-EQ",
        strategy_name="MOMENTUM_BREAKOUT",
        signal_type="BUY",
        score=88.5,
        timeframe="15m",
        close_price=2450.75,
        volume=1254000,
        indicator_values={"rsi": 68.5, "ema50": 2410.0},
    )
    assert candidate.symbol == "NSE:RELIANCE-EQ"
    assert candidate.signal_type == "BUY"
    assert candidate.score == 88.5
    assert candidate.indicator_values["rsi"] == 68.5


def test_scan_aggregate_result_defaults():
    now = datetime.now(timezone.utc)
    c1 = ScanCandidateDTO(symbol="NSE:INFY-EQ", strategy_name="S1", signal_type="BUY", score=90.0)
    c2 = ScanCandidateDTO(symbol="NSE:TCS-EQ", strategy_name="S1", signal_type="WATCH", score=75.0)

    aggregate = ScanAggregateResult(
        scan_id="test-scan-uuid-123",
        symbol_universe="NIFTY500",
        execution_timestamp=now,
        candidates=[c1, c2],
        total_scanned=500,
        total_candidates=2,
        save_history=False,
    )

    assert aggregate.scan_id == "test-scan-uuid-123"
    assert aggregate.total_scanned == 500
    assert aggregate.total_candidates == 2
    assert len(aggregate.candidates) == 2
    assert aggregate.save_history is False
    assert aggregate.status == "SUCCESS"


def test_single_write_result_dto():
    result = SingleWriteResult(
        success=True,
        latest_rows_upserted=2,
        history_rows_inserted=0,
        transaction_duration_ms=45.2,
    )
    assert result.success is True
    assert result.latest_rows_upserted == 2
    assert result.history_rows_inserted == 0
    assert result.transaction_duration_ms == 45.2
