from typing import List
import math

def calculate_position_size(account_equity: float, risk_per_trade_pct: float, entry_price: float, stop_loss: float) -> float:
    """
    Calculate position size based on risk parameters.
    """
    if account_equity <= 0 or entry_price <= 0 or stop_loss <= 0 or risk_per_trade_pct <= 0:
        return 0.0
    
    risk_amount = account_equity * (risk_per_trade_pct / 100.0)
    risk_per_share = abs(entry_price - stop_loss)
    
    if risk_per_share == 0:
        return 0.0
        
    return math.floor(risk_amount / risk_per_share)

def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """
    Calculate maximum drawdown percentage from an equity curve.
    """
    if not equity_curve:
        return 0.0
        
    max_drawdown = 0.0
    peak = equity_curve[0]
    
    for equity in equity_curve:
        if equity > peak:
            peak = equity
            
        if peak > 0:
            drawdown = ((peak - equity) / peak) * 100.0
            max_drawdown = max(max_drawdown, drawdown)
            
    return max_drawdown

def calculate_risk_reward_ratio(entry_price: float, stop_loss: float, target_price: float) -> float:
    """
    Calculate the Risk/Reward ratio for a trade.
    """
    if entry_price <= 0 or stop_loss <= 0 or target_price <= 0:
        return 0.0
        
    risk = abs(entry_price - stop_loss)
    reward = abs(target_price - entry_price)
    
    if risk == 0:
        return 0.0
        
    return reward / risk

def calculate_kelly_criterion(win_rate: float, risk_reward_ratio: float) -> float:
    """
    Calculate the Kelly Criterion percentage.
    Formula: K = W - [(1 - W) / R]
    """
    if risk_reward_ratio <= 0:
        return 0.0
    
    if not (0.0 <= win_rate <= 1.0):
        return 0.0
        
    kelly_pct = win_rate - ((1.0 - win_rate) / risk_reward_ratio)
    return max(0.0, kelly_pct)

def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
    """
    Calculate the Sharpe Ratio for a series of returns.
    """
    if not returns or len(returns) < 2:
        return 0.0
        
    excess_returns = [r - risk_free_rate for r in returns]
    avg_excess_return = sum(excess_returns) / len(excess_returns)
    
    # Calculate standard deviation
    variance = sum((r - avg_excess_return) ** 2 for r in excess_returns) / (len(excess_returns) - 1)
    
    # Floating point near-zero check for zero variance (e.g. constant returns)
    if variance < 1e-10:
        return 0.0
        
    std_dev = math.sqrt(variance)
    return avg_excess_return / std_dev
