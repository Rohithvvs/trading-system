"""Unit tests for FEAT-018 Sentiment Time-Decay pure function.

Spec source: specs/014-shadow-sentiment-breadth/spec.md
  - US1 acceptance scenarios 1–2
  - FR-001, FR-002, FR-003, FR-010
  - Edge cases: missing timestamps, empty news feed, future timestamps
  - SC-004: 100% of articles older than 72h are zeroed
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.analysis import ArticleItem
from app.schemas.shadow_telemetry import DecayedArticleDetail, SentimentDecayTelemetry
from app.services.sentiment_decay import calculate_sentiment_time_decay


def _article(
    title: str,
    score: float,
    published_at: datetime | None,
    url: str | None = None,
) -> ArticleItem:
    return ArticleItem(
        title=title,
        sentiment_score=score,
        published_at=published_at,
        url=url or f"http://example.com/{title.replace(' ', '-').lower()}",
    )


# ---------------------------------------------------------------------------
# Core math / acceptance scenarios
# ---------------------------------------------------------------------------


def test_sentiment_time_decay_exponential_half_life():
    """US1-AS1 / FR-001: exponential half-life w(t)=2^(-t/24)."""
    now = datetime.now(timezone.utc)
    articles = [
        _article("Fresh News", 100.0, now),
        _article("1 Day Old", 100.0, now - timedelta(hours=24)),
        _article("2 Days Old", 100.0, now - timedelta(hours=48)),
    ]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert result.article_count == 3
    assert result.zeroed_article_count == 0

    # Article 0: 0h -> mult = 1.0 -> 100.0
    assert result.articles[0].decay_multiplier == 1.0
    assert result.articles[0].decayed_sentiment == 100.0
    assert result.articles[0].raw_sentiment == 100.0
    assert result.articles[0].age_hours == 0.0

    # Article 1: 24h -> mult = 0.5 -> 50.0
    assert pytest.approx(result.articles[1].decay_multiplier, abs=0.01) == 0.5
    assert pytest.approx(result.articles[1].decayed_sentiment, abs=0.1) == 50.0
    assert pytest.approx(result.articles[1].age_hours, abs=0.01) == 24.0

    # Article 2: 48h -> mult = 0.25 -> 25.0
    assert pytest.approx(result.articles[2].decay_multiplier, abs=0.01) == 0.25
    assert pytest.approx(result.articles[2].decayed_sentiment, abs=0.1) == 25.0
    assert pytest.approx(result.articles[2].age_hours, abs=0.01) == 48.0


def test_sentiment_time_decay_decayed_score_never_exceeds_raw():
    """US1-AS1: each decayed score is strictly <= raw score for ages within 72h."""
    now = datetime.now(timezone.utc)
    articles = [
        _article("2h", 80.0, now - timedelta(hours=2)),
        _article("12h", 60.0, now - timedelta(hours=12)),
        _article("36h", 40.0, now - timedelta(hours=36)),
        _article("71h", 90.0, now - timedelta(hours=71)),
    ]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    for detail in result.articles:
        assert detail.decayed_sentiment <= detail.raw_sentiment
        assert detail.decay_multiplier <= 1.0
        assert detail.decay_multiplier > 0.0


def test_sentiment_time_decay_72h_hard_cutoff():
    """US1-AS2 / FR-002 / SC-004: articles older than 72h are fully zeroed."""
    now = datetime.now(timezone.utc)
    articles = [
        _article("71 Hours Old", 80.0, now - timedelta(hours=71)),
        _article("73 Hours Old", 80.0, now - timedelta(hours=73)),
        _article("5 Days Old", 90.0, now - timedelta(days=5)),
    ]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert result.article_count == 3
    assert result.zeroed_article_count == 2

    # 71h -> mult > 0
    assert result.articles[0].decay_multiplier > 0.0
    assert result.articles[0].decayed_sentiment > 0.0

    # 73h -> zeroed out
    assert result.articles[1].decay_multiplier == 0.0
    assert result.articles[1].decayed_sentiment == 0.0

    # 5d -> zeroed out
    assert result.articles[2].decay_multiplier == 0.0
    assert result.articles[2].decayed_sentiment == 0.0


def test_sentiment_time_decay_exactly_72h_boundary():
    """Boundary: age == 72.0 is within cutoff window (strict > 72 zeros)."""
    now = datetime.now(timezone.utc)
    articles = [_article("Exactly 72h", 100.0, now - timedelta(hours=72))]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert result.zeroed_article_count == 0
    assert result.articles[0].age_hours == 72.0
    # w(72) = 2^(-72/24) = 2^-3 = 0.125
    assert pytest.approx(result.articles[0].decay_multiplier, abs=0.001) == 0.125
    assert pytest.approx(result.articles[0].decayed_sentiment, abs=0.1) == 12.5


def test_sentiment_time_decay_just_over_72h_zeroed():
    """Boundary: age slightly above 72h is zeroed (FR-002)."""
    now = datetime.now(timezone.utc)
    articles = [_article("72.01h", 100.0, now - timedelta(hours=72, seconds=36))]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert result.zeroed_article_count == 1
    assert result.articles[0].decay_multiplier == 0.0
    assert result.articles[0].decayed_sentiment == 0.0


# ---------------------------------------------------------------------------
# Diagnostic telemetry (FR-003)
# ---------------------------------------------------------------------------


def test_sentiment_time_decay_diagnostic_telemetry_fields():
    """FR-003: per-article diagnostics include raw, decayed, age, multiplier."""
    now = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)
    articles = [
        _article(
            "Earnings Beat",
            80.0,
            now - timedelta(hours=24),
            url="http://news.example/101",
        ),
    ]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert isinstance(result, SentimentDecayTelemetry)
    detail = result.articles[0]
    assert isinstance(detail, DecayedArticleDetail)
    assert detail.article_id == "http://news.example/101"
    assert detail.title == "Earnings Beat"
    assert detail.published_at is not None
    assert detail.age_hours == 24.0
    assert detail.raw_sentiment == 80.0
    assert pytest.approx(detail.decay_multiplier, abs=0.01) == 0.5
    assert pytest.approx(detail.decayed_sentiment, abs=0.1) == 40.0
    assert result.executed_at  # ISO timestamp present


def test_sentiment_time_decay_aggregate_weighted_average():
    """Aggregate decayed score is weight-normalized average of decayed values."""
    now = datetime.now(timezone.utc)
    # Fresh 100 @ mult 1.0 and 24h 100 @ mult 0.5
    # weighted = (100*1 + 100*0.5) / (1 + 0.5) = 150/1.5 = 100
    # Wait: decayed_score = raw * mult, aggregate = sum(decayed)/sum(mult)
    # = (100 + 50) / (1 + 0.5) = 100
    articles = [
        _article("Fresh", 100.0, now),
        _article("Day Old", 100.0, now - timedelta(hours=24)),
    ]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert result.aggregate_raw_score == 100.0
    assert pytest.approx(result.aggregate_decayed_score, abs=0.1) == 100.0
    assert result.decayed_article_count == 1  # only the non-1.0 multiplier counts


def test_sentiment_time_decay_aggregate_all_zeroed():
    """When every article is zeroed, aggregate decayed score is 0.0."""
    now = datetime.now(timezone.utc)
    articles = [
        _article("Stale A", 80.0, now - timedelta(hours=100)),
        _article("Stale B", 60.0, None),
    ]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert result.zeroed_article_count == 2
    assert result.aggregate_decayed_score == 0.0
    assert result.aggregate_raw_score == 70.0  # mean of raw


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_sentiment_time_decay_missing_timestamp_zeroed():
    """Edge: missing published_at treated as max age and zeroed."""
    now = datetime.now(timezone.utc)
    articles = [_article("No Timestamp", 80.0, None)]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert result.article_count == 1
    assert result.zeroed_article_count == 1
    assert result.articles[0].decay_multiplier == 0.0
    assert result.articles[0].decayed_sentiment == 0.0
    assert result.articles[0].published_at is None
    assert result.articles[0].age_hours > 72.0


def test_sentiment_time_decay_empty_list():
    """Edge: empty news feed returns neutral/empty telemetry without failure."""
    now = datetime.now(timezone.utc)
    result = calculate_sentiment_time_decay([], scan_time=now)

    assert result.article_count == 0
    assert result.decayed_article_count == 0
    assert result.zeroed_article_count == 0
    assert result.aggregate_raw_score == 0.0
    assert result.aggregate_decayed_score == 0.0
    assert result.articles == []
    assert result.executed_at


def test_sentiment_time_decay_future_timestamp_clamped_to_zero_age():
    """Edge: future publication timestamps clamp age to 0 (full weight)."""
    now = datetime.now(timezone.utc)
    articles = [_article("Future Headline", 50.0, now + timedelta(hours=5))]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert result.articles[0].age_hours == 0.0
    assert result.articles[0].decay_multiplier == 1.0
    assert result.articles[0].decayed_sentiment == 50.0


def test_sentiment_time_decay_naive_datetime_treated_as_utc():
    """Timezone: naive published_at is interpreted as UTC."""
    scan = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)
    naive_pub = datetime(2026, 7, 21, 12, 0, 0)  # 24h earlier, no tz
    articles = [_article("Naive TS", 100.0, naive_pub)]

    result = calculate_sentiment_time_decay(articles, scan_time=scan)

    assert pytest.approx(result.articles[0].age_hours, abs=0.01) == 24.0
    assert pytest.approx(result.articles[0].decay_multiplier, abs=0.01) == 0.5


def test_sentiment_time_decay_negative_sentiment_preserved_sign():
    """Negative raw sentiment still decays proportionally (sign preserved)."""
    now = datetime.now(timezone.utc)
    articles = [_article("Bad News", -80.0, now - timedelta(hours=24))]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert result.articles[0].raw_sentiment == -80.0
    assert pytest.approx(result.articles[0].decayed_sentiment, abs=0.1) == -40.0


def test_sentiment_time_decay_zero_raw_score():
    """Boundary: zero raw sentiment yields zero decayed score at any age."""
    now = datetime.now(timezone.utc)
    articles = [_article("Neutral", 0.0, now - timedelta(hours=12))]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert result.articles[0].decayed_sentiment == 0.0
    assert result.articles[0].decay_multiplier > 0.0


def test_sentiment_time_decay_does_not_mutate_input_articles():
    """FR-010 / purity: pure function must not mutate caller article list."""
    now = datetime.now(timezone.utc)
    original = _article("Immutable", 75.0, now - timedelta(hours=6))
    articles = [original]
    snapshot_score = original.sentiment_score
    snapshot_ts = original.published_at

    calculate_sentiment_time_decay(articles, scan_time=now)

    assert original.sentiment_score == snapshot_score
    assert original.published_at == snapshot_ts
    assert len(articles) == 1


def test_sentiment_time_decay_default_scan_time_when_none():
    """scan_time=None uses current UTC and still produces valid telemetry."""
    articles = [_article("Now-ish", 10.0, datetime.now(timezone.utc))]

    result = calculate_sentiment_time_decay(articles, scan_time=None)

    assert result.article_count == 1
    assert result.articles[0].decay_multiplier <= 1.0
    assert result.executed_at


def test_sentiment_time_decay_mixed_valid_and_invalid_articles():
    """Mixed feed: only stale/missing timestamps contribute to zeroed count."""
    now = datetime.now(timezone.utc)
    articles = [
        _article("Fresh", 90.0, now),
        _article("Missing", 70.0, None),
        _article("Stale", 50.0, now - timedelta(hours=90)),
        _article("Day Old", 80.0, now - timedelta(hours=24)),
    ]

    result = calculate_sentiment_time_decay(articles, scan_time=now)

    assert result.article_count == 4
    assert result.zeroed_article_count == 2
    assert result.aggregate_decayed_score > 0.0
    # Decayed scores for non-zeroed articles remain positive
    non_zero = [a for a in result.articles if a.decay_multiplier > 0]
    assert len(non_zero) == 2
