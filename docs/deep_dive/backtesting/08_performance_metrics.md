# Performance Metrics

The `BacktestService` calculates standard quantitative finance metrics to evaluate the strategy's historical performance.

## 1. Win Rate
**Formula**: `(Wins / Total Trades) * 100`
**Meaning**: The percentage of trades that resulted in a positive PnL.
**Business Importance**: High win rates are psychologically easier for traders to follow. 
**Numerical Example**: 
Out of 10 trades, 6 were profitable (> 0%) and 4 were losses. 
`Win Rate = (6 / 10) * 100 = 60.0%`

## 2. Profit Factor
**Formula**: `Gross Profit / Gross Loss` (using sum of percentage returns)
**Meaning**: For every ₹1 lost, how many ₹ are made.
**Business Importance**: A profit factor > 1.0 means the strategy is profitable. > 2.0 is considered excellent.
**Numerical Example**:
- Wins: +10%, +15%, +5% (Gross Profit = 30%)
- Losses: -5%, -5% (Gross Loss = 10%)
- `Profit Factor = 30 / 10 = 3.0`

## 3. Maximum Drawdown
**Formula**: `((Peak Equity - Trough Equity) / Peak Equity) * 100`
**Meaning**: The largest percentage drop from a historical peak in the equity curve.
**Business Importance**: Measures worst-case historical risk. A 50% drawdown requires a 100% gain just to break even.
**Numerical Example**:
- Peak Equity: ₹150,000
- Equity drops to: ₹120,000
- `Max Drawdown = ((150,000 - 120,000) / 150,000) * 100 = 20.0%`

## 4. CAGR (Compound Annual Growth Rate)
**Formula**: `Total Return * (252 / Total Candles)`
**Meaning**: The annualized rate of return, assuming 252 trading days in a year.
**Business Importance**: Allows comparison against baseline assets (like Nifty 50 which averages ~12% CAGR).
**Numerical Example**:
- Total Return: 50% (0.50) over 504 trading days (2 years).
- `CAGR = 50 * (252 / 504) = 25.0%`

## 5. Sharpe Ratio (Sample-based Approximation)
**Formula**: `(Mean Return / Standard Deviation of Returns) * sqrt(Trade Count)`
**Meaning**: Risk-adjusted return. How much return is generated per unit of volatility.
**Business Importance**: High returns achieved via high risk (wild swings) have a low Sharpe ratio. High returns with a smooth curve have a high Sharpe ratio (> 1.0).
**Numerical Example**:
- Trades: +10%, +12%, +8%, -5%, +5% (Count = 5)
- Mean Return: 6%
- Std Dev: 6.44%
- `Sharpe = (6 / 6.44) * sqrt(5) = 0.93 * 2.23 = 2.07`

## 6. Average Profit / Average Loss
While not exposed as top-level fields in `BacktestResult`, they dictate the Profit Factor. 
- **Average Profit** = Sum of winning percentages / Count of wins.
- **Average Loss** = Sum of losing percentages / Count of losses.
- **Risk Reward Ratio** = Average Profit / Average Loss. (e.g., Avg profit 10%, Avg loss 5% -> RR is 2:1).
