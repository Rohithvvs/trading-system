# Recommendation Engine: AI/LLM Integration

The system uses an external LLM (Groq APIs running OpenAI-compatible models) to analyze unstructured data (news) and to synthesize complex metric structures into human-readable text.

## 1. Sentiment Analysis (`LLMService.analyze_sentiment`)
- **Purpose:** Convert raw news headlines into a quantitative float.
- **Prompt:**
  > "You are a quantitative sentiment analyzer. Respond with valid JSON only. Evaluate the following headlines for the given stock symbol and return a clean, minified JSON object containing a numeric 'sentiment_score' strictly bounded between -1.0 (highly catastrophic/bearish) and 1.0 (highly disruptive/bullish)."
- **Input:** `symbol` and a JSON stringified list of headlines.
- **Response Format:** Enforced JSON object `{"sentiment_score": float}`.
- **Validation:** Extracts the float and clamps it: `max(-1.0, min(1.0, score))`.
- **Fallback:** If the API fails or times out (10s), returns `0.0`.
- **Cost:** Uses low temperature (`0.0`) and fast/cheap models via Groq.

## 2. Reasoning Generation (`LLMService.build_reasoning`)
- **Purpose:** Translate the mathematical evaluation into readable English.
- **Prompt:**
  > "You are a trading analysis assistant. Respond with valid JSON only. Keep output advisory-only and never mention automated execution. Return keys: bullets, risk_factors, invalidation_signals, summary."
  > "Write 3 concise reasoning bullets, 2 risk factors, 2 invalidation signals, and a 1-2 sentence summary."
- **Input:** JSON payload of `technical_signal`, `technical_score`, `news_label`, `sentiment_score`, `backtest_verdict`, `fundamental_score`, `current_price`.
- **Response Format:** JSON object.
- **Validation:** Checks that all 4 required keys (`bullets`, `risk_factors`, `invalidation_signals`, `summary`) exist.
- **Fallback:** If Groq API fails or is unconfigured, it uses `_fallback_reasoning()`. This method uses Python string formatting to generate hardcoded, but accurate, summary strings based on the same input context.

## Retry and Timeout
- **Sentiment:** Timeout 10s. No internal retry loop (fails fast to `0.0`).
- **Reasoning:** Timeout 20s. No internal retry loop (fails fast to `_fallback_reasoning()`).
*Design Decision:* Speed in the main event loop is prioritized over LLM text generation. If the LLM is slow, the system degrades gracefully rather than stalling the pipeline.
