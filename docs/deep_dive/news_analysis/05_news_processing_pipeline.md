# 05 News Processing Pipeline

## Cleaning and Filtering
- The `NewsService` extracts only the `title`, `description`, `source.name`, `url`, and `published_at` from the upstream API.
- The fallback DuckDuckGo API uses `no_html=1` to ensure raw text without HTML tags.
- Max 10 articles are preserved. 

## Normalization
- Raw JSON is converted into Pydantic `ArticleItem` schemas (`app/schemas/analysis.py`).
- Dates are parsed from ISO format; if missing, they default to `datetime.utcnow()`.
- Sentiment scores at the article level are initialized to `0.0` (overall sentiment is scored at the batch level later).

## Duplicate Detection
- Not implemented in repository.

## Language Handling
- Implicitly expects English. No translation layer exists.

## Ticker/Company Mapping
- The `symbol` is passed directly to the search query appended with `" NSE news"`. (e.g., `RELIANCE NSE news`).
- No explicit mapping from Ticker to formal Company Name (e.g., "TCS" -> "Tata Consultancy Services") is performed before the search.