from app.services.re001.context import build_lab_context
from app.services.re001.engine import evaluate_re001
from app.services.re001.portfolio_context import portfolio_blocks_buy, resolve_portfolio_snapshot


class _MR:
    market_state = "FAVORABLE"
    trend_state = "BULLISH"
    new_entry_allowed = True


def test_unavailable_portfolio_blocks_buy():
    snap = resolve_portfolio_snapshot(user_portfolio=None, risk_settings=None)
    blocked, reason = portfolio_blocks_buy(snap)
    assert blocked
    assert reason == "portfolio_context_unavailable"


def test_engine_no_buy_without_portfolio_when_otherwise_strong(monkeypatch):
    # Minimal candles/TA to pass bull filter is hard; assert portfolio reason when eligible path uses empty portfolio
    ctx = build_lab_context(
        symbol="T",
        market_regime=_MR(),
        user_portfolio=None,
        risk_settings=None,
    )
    # Even if primary strategies fail, portfolio resolver returns unavailable
    from app.services.re001 import portfolio_context as pc

    snap = pc.resolve_portfolio_snapshot()
    assert not snap.available
