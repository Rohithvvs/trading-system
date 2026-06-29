# 17 API Interactions

## 1. Custom News API
- **URL**: `settings.news_api_url + "/search"`
- **Authentication**: `api_key` in query params.
- **Format**: `GET ?q={symbol} NSE news&api_key={key}`
- **Retries/Timeout**: No retries. 6-second timeout.

## 2. DuckDuckGo API (Fallback)
- **URL**: `https://api.duckduckgo.com/`
- **Authentication**: None.
- **Format**: `GET ?q={symbol} NSE news&format=json&no_html=1&skip_disambig=1`
- **Retries/Timeout**: No retries. 6-second timeout.

## 3. Groq API
- **URL**: `https://api.groq.com/openai/v1/chat/completions`
- **Authentication**: Bearer Token (`settings.llm_api_key`)
- **Format**: `POST` with JSON payload containing `model`, `messages`, and `response_format`.
- **Retries/Timeout**: No retries. 10-second timeout for sentiment, 20-second for reasoning.