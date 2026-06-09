# Request/Response Flows

This document contains sequence diagrams for key request/response flows in the trading system.

## User Login

```mermaid
sequenceDiagram
    actor User
    participant Client as Frontend Client
    participant Auth as Auth Service
    participant DB as Database
    
    User->>Client: Enter Credentials
    Client->>Auth: POST /api/auth/login {username, password}
    Auth->>DB: Query User
    DB-->>Auth: User Record & Hashed Password
    Auth->>Auth: Verify Password
    Auth->>Auth: Generate JWT (Access + Refresh)
    Auth-->>Client: 200 OK {access_token, refresh_token, user_info}
    Client->>Client: Store Tokens (LocalStorage/Cookie)
    Client-->>User: Navigate to Dashboard
```

## Token Refresh

```mermaid
sequenceDiagram
    participant Client as Frontend Client
    participant Auth as Auth Service
    participant DB as Database
    
    Client->>Auth: POST /api/auth/refresh {refresh_token}
    Auth->>DB: Verify Refresh Token
    DB-->>Auth: Token Valid
    Auth->>Auth: Generate New Access Token
    Auth-->>Client: 200 OK {access_token}
    Client->>Client: Update Stored Token
```

## Scanner Request

```mermaid
sequenceDiagram
    actor User
    participant Client as Frontend Client
    participant API as API Gateway
    participant Scanner as Scanner Service
    participant Market as Market Data API
    
    User->>Client: Apply Scan Filters
    Client->>API: POST /api/scanner/run {filters}
    API->>Scanner: Forward Request
    Scanner->>Market: Fetch Market Data for Universe
    Market-->>Scanner: Current Market Data
    Scanner->>Scanner: Apply Filters & Criteria
    Scanner-->>API: List of Matching Symbols
    API-->>Client: 200 OK {results}
    Client-->>User: Display Scanner Results
```

## Recommendation Generation

```mermaid
sequenceDiagram
    participant Scheduler as Cron/Scheduler
    participant RecEngine as Recommendation Engine
    participant AI as AI Model (LLM)
    participant DB as DB/Cache
    
    Scheduler->>RecEngine: Trigger Generate Recommendations
    RecEngine->>DB: Fetch Market Data & News
    DB-->>RecEngine: Data payload
    RecEngine->>AI: Prompt with Data
    AI-->>RecEngine: Trading Signals/Analysis
    RecEngine->>RecEngine: Format Recommendations
    RecEngine->>DB: Store Recommendations
```

## Technical Analysis Request

```mermaid
sequenceDiagram
    actor User
    participant Client as Frontend Client
    participant API as API Gateway
    participant TA as TA Engine
    participant Market as Market Data API
    
    User->>Client: Request TA for Symbol (e.g. AAPL)
    Client->>API: GET /api/ta/{symbol}?indicators=RSI,MACD
    API->>TA: Forward Request
    TA->>Market: Fetch Historical K-lines
    Market-->>TA: Historical Data
    TA->>TA: Calculate Indicators (RSI, MACD)
    TA-->>API: Indicator Values
    API-->>Client: 200 OK {indicators}
    Client-->>User: Render Charts/Values
```

## Paper Trade Execution

```mermaid
sequenceDiagram
    actor User
    participant Client as Frontend Client
    participant API as API Gateway
    participant Paper as Paper Trading Engine
    participant DB as Database
    
    User->>Client: Submit Order (e.g. Buy 100 AAPL @ Market)
    Client->>API: POST /api/paper-trade/order {symbol, qty, side, type}
    API->>Paper: Process Order
    Paper->>DB: Get User Buying Power
    DB-->>Paper: Balance Details
    Paper->>Paper: Check Margin/Balance
    Paper->>DB: Fetch Current Market Price
    DB-->>Paper: Price = $150
    Paper->>Paper: Execute Order (Deduct Funds, Add Position)
    Paper->>DB: Update Portfolio & Log Transaction
    DB-->>Paper: Success
    Paper-->>API: Order Executed
    API-->>Client: 200 OK {order_id, execution_price, status}
    Client-->>User: Show Success Notification
```

## Portfolio Refresh

```mermaid
sequenceDiagram
    actor User
    participant Client as Frontend Client
    participant API as API Gateway
    participant Portfolio as Portfolio Service
    participant Market as Market Data API
    participant DB as Database
    
    User->>Client: Open Portfolio Page
    Client->>API: GET /api/portfolio
    API->>Portfolio: Fetch Portfolio
    Portfolio->>DB: Get Positions
    DB-->>Portfolio: List of Positions
    Portfolio->>Market: Fetch Current Prices for Positions
    Market-->>Portfolio: Real-time Prices
    Portfolio->>Portfolio: Calculate PnL & Total Value
    Portfolio-->>API: Portfolio Summary
    API-->>Client: 200 OK {positions, total_value, pnl}
    Client-->>User: Display Portfolio Metrics
```

## Market Data Update

```mermaid
sequenceDiagram
    participant MarketProvider as External Provider (e.g. Alpaca)
    participant Ingestion as Data Ingestion Service
    participant DB as Time-Series DB
    participant Cache as Redis Cache
    
    MarketProvider->>Ingestion: Push Real-time Data (Websocket)
    Ingestion->>Ingestion: Normalize Data Format
    Ingestion->>Cache: Update Latest Price
    Ingestion->>DB: Persist Tick/Candle
```

## WebSocket Subscription

```mermaid
sequenceDiagram
    actor User
    participant Client as Frontend Client
    participant WS as WebSocket Server
    participant Cache as Redis Pub/Sub
    
    User->>Client: View Chart for AAPL
    Client->>WS: Connect WebSocket
    WS-->>Client: Connection Established
    Client->>WS: SEND {"action": "subscribe", "symbol": "AAPL"}
    WS->>Cache: Subscribe to "market_data.AAPL"
    Cache-->>WS: Messages (Price Updates)
    WS-->>Client: Push Data (JSON)
    Client-->>User: Update Chart in Real-time
```

## Backtest Execution

```mermaid
sequenceDiagram
    actor User
    participant Client as Frontend Client
    participant API as API Gateway
    participant Backtest as Backtesting Engine
    participant DB as Historical Data DB
    
    User->>Client: Run Backtest (Strategy A, 2020-2023)
    Client->>API: POST /api/backtest {strategy, params, timeframe}
    API->>Backtest: Queue Backtest Task
    Backtest->>DB: Fetch Historical Data
    DB-->>Backtest: K-lines & Ticks
    Backtest->>Backtest: Simulate Strategy Execution
    Backtest->>Backtest: Calculate Performance Metrics (Sharpe, Drawdown)
    Backtest-->>API: Backtest Results
    API-->>Client: 200 OK {metrics, equity_curve, trades}
    Client-->>User: Render Backtest Report
```
