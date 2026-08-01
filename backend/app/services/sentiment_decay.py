from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.schemas.analysis import ArticleItem
from app.schemas.shadow_telemetry import DecayedArticleDetail, SentimentDecayTelemetry


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def calculate_sentiment_time_decay(
    articles: list[ArticleItem],
    scan_time: datetime | None = None,
    half_life_hours: float = 24.0,
    max_age_hours: float = 72.0,
) -> SentimentDecayTelemetry:
    """Pure function calculating exponential time-decay for news article sentiment.

    - Half-life formula: w(t) = 2^(-t / 24.0)
    - Hard cutoff: any article older than max_age_hours (72.0h) receives multiplier = 0.0
    - Missing timestamps default to age > max_age_hours (0.0 multiplier)
    - Zero side-effects
    """
    if scan_time is None:
        scan_time = datetime.now(timezone.utc)
    else:
        scan_time = _as_utc(scan_time) or datetime.now(timezone.utc)

    detailed_articles: list[DecayedArticleDetail] = []
    total_raw_weight = 0.0
    total_weighted_decayed_sentiment = 0.0
    total_raw_sentiment = 0.0

    decayed_count = 0
    zeroed_count = 0

    for article in articles:
        raw = float(getattr(article, "sentiment_score", 0.0) or getattr(article, "score", 0.0) or 0.0)
        published_at_utc = _as_utc(article.published_at)

        if published_at_utc is None:
            age_hours = max_age_hours + 1.0
        else:
            age_seconds = (scan_time - published_at_utc).total_seconds()
            age_hours = max(0.0, age_seconds / 3600.0)

        if age_hours > max_age_hours:
            multiplier = 0.0
            zeroed_count += 1
        else:
            multiplier = math.pow(2.0, -age_hours / half_life_hours)
            if multiplier < 1.0:
                decayed_count += 1

        decayed_score = raw * multiplier

        art_id = getattr(article, "url", None) or f"{article.title}|{article.published_at}"
        detailed_articles.append(
            DecayedArticleDetail(
                article_id=str(art_id),
                title=article.title or "",
                published_at=published_at_utc.isoformat() if published_at_utc else None,
                age_hours=round(age_hours, 2),
                raw_sentiment=round(raw, 2),
                decay_multiplier=round(multiplier, 4),
                decayed_sentiment=round(decayed_score, 2),
            )
        )

        total_raw_sentiment += raw
        total_raw_weight += multiplier
        total_weighted_decayed_sentiment += decayed_score

    article_count = len(articles)
    if article_count > 0:
        agg_raw = total_raw_sentiment / article_count
    else:
        agg_raw = 0.0

    if total_raw_weight > 0:
        agg_decayed = total_weighted_decayed_sentiment / total_raw_weight
    else:
        agg_decayed = 0.0

    return SentimentDecayTelemetry(
        aggregate_raw_score=round(agg_raw, 2),
        aggregate_decayed_score=round(agg_decayed, 2),
        article_count=article_count,
        decayed_article_count=decayed_count,
        zeroed_article_count=zeroed_count,
        articles=detailed_articles,
        executed_at=scan_time.isoformat(),
    )
