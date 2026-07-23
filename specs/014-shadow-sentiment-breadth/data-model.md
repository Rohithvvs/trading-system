# Phase 1 Data Model: Shadow Candidate Features — Sentiment Time-Decay & Market Breadth

**Feature**: `014-shadow-sentiment-breadth`  
**Date**: 2026-07-22  
**Status**: Completed  

---

## 1. Domain Entities & Schemas

### Entity 1: `ArticleSentimentItem` (Input Data Structure)
Represents a single news article with raw sentiment score and publication timestamp.

- **`article_id`**: `str` — Unique identifier or URL of the article.
- **`title`**: `str` — Article headline.
- **`published_at`**: `datetime | None` — Publication timestamp (timezone-aware UTC).
- **`raw_sentiment_score`**: `float` — Original sentiment score (range: $[-100.0, 100.0]$ or $[0.0, 100.0]$).

---

### Entity 2: `SentimentDecayResult` (Output Schema for `shadow_outputs["sentiment_decay"]`)

```json
{
  "aggregate_raw_score": 75.0,
  "aggregate_decayed_score": 52.4,
  "article_count": 3,
  "decayed_article_count": 2,
  "zeroed_article_count": 1,
  "articles": [
    {
      "article_id": "news_101",
      "title": "Earnings Beat Expectations",
      "published_at": "2026-07-21T10:00:00Z",
      "age_hours": 24.0,
      "raw_sentiment": 80.0,
      "decay_multiplier": 0.5,
      "decayed_sentiment": 40.0
    },
    {
      "article_id": "news_102",
      "title": "Old Market Analysis",
      "published_at": "2026-07-18T08:00:00Z",
      "age_hours": 98.0,
      "raw_sentiment": 60.0,
      "decay_multiplier": 0.0,
      "decayed_sentiment": 0.0
    }
  ],
  "executed_at": "2026-07-22T10:44:00Z"
}
```

---

### Entity 3: `StockBreadthItem` (Input Data Structure)
Represents technical data for a single universe stock required to compute market breadth.

- **`symbol`**: `str` — Stock ticker symbol.
- **`current_price`**: `float | None` — Latest closing or market price.
- **`sma_200`**: `float | None` — 200-day simple moving average price.

---

### Entity 4: `MarketBreadthResult` (Output Schema for `shadow_outputs["market_breadth"]`)

```json
{
  "universe_size": 50,
  "valid_stock_count": 48,
  "above_200ma_count": 36,
  "breadth_percentage": 75.0,
  "regime_label": "strong",
  "soft_score_contribution": 15.0,
  "is_valid": true,
  "executed_at": "2026-07-22T10:44:00Z"
}
```

---

### Entity 5: `AnalysisHistory.shadow_outputs` (JSONB Database Column Payload)

Full structure of `shadow_outputs` stored in `analysis_history` table:

```json
{
  "news_dedup": {
    "original_news_count": 5,
    "kept_news_count": 3,
    "removed_news_count": 2,
    "executed_at": "2026-07-22T10:44:00Z"
  },
  "sentiment_decay": {
    "aggregate_raw_score": 75.0,
    "aggregate_decayed_score": 52.4,
    "article_count": 3,
    "decayed_article_count": 2,
    "zeroed_article_count": 1,
    "articles": [],
    "executed_at": "2026-07-22T10:44:00Z"
  },
  "market_breadth": {
    "universe_size": 50,
    "valid_stock_count": 48,
    "above_200ma_count": 36,
    "breadth_percentage": 75.0,
    "regime_label": "strong",
    "soft_score_contribution": 15.0,
    "is_valid": true,
    "executed_at": "2026-07-22T10:44:00Z"
  }
}
```
