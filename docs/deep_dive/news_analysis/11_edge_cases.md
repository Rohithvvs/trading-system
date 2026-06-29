# 11 Edge Cases

## No News Available
- **What happened**: APIs return empty results.
- **Expected behavior**: Gracefully continue without news.
- **Actual implementation**: `NewsAnalysisAgent` detects empty lists and returns `[], 0.5, "Neutral", "No recent news found"`.

## API Timeout
- **What happened**: Custom API or DDG takes too long.
- **Expected behavior**: Fast fail.
- **Actual implementation**: Both `requests.get` use `timeout=6`. Exceptions are caught and ignored (returns `[]`).

## Duplicate Articles
- **Actual implementation**: Not implemented in repository. Returns whatever the API provides.

## Conflicting News / Fake News
- **Actual implementation**: Handled implicitly by the LLM which averages sentiment. No specific fake news detection.

## LLM Unavailable
- **Actual implementation**: `requests.post` timeout or 5xx. Exception caught in `LLMService`, logs error, returns `0.0`.

## Ticker Mapping Failures
- **Actual implementation**: Appends " NSE news" to the ticker. If the ticker is obscure, DDG might return irrelevant topics. No rigorous validation exists.