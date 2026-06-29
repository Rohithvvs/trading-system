# Scoring Logic

The Scanner Engine uses a weighted scoring system out of 100 points to rank stocks. The score is a blend of the technical engine's base score and specific swing-trading confirmations.

## Overall Score Calculation
Located in `ScreenerService._weighted_score`.

**Maximum Possible Score = 100**

1. **Base Technical Score (Max 50 points)**
   - `score += technical.score * 0.5`
   - The Technical Analysis engine computes a base score (out of 100) based on EMAs, Supertrend, MACD, etc. The scanner uses 50% of this as the foundation.

2. **Trend Eligibility (Max 12 points)**
   - `+12 points`: If `broad_trend_eligibility == True` (Close > SMA50 > SMA200).

3. **Hard Filters (Max 6 points)**
   - `+6 points`: If `hard_filters_pass == True` (Core trend, momentum, and liquidity filters pass).

4. **Moving Average Alignments (Max 9 points)**
   - `+4 points`: If `close_above_ema20`.
   - `+5 points`: If `ema20_above_ema50`.

5. **Momentum Indicators (Max 11 points)**
   - `+4 points`: If `supertrend_positive`.
   - `+4 points`: If `macd_positive`.
   - `+3 points`: If `rsi_supportive` (RSI >= 50).

6. **Price Structure / Price Action (Max 18 points)**
   - `+4 points`: If `sma_uptrend_20d` (20-day SMA is rising).
   - `+3 points`: If `hh_hl_2d` (Higher High, Higher Low over 2 days).
   - `+3 points`: If `hh_hl_3d` (Higher High, Higher Low over 3 days).
   - `+3 points`: If `hh_hl_4d` (Higher High, Higher Low over 4 days).
   - `+3 points`: If `latest_confirms_5d_structure` (Breakout above 5-day structure).
   - `+2 points`: If `hammer_or_gravestone` (Reversal candlestick pattern).

7. **Volume Profile (Max 14 points)**
   - `+3 points`: If `volume_above_50000`.
   - `+3 points`: If `volume_above_previous_day`.
   - `+ up to 8 points`: Volume Lift. Calculated as `((latest.volume - previous.volume) / previous.volume) * 100`. Capped at a maximum of 8 points.

Finally, the total score is capped at 100.0:
`score = round(min(score, 100.0), 2)`

## Technical Engine Base Score (Swing)
Located in `TechnicalAnalysisService.analyze_bulk_from_frame`.

This is the score that is halved and fed into the overall score above.
- `+18 points`: `close_above_ema20`
- `+12 points`: `ema_20 > ema_50`
- `+16 points`: `supertrend_positive`
- `+12 points`: `macd_positive`
- `+8 points`: `rsi_supportive` (RSI >= 50)
- `+6 points`: `rsi_in_buy_zone` (55 <= RSI <= 68)
- `+8 points`: `sma_uptrend_20d`
- `+10 points`: `higher_timeframe_trend == uptrend` (Close > SMA50 and SMA20 > SMA50)
- `+5 points`: `volume_above_50000`
- `+4 points`: `volume_above_previous_day`
- `+4 points`: `price_above_100`
- `+2 points`: `price_below_500000`
- `+ up to 12 points`: `structure_score * 3`
- `+4 points`: `hammer_or_gravestone`

## Recommendation Logic
Once shortlisted, the `RecommendationAgent` analyzes the complete context (Technical, Fundamental, Backtest, News).
- **BUY**: The stock has a high technical score, passed hard filters, has supportive news, and favorable backtest metrics.
- **WATCH**: The stock has a strong setup but might be extended, hitting resistance, or lacking volume confirmation.
- **REJECT**: The stock failed downstream analysis (e.g., terrible fundamentals or negative news overriding the technical setup).
