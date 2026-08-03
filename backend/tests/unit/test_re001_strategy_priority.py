from app.services.re001.strategy_config import REGIME_PRIMARY_PRIORITY


def test_bull_priority_starts_with_trend():
    assert REGIME_PRIMARY_PRIORITY["Bull"][0] == "Trend Following"


def test_sideways_priority_starts_with_breakout():
    assert REGIME_PRIMARY_PRIORITY["Sideways"][0] == "Breakout Continuation"


def test_all_regimes_have_four_families():
    for regime, order in REGIME_PRIMARY_PRIORITY.items():
        assert len(order) == 4
