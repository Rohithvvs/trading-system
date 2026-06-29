# 07 LLM Integration

## Provider Configuration
- Uses **Groq** via `https://api.groq.com/openai/v1/chat/completions`.
- Triggered only if `settings.llm_provider.lower() == "groq"` and `settings.llm_api_key` is set.

## Prompt Structure
- **System**: Defines the persona ("quantitative sentiment analyzer" or "trading analysis assistant") and enforces JSON output.
- **User**: Passes the `Symbol` and `Headlines` (as a JSON dumped string).

## Input and Output
- **Input**: A list of strings (headlines).
- **Output**: JSON containing `sentiment_score` (float). For reasoning, it outputs `bullets`, `risk_factors`, `invalidation_signals`, and `summary`.
- **Response Format**: Uses `"response_format": {"type": "json_object"}` to guarantee JSON.

## Response Validation & Fallback Strategy
- The payload is parsed via `json.loads`.
- If the `sentiment_score` key is missing, it defaults to `0.0`.
- The score is clamped using `max(-1.0, min(1.0, score))` to prevent rogue LLM outputs.
- **Fallback**: If the Groq API fails, times out (`timeout=10`), or throws an exception, `LLMService` catches it, logs `"LLM sentiment analysis failed"`, and returns `0.0`. No retry logic is implemented.

## Cost Considerations
- Groq is utilized for fast, low-cost inference. The prompt is kept minimal ("clean, minified JSON object") to reduce token usage.