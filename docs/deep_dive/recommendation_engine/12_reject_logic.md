# Recommendation Engine: REJECT Logic

The `REJECT` recommendation explicitly advises avoiding the asset.

## Every Rule to Achieve REJECT

### 1. Standard Scoring Threshold
The weighted `Final Score` falls strictly below **55.0**.
This happens when the technical structure is broken (bearish), fundamentals are terrible, or news is overwhelmingly negative.

### 2. Missing Live Data
If the `OrchestratorAgent` detects that NO live OHLCV data is available across the required modes (empty candle arrays), it instantly hardcodes a REJECT.
```python
recommendation = self.recommendation_agent.recommendation_service.build(...)
recommendation = recommendation.model_copy(update={
    "action": "REJECT", 
    "confidence": 0.0, 
    "score": 0.0, 
    "trade_plans": []
})
```
This is a safety mechanism to prevent stale advisory.

## Examples

**Example A (Bearish Setup):**
- Technical Score: 30 (Bearish)
- Final Weighted Score: 38
- **Result:** REJECT. The stock is in a downtrend.

**Example B (Data Failure):**
- Fyers API fails to return data. SQLite cache is empty.
- Engine detects `len(candles) == 0`.
- **Result:** Forced REJECT with 0.0 score and confidence.
