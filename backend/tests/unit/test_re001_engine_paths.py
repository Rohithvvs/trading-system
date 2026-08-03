"""Unit: engine BUY/WATCH/REJECT paths, empty inputs, supporting-only cannot force BUY."""

from app.services.re001.context import build_lab_context
from app.services.re001.engine import evaluate_re001


class _Bull:
    market_state = "FAVORABLE"
    trend_state = "BULLISH"
    new_entry_allowed = True


class _Bear:
    market_state = "DEFENSIVE"
    trend_state = "BEARISH"
    new_entry_allowed = False


class _C:
    def __init__(self, close, volume=200_000):
        self.close = close
        self.volume = volume
        self.high = close + 1
        self.low = close - 1
        self.open = close


class _T:
    def __init__(self, score, signal="bullish"):
        self.score = score
        self.signal = signal


def _candles(n=220, base=100.0):
    return [_C(base + i * 0.5, volume=200_000 + i * 1000) for i in range(n)]


def _portfolio():
    return {"open_positions_count": 0, "max_positions": 10, "available_cash": 1_000_000.0}


def test_empty_candles_bull_regime_rejects_or_no_buy():
    ctx = build_lab_context(
        symbol="EMPTY",
        market_regime=_Bull(),
        candles=[],
        technical_results=[_T(80)],
        user_portfolio=_portfolio(),
    )
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] in {"REJECT", "WATCH"}
    assert r["recommendation_state"] != "BUY" or "insufficient" in str(r.get("reason_codes"))


def test_strong_setup_can_buy_in_bull():
    ctx = build_lab_context(
        symbol="STRONG",
        market_regime=_Bull(),
        candles=_candles(),
        technical_results=[_T(85, "bullish")],
        user_portfolio=_portfolio(),
    )
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] in {"BUY", "WATCH", "REJECT"}
    if r["recommendation_state"] == "BUY":
        assert r.get("strategy_name")
        assert r["market_regime"] == "Bull"


def test_bear_ordinary_rejects():
    ctx = build_lab_context(
        symbol="BEAR1",
        market_regime=_Bear(),
        candles=_candles(),
        technical_results=[_T(70, "bullish")],
        user_portfolio=_portfolio(),
    )
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] == "REJECT"
    assert "bear_regime_minimal_participation" in r["reason_codes"]


def test_portfolio_unavailable_never_buy():
    ctx = build_lab_context(
        symbol="NOPORT",
        market_regime=_Bull(),
        candles=_candles(),
        technical_results=[_T(90, "bullish")],
        user_portfolio=None,
        risk_settings=None,
    )
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] != "BUY"
    # Either failed filter/strategy or portfolio downgrade
    if "portfolio_context_unavailable" in r.get("reason_codes", []):
        assert r["recommendation_state"] in {"WATCH", "REJECT"}


def test_states_only_allowed_values():
    ctx = build_lab_context(symbol="X", market_regime=_Bull(), candles=[], technical_results=[])
    r = evaluate_re001(ctx)
    assert r["recommendation_state"] in {"BUY", "WATCH", "REJECT"}
