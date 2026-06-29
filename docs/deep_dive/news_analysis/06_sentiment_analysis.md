# 06 Sentiment Analysis

## How Sentiment is Determined
Sentiment is evaluated at the batch level rather than per-article. `SentimentService.summarize` extracts headlines from all `ArticleItem`s and passes them to `LLMService.analyze_sentiment`.

## Scoring
The LLM returns a single float (`sentiment_score`) between `-1.0` and `1.0`.

## Labeling
In `SentimentService.summarize`, the float score is mapped to a categorical label:
- **Positive**: `score >= 0.2`
- **Negative**: `score <= -0.2`
- **Neutral**: `-0.2 < score < 0.2`

## Keywords
Not implemented. The system relies entirely on the LLM's semantic understanding rather than keyword matching.

## Prompting
The `LLMService` uses the following system prompt for sentiment:
*"You are a quantitative sentiment analyzer. Respond with valid JSON only. Evaluate the following headlines for the given stock symbol and return a clean, minified JSON object containing a numeric 'sentiment_score' strictly bounded between -1.0 (highly catastrophic/bearish) and 1.0 (highly disruptive/bullish)."*

## Model Selection
If `settings.llm_provider` is "groq", it calls Groq's API using `settings.llm_model`.

## Real Examples
If 10 headlines show "Record profits for Q3", the LLM parses the JSON, outputs `{"sentiment_score": 0.85}`, and the label becomes `positive`.