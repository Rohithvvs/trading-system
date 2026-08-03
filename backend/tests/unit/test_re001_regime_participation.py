"""SC-006: bear BUY count <= 50% of bull on shared fixtures (engine heuristics)."""

from app.services.re001.context import build_lab_context
from app.services.re001.engine import evaluate_re001


class _BullMR:
    market_state = "FAVORABLE"
    trend_state = "BULLISH"
    new_entry_allowed = True


class _BearMR:
    market_state = "DEFENSIVE"
    trend_state = "BEARISH"
    new_entry_allowed = False


class _Tech:
    def __init__(self, score: float, signal: str = "bullish"):
        self.score = score
        self.signal = signal


def _candles(n=220, close=200.0):
    class C:
        pass

    out = []
    for i in range(n):
        c = C()
        c.close = close + (i % 5) * 0.1
        c.volume = 100000 + i * 10
        c.high = c.close + 1
        c.low = c.close - 1
        c.open = c.close
        out.append(c)
    return out


def test_bear_buy_not_exceed_half_bull():
    symbols = [f"S{i}" for i in range(10)]
    bull_buys = 0
    bear_buys = 0
    for s in symbols:
        tech = [_Tech(80.0)]
        candles = _candles()
        bull_ctx = build_lab_context(
            symbol=s,
            market_regime=_BullMR(),
            technical_results=tech,
            candles=candles,
            user_portfolio={"open_positions_count": 0, "max_positions": 10, "available_cash": 1e6},
        )
        bear_ctx = build_lab_context(
            symbol=s,
            market_regime=_BearMR(),
            technical_results=tech,
            candles=candles,
            user_portfolio={"open_positions_count": 0, "max_positions": 10, "available_cash": 1e6},
        )
        if evaluate_re001(bull_ctx)["recommendation_state"] == "BUY":
            bull_buys += 1
        if evaluate_re001(bear_ctx)["recommendation_state"] == "BUY":
            bear_buys += 1

    # In bear with new_entry_allowed False, exceptional path is rare — expect 0 buys typically
    if bull_buys == 0:
        assert bear_buys == 0
    else:
        assert bear_buys <= 0.5 * bull_buys
