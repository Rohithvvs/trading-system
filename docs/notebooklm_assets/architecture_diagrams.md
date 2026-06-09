# Architecture Diagrams

This document contains Mermaid diagrams illustrating the various architectural components and data flows of the Trading System.

## Overall System Architecture

```mermaid
graph TD
    Client[Client Applications<br>Web / Mobile] -->|HTTPS / WSS| LB[Load Balancer]
    LB --> API[API Gateway]
    
    subgraph Backend Services
        API --> Auth[Auth Service]
        API --> User[User Service]
        API --> Market[Market Data Service]
        API --> Trade[Trading Engine]
        API --> Reco[Recommendation Engine]
        API --> Backtest[Backtesting Service]
    end
    
    subgraph External APIs
        Market -.->|REST / WS| Providers[Data Providers<br>Polygon, Alpaca, etc.]
        Trade -.->|REST / FIX| Brokers[Brokerages]
    end
    
    subgraph Data Layer
        Auth --> DB_Main[(Primary DB<br>PostgreSQL)]
        User --> DB_Main
        Trade --> DB_Main
        Market --> DB_TS[(Time-Series DB<br>TimescaleDB)]
        Backtest --> DB_TS
        Market --> Cache[(Cache/Message Broker<br>Redis / Kafka)]
        Trade --> Cache
    end
```

## Frontend Architecture

```mermaid
graph TD
    subgraph Frontend Application
        UI[UI Components]
        Pages[Views / Pages]
        State[State Management<br>Redux / Zustand]
        Hooks[Custom Hooks]
        
        subgraph Data Access Layer
            API_Client[API Client<br>Axios / Fetch]
            WS_Client[WebSocket Client]
            ReactQuery[Data Fetching & Caching<br>React Query]
        end
        
        UI --> Hooks
        Pages --> UI
        Hooks --> State
        Hooks --> ReactQuery
        ReactQuery --> API_Client
        ReactQuery --> WS_Client
    end
    
    API_Client -->|REST| Backend[Backend API]
    WS_Client -->|WSS| BackendWS[Backend WebSockets]
```

## Backend Architecture

```mermaid
graph TD
    subgraph Backend
        Gateway[API Gateway / Ingress]
        
        subgraph Microservices / Modules
            Auth[Authentication]
            Users[User Management]
            Portfolios[Portfolio Management]
            Orders[Order Management]
            MarketData[Market Data Ingestion]
            Analytics[Analytics & Reporting]
        end
        
        Gateway --> Auth
        Gateway --> Users
        Gateway --> Portfolios
        Gateway --> Orders
        Gateway --> MarketData
        Gateway --> Analytics
        
        EventBus{Event Bus / Message Broker}
        Orders -->|Order Placed| EventBus
        MarketData -->|Price Update| EventBus
        EventBus -->|Update Portfolio| Portfolios
        EventBus -->|Trigger Alerts| Analytics
    end
```

## Database Architecture

```mermaid
erDiagram
    USERS ||--o{ PORTFOLIOS : owns
    USERS ||--o{ WATCHLISTS : creates
    PORTFOLIOS ||--o{ POSITIONS : contains
    PORTFOLIOS ||--o{ ORDERS : tracks
    WATCHLISTS ||--o{ WATCHLIST_ITEMS : includes
    
    USERS {
        uuid id PK
        string email
        string password_hash
        datetime created_at
    }
    PORTFOLIOS {
        uuid id PK
        uuid user_id FK
        string name
        decimal cash_balance
    }
    POSITIONS {
        uuid id PK
        uuid portfolio_id FK
        string symbol
        decimal quantity
        decimal average_price
    }
    ORDERS {
        uuid id PK
        uuid portfolio_id FK
        string symbol
        string type
        string side
        decimal quantity
        decimal price
        string status
    }
    MARKET_DATA {
        string symbol
        datetime timestamp
        decimal open
        decimal high
        decimal low
        decimal close
        bigint volume
    }
```

## Authentication Flow

```mermaid
sequenceDiagram
    participant Client
    participant API Gateway
    participant Auth Service
    participant Database

    Client->>API Gateway: POST /api/login (email, password)
    API Gateway->>Auth Service: Forward request
    Auth Service->>Database: Query user by email
    Database-->>Auth Service: Return user record
    Auth Service->>Auth Service: Verify password hash
    Auth Service->>Auth Service: Generate JWT
    Auth Service-->>API Gateway: Return JWT & User Info
    API Gateway-->>Client: 200 OK (JWT)
    
    Note over Client,API Gateway: Subsequent Requests
    Client->>API Gateway: GET /api/portfolio (Header: Bearer JWT)
    API Gateway->>API Gateway: Validate JWT
    API Gateway->>Backend: Forward request
```

