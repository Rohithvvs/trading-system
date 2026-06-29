# Recommendation Engine: Decision Tree

This outlines the precise logical branching the Orchestrator and Recommendation engines use to arrive at a final state.

```mermaid
graph TD
    A[Start: Symbol Data Loaded] --> B{Is Live Data Available?}
    B -- No --> C[Set Score=0, Action=REJECT]
    B -- Yes --> D{Is News Extreme OR Volume > 3x?}
    
    D -- Yes (Catalyst) --> E[Weights: Tech=20%, Backtest=20%, News=30%, Fund=30%]
    D -- No (Standard) --> F[Weights: Tech=50%, Backtest=25%, News=0%, Fund=25%]
    
    E --> G[Calculate Base Score]
    F --> G
    
    G --> H{Is Score >= 72?}
    H -- No --> I{Is Score >= 55?}
    
    I -- Yes --> J[Action = WATCH]
    I -- No --> K[Action = REJECT]
    
    H -- Yes --> L[Action = BUY]
    
    L --> M{Strict Gating Check}
    M --> |Check: Strong Technical >= 75?| N{Tech Pass?}
    N -- No --> O[Downgrade to WATCH]
    N -- Yes --> P{Check: R/R >= 1.25?}
    
    P -- No --> O
    P -- Yes --> Q{Check: Live Fyers Data & Min Candles?}
    
    Q -- No --> O
    Q -- Yes --> R[Final Action = BUY]
```

## Branch Explanations

1. **Data Availability:** If live OHLCV data is missing, analysis is completely aborted to prevent stale recommendations.
2. **Regime Detection:** Instantly determines if the market is trading normally or reacting to a sudden catalyst, setting weights accordingly.
3. **Thresholding:** Simple numerical thresholding translates continuous mathematical scores into discrete categorical labels (BUY, WATCH, REJECT).
4. **Strict Gating:** Even if the mathematical score is extremely high (e.g., 85), the Orchestrator applies safety vetoes. If the Technical score alone isn't strong enough, or the Risk/Reward ratio on the Trade Plan is poor, or the data source was "mocked" instead of live, it will refuse to authorize a BUY and downgrades to a WATCH.
