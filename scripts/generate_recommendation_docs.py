import os

docs_dir = r"F:\trading system01\trading system\docs\deep_dive\recommendation_engine"
os.makedirs(docs_dir, exist_ok=True)

files = {
    "09_buy_logic.md": """# 09 BUY Logic

## Exactly Why BUY is Generated
A **BUY** recommendation is the hardest state to achieve in the system. It requires two distinct phases of validation to pass:

1. **Score Threshold (`RecommendationService.build`)**
   The dynamically weighted combined score (Technical + Backtest + News + Fundamental) must be `>= 72` out of 100.

2. **Strict Buy Gate (`OrchestratorAgent._enforce_strict_buy_gate`)**
   Even if the score is `>= 72`, the Orchestrator will aggressively downgrade the BUY to a WATCH unless three strict confirmations are met:
   - **Strong Live Data**: Real FYERS data must be used (`source == "FYERS_PRIMARY"`), no mock warnings, and minimum swing candles must be met (e.g., 220 candles).
   - **Strong Execution**: The generated Trade Plan must have a Risk:Reward ratio `>= 1.25`.
   - **Strong Technicals**: The raw underlying Technical score must be `>= 75`.

## Every Dependency
- `TechnicalAnalysisResult`: For base score and trade plan formulation.
- `BacktestResult`: For win rate and strategy profitability.
- Sentiment Score: For dynamic weighting.
- `FundamentalAnalysisResult`: For fundamental strength.
- Volume: For catalyst regime triggering.

## Worked Example
- Technical Score: 85
- Backtest Return: 15% (gives max backtest component)
- Sentiment: 0.10 (Standard Regime)
- **Calculation**: 
  (85 * 0.50) + (100 * 0.25) + (10 * 0.0) + (50 * 0.25) = 42.5 + 25 + 12.5 = 80.
- **Result**: Initial score is 80 (>= 72), so Action = "BUY".
- **Strict Gate**: Live data is FYERS, RR is 1.5, Tech is 85.
- **Final Output**: BUY.

## Business Meaning
A BUY signal means the engine has extreme confidence. The setup is historically profitable, technically prime, mathematically skewed in risk-reward favor, and backed by high-quality non-mocked data.
""",
    "10_watch_logic.md": """# 10 WATCH Logic

## Every Rule & Threshold
A **WATCH** recommendation occurs in two primary scenarios:

1. **Natural Score-Based WATCH**:
   The final calculated score is `>= 55` but `< 72`.
   This indicates a setup that has positive merit but lacks the absolute conviction required to risk capital immediately.

2. **Downgraded BUY**:
   The initial score was `>= 72` (BUY), but the `OrchestratorAgent._enforce_strict_buy_gate` rejected it. 
   - E.g., The setup looks great, but the Risk:Reward ratio is 1.10 (fails `>= 1.25` requirement).
   - E.g., The system used fallback data (`mock_warning == True`).
   - E.g., The raw technical score was 70, but great news pushed the total score to 75. It fails the `best_technical.score >= 75` strict gate requirement.

## Examples
- A stock breaks out, but the stop-loss is very wide, making Risk:Reward `0.9`. It scores `78`. The Strict Buy Gate downgrades it to WATCH. The reasoning `risk_factors` array gets appended with: *"Strict BUY gate blocked this setup because live-data quality, backtest strength, or risk-reward confirmation was not strong enough."*
""",
    "11_hold_logic.md": """# 11 HOLD Logic

## Explicit Notice
**HOLD is NOT implemented as a generated action in the Recommendation Engine.**

## Why HOLD exists (or doesn't)
The scanner and Recommendation Engine evaluate stocks for **Entry (BUY)**. 
Once a stock is bought, the system delegates position management to the execution layer. The Recommendation Engine emits `TradePlan` objects that contain:
- `stop_loss`
- `target_1`
- `target_2`
- `target_3`

A position is implicitly "HELD" until one of these price levels is breached during live execution. The Recommendation Engine does not continually evaluate open positions to emit "HOLD" strings; it only evaluates fresh setups for "BUY", "WATCH", or "REJECT".

## Examples
If a user runs the scanner on a stock they already own, the engine will return BUY, WATCH, or REJECT based on the *current* entry setup, entirely agnostic to the user's existing portfolio.
""",
    "12_reject_logic.md": """# 12 REJECT Logic

## Every Rule
A **REJECT** recommendation is generated when:
1. The combined dynamic score is `< 55`.
2. There is a catastrophic failure in data retrieval (e.g., empty candles), which triggers the `_unavailable_analysis_result` fallback in Orchestrator, hardcoding a `0.0` score and "REJECT" action.

## Examples
- **Poor Setup**: Technical score is 30, Backtest is losing money, News is neutral. Score calculates to `25`. Result: REJECT.
- **Negative Catalyst**: Technical score is 70. Earnings report is terrible (News Score = -0.90). Catalyst Regime activates, weighting news at 30%. Total score gets dragged down to `45`. Result: REJECT.
""",
    "13_conflict_resolution.md": """# 13 Conflict Resolution

## Very Important: The Dynamic Weighting Regime

The Recommendation Engine resolves conflicts (e.g., Technical says BUY, News says NEGATIVE) through **Dynamic Weights**.

### The Two Regimes
In `RecommendationService.calculate_dynamic_weights`, the engine checks for Catalysts:
- `news_catalyst`: `abs(sentiment_score) >= 0.75`
- `volume_catalyst`: `current_volume > avg_volume * 3.0`

**1. Standard Regime (No Catalyst)**
If volume is normal and news is mildly positive/negative/neutral:
- Technical: 50%
- Backtest: 25%
- Fundamental: 25%
- News: 0% (Ignored entirely as it's just "noise")

**2. Catalyst Regime (Conflict Trigger)**
If a massive news event occurs (News Score = -0.90) or massive volume flows in:
- Technical: 20%
- Backtest: 20%
- News: 30%
- Fundamental: 30%

### Conflict Resolution Example
**Scenario**: Technical Analysis says BUY (Score 90). News says NEGATIVE (-0.90). Backtesting says GOOD. Volume says HIGH (3.5x avg).

**How the system decides**:
1. High volume and extreme news triggers the **Catalyst Regime**.
2. News is now weighted at 30%. Fundamental at 30%. Technical drops to 20%.
3. The negative news score (-0.90 * 100 = -90) contributes heavily.
4. Total Score calculation gets crushed by the -90 * 0.30 (-27 points penalty).
5. A setup that would have scored ~80 natively might drop to `48`.
6. The system emits a **REJECT**.

**Conclusion**: In conflicts involving extreme volume or extreme news, Fundamentals and News override Technicals.
""",
    "14_ai_llm_integration.md": """# 14 AI / LLM Integration

## Integration Point
The `RecommendationAgent` utilizes `LLMService.build_reasoning` to generate human-readable narratives for the final recommendation.

## Prompt
- **System**: "You are a trading analysis assistant. Respond with valid JSON only. Keep output advisory-only and never mention automated execution. Return keys: bullets, risk_factors, invalidation_signals, summary."
- **User context**: Contains Technical Signal, Technical Score, News Label, Backtest Verdict, Fundamental Score, and Current Price.

## Response & Validation
- The LLM (Groq) responds with JSON.
- `json.loads(content)` ensures valid JSON.
- Validates the presence of keys: `bullets`, `risk_factors`, `invalidation_signals`, `summary`.

## Fallback & Retry
- **Retry**: No automated retry loop. If it fails, it fails fast.
- **Fallback**: If the API call fails or times out, `_fallback_reasoning` builds a hardcoded dictionary using the input context (e.g., "Symbol technical posture is currently {signal}."). This guarantees the engine never crashes due to AI downtime.

## Confidence
The LLM does NOT determine the mathematical confidence. `confidence` is calculated deterministically in python: `min(0.95, max(0.35, score / 100))`.

## Cost
Groq is used for ultra-fast, cheap inference.
""",
    "15_dependencies.md": """# 15 Dependencies

## Modules Recommendation Depends On
- **`TechnicalAnalysisAgent`**: Provides base scores and directional bias.
- **`BacktestAgent`**: Provides historical win rates and max drawdowns.
- **`NewsAnalysisAgent`**: Provides sentiment score.
- **`FundamentalAnalysisAgent`**: Provides fundamental scores.
- **`FyersService`**: OHLCV data required for calculating current vs average volume.

## Modules That Depend on Recommendation
- **`RankingAgent`**: Needs the final scores and actions to sort the best BUY/WATCH candidates across a screened batch.
- **`OrchestratorAgent`**: Orchestrates the entire flow and persists the `recommendation.action` to the database.
""",
    "16_edge_cases.md": """# 16 Edge Cases

### Missing Candles / Live Data Unavailable
- **What happened**: Fyers returns empty arrays.
- **Expected & Actual**: The Orchestrator intercepts this before it hits the Recommendation Agent. It calls `_unavailable_analysis_result()`, which hardcodes a REJECT action and bypasses all scoring logic.

### AI Timeout / Invalid AI Response
- **What happened**: Groq takes >20s or returns malformed text.
- **Actual**: Exception is caught in `LLMService`. It immediately executes `_fallback_reasoning()`, generating deterministic strings so the recommendation payload still successfully builds.

### Extremely Low / Zero Volume
- **What happened**: `avg_volume` is 0.
- **Actual**: `RecommendationService` has a safeguard: `avg_volume = mean(...) if len(...) >= 20 else current_volume`. It prevents divide-by-zero when checking the volume catalyst (`current_volume > avg_volume * 3.0`).

### Duplicate Recommendations
- **Actual**: The Orchestrator maintains a `seen_symbols` set using `_dedupe_symbols()` during the screening phase, ensuring the Recommendation Agent is never called twice for the same ticker.
""",
    "17_failure_scenarios.md": """# 17 Failure Scenarios

## Wrong Recommendation (False BUY)
- **Root Cause**: Stale technical data or a bug in `TechnicalAnalysisResult` scoring artificially high.
- **Recovery**: The `_enforce_strict_buy_gate` acts as a fail-safe. Even if the score calculates incorrectly to 80, if the calculated `risk_reward_ratio` from the Trade Plan is `< 1.25`, the BUY is killed.

## Recommendation Delay
- **Root Cause**: `LLMService` taking too long.
- **Recovery**: Timeout is hard-capped at 20 seconds for reasoning.

## Inconsistent Recommendation
- **Root Cause**: LLM hallucinating different strings for the exact same inputs.
- **Recovery**: The LLM *only* dictates the human-readable reasoning strings. It has exactly *zero* authority over the actual Action (BUY/WATCH/REJECT) or the numerical Score/Confidence. Thus, trading logic remains 100% deterministic and consistent.
""",
    "18_debugging_guide.md": """# 18 Debugging Guide

If a recommendation is mysteriously wrong (e.g., you expect a BUY but get a WATCH), follow this exact workflow:

## 1. Check `logs/` for the Strict Buy Gate
Grep the logs for `STRICT BUY GATE`.
The `OrchestratorAgent` logs a massive diagnostic payload:
`STRICT BUY GATE EVALUATE | symbol=... | rec_score=... | best_tech_score=... | plan_rw=... | mock_warning=...`
If it says `STRICT BUY GATE DOWNGRADE`, the log will tell you exactly which boolean failed (e.g., `strong_execution=False`).

## 2. Which Files to Check
- `backend/app/services/recommendation_service.py` -> `build()` -> To see how the score was calculated.
- `backend/app/agents/orchestrator_agent.py` -> `_enforce_strict_buy_gate()` -> To see why it was overridden.

## 3. Which Database Tables
- `analysis_history`: Query `SELECT mode, technical_score, backtest_score, sentiment_score, recommendation FROM analysis_history WHERE symbol='...'`. You can reverse-engineer the math.

## 4. Redis Keys
- Redis is not used for this module.
""",
    "19_performance.md": """# 19 Performance & Scaling

## Performance & Concurrency
- The `RecommendationService` is a purely synchronous, CPU-bound mathematical calculation. It executes in milliseconds.
- Concurrency happens *before* the Recommendation Engine: `OrchestratorAgent` runs backtests, news, and fundamentals concurrently via `asyncio.gather` and `asyncio.to_thread`.
- The LLM network call for reasoning is made via `LLMService.build_reasoning` synchronously inside the RecommendationAgent execution flow (which is offloaded to a thread by the Orchestrator).

## Caching, Memory, CPU
- No specific caching layer is applied to the Recommendation output.
- Memory footprint is extremely light (processing basic Pydantic models).
- CPU cost is minimal; the heavy lifting was done during vectorized technical indicator calculation.
""",
    "20_database.md": """# 20 Database Interactions

## Tables
- `analysis_history`: The master record.

## Interactions
The Recommendation Engine does not query the database. It is a pure function taking inputs and returning outputs.
The `OrchestratorAgent` takes the resulting `FinalRecommendation` and inserts it into `analysis_history` inside `_persist_analysis()`:
- `recommendation`: Maps to `FinalRecommendation.action`
- `confidence`: Maps to `FinalRecommendation.confidence`
- `reasoning`: Maps to `FinalRecommendation.summary`

## Relationships
Linked via `stock_id` to the `watched_stocks` table.
""",
    "21_cache.md": """# 21 Cache Interactions

## Redis Usage
**Redis is completely bypassed for the Recommendation Engine.**

Every analysis run recalculates the recommendation dynamically based on the freshest technical and sentiment data. There are no TTLs, keys, or invalidation strategies applicable here.
""",
    "22_api_dependencies.md": """# 22 External API Dependencies

## Groq API
- **Purpose**: Generates the final reasoning (`bullets`, `risk_factors`, `invalidation_signals`, `summary`).
- **Endpoint**: `https://api.groq.com/openai/v1/chat/completions`
- **Timeout**: `20` seconds.
- **Retry**: None. Falls back instantly to deterministic python strings.
- **Rate Limits**: Subject to standard Groq tier limits. If 429 occurs, it falls back silently.
""",
    "23_code_walkthrough.md": """# 23 Code Walkthrough

## `backend/app/services/recommendation_service.py`
- **Purpose**: Core math for determining the trade action.
- **Methods**:
  - `build()`: Normalizes inputs, calls weight calculator, computes `0-100` score, defines action.
  - `calculate_dynamic_weights()`: Evaluates volume and news to toggle standard vs catalyst regime.
  - `_build_trade_plans()`: Analyzes price action (ATR/averages) to calculate Entry, Stop Loss, and Targets. Determines Long vs Short bias based on `technical.signal`.

## `backend/app/agents/recommendation_agent.py`
- **Purpose**: Orchestrates the LLM context gathering and calls the service.
- **Methods**:
  - `run()`: Builds the prompt context dict, calls `LLMService`, passes reasoning to `RecommendationService`.

## `backend/app/agents/orchestrator_agent.py` (Partial)
- **Role**: The gatekeeper.
- **Methods**:
  - `_enforce_strict_buy_gate()`: Takes the output from `RecommendationAgent` and applies strict trading rules. If RR < 1.25 or technicals < 75, it forcefully mutates `recommendation.action` to WATCH.
""",
    "24_sequence_diagrams.md": """# 24 Sequence Diagrams

## BUY Flow with Conflict Resolution & Strict Gate

```mermaid
sequenceDiagram
    participant O as OrchestratorAgent
    participant RA as RecommendationAgent
    participant RS as RecommendationService
    participant LLM as LLMService

    O->>RA: run(tech=80, news=0.9, vol=High)
    RA->>LLM: build_reasoning(...)
    LLM-->>RA: JSON Reasoning
    RA->>RS: build(tech, news, vol...)
    
    note right of RS: calculate_dynamic_weights()
    note right of RS: Catalyst Regime Activated (News 30%)
    note right of RS: Score calculates to 82 (BUY)
    
    RS-->>RA: FinalRecommendation(action="BUY")
    RA-->>O: FinalRecommendation
    
    O->>O: _enforce_strict_buy_gate()
    note left of O: Live Data? Yes.<br/>RR >= 1.25? Yes.<br/>Tech >= 75? Yes.
    
    O->>DB: Persist BUY
```
""",
    "25_learning_notes.md": """# 25 Learning Notes

## Architecture Decisions
- **Deterministic Action, Stochastic Reasoning**: The absolute best design choice in this module is that the LLM is completely isolated from the mathematical scoring. AI hallucinations cannot trigger bad trades; they can only produce weird text.
- **Gatekeeper Pattern**: By placing `_enforce_strict_buy_gate` in the Orchestrator instead of the Recommendation engine, the system preserves the "pure" output of the Recommendation scoring while still enforcing a rigid safety net at the execution layer.

## Best Practices
- **Dynamic Weighting**: Handling conflicting indicators via regimes (Catalyst vs Standard) prevents "flat" averaging which often kills good setups.

## Common Mistakes
- **Assuming HOLD exists**: New developers might try to search for HOLD logic. It doesn't exist. The engine is an entry scanner.
- **Debugging Score vs Output**: If a stock scores 85 but returns WATCH, developers might assume the math is broken. It is not; the `_enforce_strict_buy_gate` intercepted it.

## Interview Questions
**Q: How does the system handle a situation where Technicals are brilliant but News is disastrous?**
A: Extreme news scores trigger the Catalyst Regime in `calculate_dynamic_weights`. The News weight jumps to 30%, suppressing the Technical score, dragging the total score below the 55 (WATCH) or 72 (BUY) thresholds, resulting in a REJECT.
"""
}

for filename, content in files.items():
    with open(os.path.join(docs_dir, filename), "w", encoding="utf-8") as f:
        f.write(content.strip())

print("Successfully generated all recommendation engine documentation files.")
