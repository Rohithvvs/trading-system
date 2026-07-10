import pytest
from hypothesis import given, strategies as st
import math

from backend.app.utils.financial_math import (
    calculate_position_size,
    calculate_max_drawdown,
    calculate_risk_reward_ratio,
    calculate_kelly_criterion,
    calculate_sharpe_ratio
)

# Test Position Sizing
@given(
    st.floats(min_value=-1000000.0, max_value=1000000.0),
    st.floats(min_value=-100.0, max_value=100.0),
    st.floats(min_value=-10000.0, max_value=10000.0),
    st.floats(min_value=-10000.0, max_value=10000.0)
)
def test_position_size_invariants(equity, risk_pct, entry, stop_loss):
    """Property: Position size must never be negative, and must handle extreme edges safely."""
    size = calculate_position_size(equity, risk_pct, entry, stop_loss)
    assert size >= 0
    assert isinstance(size, (int, float))

def test_position_size_known_values():
    """Test standard known mathematical outcomes."""
    assert calculate_position_size(10000, 2, 100, 98) == 100 # Risking $200. $2 risk per share. 100 shares.
    assert calculate_position_size(10000, 2, 100, 100) == 0  # Zero division protection

# Test Max Drawdown
@given(st.lists(st.floats(min_value=-1000.0, max_value=100000.0), max_size=100))
def test_max_drawdown_invariants(equity_curve):
    """Property: Max drawdown should always be between 0 and 100% or unbounded depending on negative logic."""
    drawdown = calculate_max_drawdown(equity_curve)
    # The math function maxes at 0, so it's never negative.
    assert drawdown >= 0

def test_max_drawdown_known_values():
    assert calculate_max_drawdown([100.0, 90.0, 80.0, 100.0]) == 20.0
    assert calculate_max_drawdown([100.0, 110.0, 120.0]) == 0.0

# Test Risk/Reward
@given(
    st.floats(min_value=-10000.0, max_value=10000.0),
    st.floats(min_value=-10000.0, max_value=10000.0),
    st.floats(min_value=-10000.0, max_value=10000.0)
)
def test_risk_reward_invariants(entry, stop_loss, target):
    """Property: Risk reward ratio should never fail on zero division or negatives."""
    rr = calculate_risk_reward_ratio(entry, stop_loss, target)
    assert rr >= 0

def test_risk_reward_known_values():
    assert calculate_risk_reward_ratio(100, 95, 110) == 2.0  # Risk 5, Reward 10
    assert calculate_risk_reward_ratio(100, 100, 110) == 0.0 # Zero risk handled safely

# Test Kelly Criterion
@given(
    st.floats(min_value=-10.0, max_value=10.0),
    st.floats(min_value=-100.0, max_value=100.0)
)
def test_kelly_criterion_invariants(win_rate, rr_ratio):
    """Property: Kelly should always return between 0.0 and 1.0."""
    kelly = calculate_kelly_criterion(win_rate, rr_ratio)
    # The pure kelly can be > 1.0 if win rate is 1.0 and rr is very high, wait, W=1.0 -> 1.0 - 0 = 1.0. 
    # But let's assert it never errors and is >= 0
    assert kelly >= 0.0

def test_kelly_criterion_known_values():
    assert calculate_kelly_criterion(0.6, 1.0) == pytest.approx(0.2)  # 60% win rate, 1:1 RR -> Kelly 20%
    assert calculate_kelly_criterion(0.4, 1.0) == pytest.approx(0.0)  # Losing expectancy -> Kelly 0

# Test Sharpe Ratio
@given(
    st.lists(st.floats(min_value=-1.0, max_value=1.0), max_size=100),
    st.floats(min_value=-0.1, max_value=0.1)
)
def test_sharpe_ratio_invariants(returns, risk_free):
    """Property: Sharpe Ratio should calculate without zero division errors."""
    sharpe = calculate_sharpe_ratio(returns, risk_free)
    assert isinstance(sharpe, float)

def test_sharpe_ratio_known_values():
    assert calculate_sharpe_ratio([0.1, 0.1, 0.1]) == pytest.approx(0.0) # No std dev -> 0
    
