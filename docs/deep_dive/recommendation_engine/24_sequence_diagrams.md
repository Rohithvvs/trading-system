# Recommendation Engine: Sequence Diagrams

## 1. BUY Recommendation Flow
```mermaid
sequenceDiagram
    participant O as OrchestratorAgent
    participant T as TechAnalysisService
    participant R as RecommendationAgent
    participant L as LLMService
    participant S as RecommendationService

    O->>T: analyze_bulk_from_frame(candles)
    T-->>O: TechnicalResult (Score: 85)
    O->>R: run(symbol, Tech, News, Backtest, Fund)
    R->>L: build_reasoning(context)
    L-->>R: JSON (bullets, summary)
    R->>S: build(...)
    S->>S: calculate_dynamic_weights()
    S->>S: Final Score = 78
    S-->>R: FinalRecommendation (Action: BUY)
    R-->>O: FinalRecommendation
    O->>O: _enforce_strict_buy_gate()
    Note over O: Checks Tech >= 75 (Pass), R/R >= 1.25 (Pass), Data Live (Pass)
    O-->>UI: Output: BUY
```

## 2. WATCH (Downgraded) Recommendation Flow
```mermaid
sequenceDiagram
    participant O as OrchestratorAgent
    participant R as RecommendationAgent
    participant S as RecommendationService

    O->>R: run(symbol, ...)
    R->>S: build(...)
    S-->>R: FinalRecommendation (Action: BUY, Tech Score: 60)
    R-->>O: FinalRecommendation
    O->>O: _enforce_strict_buy_gate()
    Note over O: Tech Score is 60 (Fails >= 75 check)
    O-->>UI: Output: WATCH (Downgraded due to weak tech)
```

## 3. Conflict Resolution (Catalyst Overrides Tech)
```mermaid
sequenceDiagram
    participant O as OrchestratorAgent
    participant S as RecommendationService

    O->>S: build(Tech: 90, News: -0.95)
    S->>S: calculate_dynamic_weights()
    Note over S: abs(-0.95) >= 0.75 -> Catalyst Regime!
    Note over S: Weights change: Tech=20%, News=30%
    S->>S: Calculate Final Score
    Note over S: High negative news drags score to 40
    S-->>O: FinalRecommendation (Action: REJECT)
```

## 4. AI Timeout (Graceful Degradation)
```mermaid
sequenceDiagram
    participant R as RecommendationAgent
    participant L as LLMService
    participant G as Groq API

    R->>L: build_reasoning(context)
    L->>G: HTTP POST (timeout=20s)
    Note over G: Server hangs...
    L--xG: Timeout Exception
    L->>L: _fallback_reasoning()
    Note over L: Generates deterministic text
    L-->>R: JSON (fallback bullets)
```
