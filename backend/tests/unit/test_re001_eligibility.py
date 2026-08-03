"""Unit: Bull Stock Filter + exceptional RS leader (FR-024, bear path)."""

from app.services.re001.eligibility import bull_stock_filter_pass, exceptional_rs_leader


class _C:
    def __init__(self, close, volume=150_000):
        self.close = close
        self.volume = volume
        self.high = close + 1
        self.low = close - 1
        self.open = close


class _T:
    def __init__(self, score, signal="bullish"):
        self.score = score
        self.signal = signal


def _uptrend_candles(n=220, base=100.0):
    # Rising closes so recent price is above SMA50/SMA200
    return [_C(base + i * 0.5) for i in range(n)]


def test_insufficient_history_fails():
    ok, reasons = bull_stock_filter_pass(candles=[_C(100)] * 10, technical_results=[_T(80)])
    assert not ok
    assert "insufficient_history" in reasons


def test_uptrend_passes_bull_filter():
    ok, reasons = bull_stock_filter_pass(
        candles=_uptrend_candles(),
        technical_results=[_T(75)],
        sector_rs=1.0,
    )
    assert ok, reasons


def test_low_tech_score_fails():
    ok, reasons = bull_stock_filter_pass(
        candles=_uptrend_candles(),
        technical_results=[_T(40)],
    )
    assert not ok
    assert "technical_score_below_floor" in reasons


def test_exceptional_rs_leader_high_score():
    assert exceptional_rs_leader(technical_results=[_T(90)], sector_rs=None) is True
    assert exceptional_rs_leader(technical_results=[_T(70)], sector_rs=None) is False
    assert exceptional_rs_leader(technical_results=[_T(78)], sector_rs=2.0) is True
    assert exceptional_rs_leader(technical_results=[_T(78)], sector_rs=-1.0) is False
