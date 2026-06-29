# Technical Analysis: Sequence Diagrams

These sequence diagrams detail the exact interactions between services during various execution scenarios.

## 1. Normal Calculation (Happy Path)

```mermaid
sequenceDiagram
    participant CRON as Scheduler
    participant SCN as ScreenerService
    participant MD as MarketDataService
    participant DB as SQLite Cache
    participant TA as TechnicalAnalysisService

    CRON->>SCN: screen_symbols_swing(universe)
    SCN->>MD: validate_candle_continuity()
    MD->>DB: query existing history
    DB-->>MD: Valid (250 candles)
    MD-->>SCN: cache_health = True
    
    SCN->>MD: load_full_history()
    MD-->>SCN: DataFrame
    
    SCN->>SCN: concat all frames & ffill()
    
    SCN->>TA: analyze_bulk_from_frame(combined_frame)
    TA->>TA: calculate EMA, SMA, RSI, MACD
    TA->>TA: apply scoring logic
    TA-->>SCN: dict[symbol, TechnicalAnalysisResult]
    
    SCN->>SCN: calculate screener_score
    SCN-->>CRON: List[ScreenerConditionResult]
```

## 2. Cache Miss / Missing Data

```mermaid
sequenceDiagram
    participant SCN as ScreenerService
    participant MD as MarketDataService
    participant DB as SQLite Cache
    participant FYERS as Fyers API
    participant TA as TechnicalAnalysisService

    SCN->>MD: validate_candle_continuity()
    MD->>DB: query history
    DB-->>MD: Invalid (Only 50 candles found)
    MD-->>SCN: cache_health = False (Insufficient)
    
    SCN->>FYERS: fetch_incremental_ohlcv()
    FYERS-->>SCN: return missing 190 candles
    
    SCN->>MD: upsert_candles(new_data)
    MD->>DB: INSERT OR REPLACE
    
    SCN->>MD: load_full_history()
    MD-->>SCN: DataFrame (240 candles)
    
    SCN->>TA: analyze_bulk_from_frame()
    TA-->>SCN: TechnicalAnalysisResult
```

## 3. Corrupted Cache / Forced Rebuild

```mermaid
sequenceDiagram
    participant SCN as ScreenerService
    participant MD as MarketDataService
    participant DB as SQLite Cache
    participant FYERS as Fyers API

    SCN->>MD: validate_candle_continuity()
    MD->>DB: query history
    DB-->>MD: Invalid (Gaps detected)
    MD-->>SCN: cache_health = CORRUPTED
    
    Note over SCN: System drops existing cache
    SCN->>FYERS: fetch full history (240+ candles)
    FYERS-->>SCN: return full history
    
    SCN->>MD: upsert_candles(full_history)
    MD->>DB: INSERT OR REPLACE
    
    SCN->>MD: load_full_history()
    MD-->>SCN: Clean DataFrame
```

## 4. API Delay / Rate Limit

```mermaid
sequenceDiagram
    participant SCN as ScreenerService
    participant RATE as TokenBucketRateLimiter
    participant FYERS as Fyers API

    SCN->>RATE: acquire()
    RATE-->>SCN: token granted
    SCN->>FYERS: fetch_incremental_ohlcv()
    
    Note over SCN: Concurrent thread requests data
    SCN->>RATE: acquire()
    Note over RATE: Bucket empty. Sleep 200ms
    RATE-->>SCN: token granted (delayed)
    SCN->>FYERS: fetch_incremental_ohlcv()
```

## 5. Indicator Calculation Pipeline

```mermaid
sequenceDiagram
    participant TA_MAIN as TA: analyze_bulk_from_frame()
    participant PANDAS as Pandas Engine
    
    TA_MAIN->>PANDAS: frame.groupby("symbol")
    PANDAS-->>TA_MAIN: grouped_frame
    
    TA_MAIN->>PANDAS: transform(EMA 20)
    PANDAS-->>TA_MAIN: ema_20_series
    
    TA_MAIN->>PANDAS: transform(RSI Math)
    PANDAS-->>TA_MAIN: rsi_14_series
    
    TA_MAIN->>PANDAS: transform(MACD Math)
    PANDAS-->>TA_MAIN: macd_series
    
    TA_MAIN->>TA_MAIN: _calculate_supertrend(grouped)
    
    TA_MAIN->>PANDAS: pd.DataFrame(all_series)
    PANDAS-->>TA_MAIN: df_indicators
    
    TA_MAIN->>PANDAS: df_indicators.groupby("symbol").last()
    PANDAS-->>TA_MAIN: last_inds (Tail data)
```

## 6. Signal Generation

```mermaid
sequenceDiagram
    participant TA as TechnicalAnalysisService
    participant SCORE as Scoring Engine
    participant LOG as _log_analysis_decision
    
    loop For each symbol in Universe
        TA->>SCORE: Input: last_inds (EMA, RSI, MACD)
        
        SCORE->>SCORE: Check core_trend_filter_pass
        SCORE->>SCORE: Check core_momentum_filter_pass
        SCORE->>SCORE: Check basic_liquidity_filter_pass
        
        alt hard_filters_pass == True
            SCORE->>SCORE: Add points for EMA, MACD, Volume
            alt score >= 72
                SCORE-->>TA: signal = bullish
            else score >= 52
                SCORE-->>TA: signal = neutral
            end
        else hard_filters_pass == False
            SCORE-->>TA: signal = bearish
        end
        
        TA->>LOG: Log specific points and failures
    end
```
