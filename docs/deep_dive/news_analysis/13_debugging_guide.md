# 13 Debugging Guide

## Debugging Workflow
If News Analysis behaves incorrectly (e.g., always returning neutral, or crashing the screener):

### 1. Inspect Logs
- Check `logs/` directory (or stdout).
- Grep for `app.sentiment` to see LLM failures.
- Grep for `app.llm_service` to catch 4xx/5xx from Groq.

### 2. Inspect Files
- `app/services/news_service.py`: To verify the API URL and DDG fallback.
- `app/services/llm_service.py`: To check prompt structure and Groq connection.

### 3. Test API Connections
Run manual `requests` calls to:
- `settings.news_api_url`
- `api.duckduckgo.com`
- `api.groq.com`

### 4. Database Verification
- Check the `analysis_history` table:
  `SELECT symbol, sentiment_score FROM analysis_history ORDER BY id DESC LIMIT 10;`
- If scores are all exactly `0.0` or `0.5`, the LLM or News Service is failing silently.