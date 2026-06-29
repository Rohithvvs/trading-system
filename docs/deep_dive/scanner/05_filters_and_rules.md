# Filters and Rules

The Scanner Engine enforces strict mathematical rules to filter out low-probability trades. These rules are split into Data Quality, Broad Trend Eligibility, and Hard Technical Filters.

## 1. Data Quality Filters
Located in `ScreenerService._passes_data_quality`.

- **Minimum Swing Candles Met**
  - **Implementation**: Requires `total_candle_count >= 220`.
  - **Business Purpose**: Ensures the stock has been listed long enough to form a stable 200-day moving average.
  - **If Removed**: New IPOs with wild volatility would enter the scanner, throwing off moving average calculations.

- **Positive Price Check**
  - **Implementation**: `close > 0, high > 0, low > 0` for the last 30 candles.
  - **Business Purpose**: Ensures data is not corrupted or split-adjusted to zero.
  - **If Removed**: Math errors (division by zero) would crash the technical analysis engine.

- **Minimum Liquidity Days**
  - **Implementation**: `volume > 0` on at least 25 out of the last 30 days.
  - **Business Purpose**: Filters out illiquid stocks that do not trade daily.
  - **If Removed**: Traders could get trapped in illiquid penny stocks unable to exit their positions.

## 2. Broad Trend Eligibility
Located in `ScreenerService._passes_broad_trend`.

This is the primary gateway. A stock MUST pass this to be considered "Matched".

- **Price Above SMA 50**
  - **Implementation**: `latest_close > sma_50`
  - **Business Purpose**: Ensures the medium-term trend is upward. Do not catch falling knives.

- **SMA 50 Above SMA 200**
  - **Implementation**: `sma_50 > sma_200`
  - **Business Purpose**: Ensures the long-term trend (Golden Cross) is established.

- **Hard Filters Pass**
  - **Implementation**: `hard_filters_pass == True` (Defined in Technical Analysis Engine).

- **Minimum Average Volume**
  - **Implementation**: `avg_volume (last 20 days) > 100,000`
  - **Business Purpose**: Requires deep liquidity so slippage is minimized when entering/exiting trades.

- **Minimum Technical Score**
  - **Implementation**: `technical_score >= 48`
  - **Business Purpose**: Ensures baseline technical strength.

## 3. Hard Technical Filters
Calculated in `TechnicalAnalysisService` and aggregated into `hard_filters_pass`.

- **Core Trend Filter Pass**
  - **Implementation**: `close_above_ema20 AND supertrend_positive`
  - **Business Purpose**: Validates short-term momentum is aligned with the long-term trend.

- **Core Momentum Filter Pass**
  - **Implementation**: `macd_positive AND rsi_supportive (RSI >= 50)`
  - **Business Purpose**: Validates that buying pressure is increasing.

- **Basic Liquidity Filter Pass**
  - **Implementation**: `volume > 50,000 AND 100 < close < 500,000`
  - **Business Purpose**: Removes penny stocks (< 100 INR) which are highly manipulated, and removes extremely illiquid high-priced stocks.