## Market Data Flow

```mermaid
sequenceDiagram
    participant External Provider
    participant Ingestion Service
    participant TimeSeries DB
    participant Message Broker
    participant WebSocket Server
    participant Client

    External Provider-->>Ingestion Service: Real-time Price Update (WS)
    Ingestion Service->>TimeSeries DB: Save Historical Tick
    Ingestion Service->>Message Broker: Publish Topic (e.g., ticks.AAPL)
    Message Broker-->>WebSocket Server: Push Message
    WebSocket Server-->>Client: Broadcast Price Update (WS)
```

## Recommendation Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Reco Engine
    participant ML Model
    participant DB

    User->>Frontend: View Dashboard
    Frontend->>Reco Engine: GET /api/recommendations
    Reco Engine->>DB: Fetch User Portfolio & Preferences
    Reco Engine->>ML Model: Request Signals (User Context)
    ML Model-->>Reco Engine: Return Scored Assets
    Reco Engine->>Reco Engine: Format & Filter Recommendations
    Reco Engine-->>Frontend: Return Recommendations List
    Frontend-->>User: Display Recommended Trades
```

## Paper Trading Flow

```mermaid
sequenceDiagram
    participant Client
    participant Order Manager
    participant Portfolio Service
    participant Market Data
    participant Database

    Client->>Order Manager: Place Market BUY Order (AAPL, 10 shares)
    Order Manager->>Portfolio Service: Check buying power
    Portfolio Service-->>Order Manager: Sufficient funds
    Order Manager->>Market Data: Get current AAPL price
    Market Data-->>Order Manager: AAPL = $150
    Order Manager->>Database: Save Order (Status: FILLED, Price: $150)
    Order Manager->>Portfolio Service: Deduct $1500, Add 10 AAPL
    Portfolio Service->>Database: Update Portfolio Balance & Positions
    Order Manager-->>Client: Order Filled Confirmation
```

## Backtesting Flow

```mermaid
sequenceDiagram
    participant Client
    participant Backtest Engine
    participant Strategy Runner
    participant Historical Data

    Client->>Backtest Engine: Start Backtest (Strategy ID, Timeframe, Params)
    Backtest Engine->>Historical Data: Fetch Data (e.g., 2020-2023)
    Historical Data-->>Backtest Engine: Return OHLCV Data
    Backtest Engine->>Strategy Runner: Execute Strategy with Data
    loop For each time step
        Strategy Runner->>Strategy Runner: Evaluate conditions
        Strategy Runner->>Strategy Runner: Simulate trades
    end
    Strategy Runner-->>Backtest Engine: Return Trade Log & Metrics
    Backtest Engine->>Database: Save Results
    Backtest Engine-->>Client: Return Performance Metrics (Sharpe, Max Drawdown)
```

## WebSocket Flow

```mermaid
sequenceDiagram
    participant Client
    participant API Gateway
    participant WS Manager
    participant Redis PubSub

    Client->>API Gateway: Upgrade to WebSocket (wss://...)
    API Gateway->>WS Manager: Establish Connection
    WS Manager-->>Client: Connected
    
    Client->>WS Manager: Subscribe: {"action":"subscribe", "channels":["AAPL.trades", "portfolio.updates"]}
    WS Manager->>Redis PubSub: Subscribe to channels
    WS Manager-->>Client: Subscription Confirmed
    
    Note over Redis PubSub, Client: Async Data Push
    Redis PubSub-->>WS Manager: Message received on 'AAPL.trades'
    WS Manager-->>Client: {"channel": "AAPL.trades", "data": {...}}
```

## Deployment Architecture

```mermaid
graph TD
    User((Users)) -->|HTTPS/WSS| CDN[CDN / WAF<br>Cloudflare]
    CDN --> K8s[Kubernetes Cluster]
    
    subgraph Kubernetes Cluster
        Ingress[Ingress Controller]
        Ingress --> WebApp[Frontend Pods]
        Ingress --> API[API Gateway Pods]
        Ingress --> WS[WebSocket Pods]
        
        API --> SVC_User[User Service Pods]
        API --> SVC_Trade[Trading Service Pods]
        API --> SVC_Data[Market Data Pods]
    end
    
    subgraph Managed Cloud Services
        SVC_User --> RDS[(Managed PostgreSQL)]
        SVC_Trade --> RDS
        SVC_Data --> TS[(TimescaleDB)]
        WS -.-> Redis[(Managed Redis)]
        SVC_Data -.-> Redis
    end
```
