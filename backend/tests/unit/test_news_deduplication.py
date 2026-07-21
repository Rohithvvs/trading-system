"""Unit tests for FEAT-014 pure news deduplication heuristic.

Spec source: specs/011-news-deduplication/spec.md
Covers FR-001 through FR-006, SC-001, and related edge cases.
"""
from __future__ import annotations

import copy
import datetime
from datetime import timedelta

import pytest

from app.schemas.analysis import ArticleItem
from app.services.news_deduplication import (
    STOP_WORDS,
    _clean_title,
    _get_source_priority,
    deduplicate_articles,
)


def _create_article(
    title: str,
    published_at: datetime.datetime,
    source: str = "Unknown",
    url: str = "http://example.com/art",
    description: str = "",
    sentiment_score: float = 0.0,
) -> ArticleItem:
    return ArticleItem(
        title=title,
        published_at=published_at,
        source=source,
        url=url,
        description=description,
        sentiment_score=sentiment_score,
    )


# ---------------------------------------------------------------------------
# Edge cases (empty / single / purity)
# ---------------------------------------------------------------------------


def test_empty_article_list_returns_empty() -> None:
    """FR-006 / edge: empty input returns empty list without raising."""
    assert deduplicate_articles([]) == []


def test_single_article_returned_as_is() -> None:
    """Edge: single article is returned unchanged."""
    art = _create_article("Single Headline", datetime.datetime(2023, 1, 1, 12, 0, 0))
    result = deduplicate_articles([art])
    assert len(result) == 1
    assert result[0].url == art.url
    assert result[0].title == art.title


def test_pure_function_does_not_mutate_input() -> None:
    """FR-006: deduplicate_articles must not mutate the caller's list or items."""
    base = datetime.datetime(2023, 1, 1, 12, 0, 0)
    articles = [
        _create_article("AAPL Earnings Beat", base, source="CNBC", url="http://example.com/1"),
        _create_article("AAPL Earnings Beat", base + timedelta(minutes=5), source="Reuters", url="http://example.com/2"),
    ]
    original = copy.deepcopy(articles)

    result = deduplicate_articles(articles)

    assert len(articles) == len(original)
    assert [a.url for a in articles] == [a.url for a in original]
    assert [a.title for a in articles] == [a.title for a in original]
    assert len(result) == 1  # collapsed, but input intact


# ---------------------------------------------------------------------------
# Input capping (FR-001 / US1 SC3)
# ---------------------------------------------------------------------------


def test_input_capping_keeps_50_most_recent() -> None:
    """FR-001: cap input at the 50 most recent articles before deduplication.

    Titles intentionally share fewer than 3 non-stop words so only the cap
    (not duplicate collapse) reduces the count.
    """
    base_time = datetime.datetime(2023, 1, 1, 12, 0, 0)
    articles = [
        _create_article(
            f"Headline{i}",
            base_time + timedelta(minutes=i),
            url=f"http://example.com/{i}",
        )
        for i in range(60)
    ]

    result = deduplicate_articles(articles)

    assert len(result) == 50
    sorted_result = sorted(result, key=lambda x: x.published_at)
    # Most recent 50 are indices 10..59
    assert sorted_result[0].title == "Headline10"
    assert sorted_result[-1].title == "Headline59"


def test_input_capping_exactly_50_unchanged_count() -> None:
    """Boundary: exactly 50 distinct articles all pass through."""
    base_time = datetime.datetime(2023, 1, 1, 12, 0, 0)
    articles = [
        _create_article(
            f"Topic{i}",
            base_time + timedelta(minutes=i),
            url=f"http://example.com/exact/{i}",
        )
        for i in range(50)
    ]
    result = deduplicate_articles(articles)
    assert len(result) == 50


# ---------------------------------------------------------------------------
# Stop words, punctuation, word overlap (FR-003)
# ---------------------------------------------------------------------------


def test_stop_words_and_punctuation_stripping() -> None:
    """FR-003 / edge: stop words and punctuation are ignored before overlap check."""
    base_time = datetime.datetime(2023, 1, 1, 12, 0, 0)

    art1 = _create_article(
        "the AAPL is a big Earnings Beat for today!",
        base_time,
        source="Reuters",
        url="http://example.com/1",
    )
    art2 = _create_article(
        "AAPL: Earnings Beat!",
        base_time + timedelta(minutes=10),
        source="CNBC",
        url="http://example.com/2",
    )

    result = deduplicate_articles([art1, art2])

    assert len(result) == 1
    assert result[0].url == "http://example.com/1"


def test_special_characters_in_titles_match() -> None:
    """Edge: 'AAPL: Earnings Beat!' and 'AAPL - Earnings Beat' match after stripping."""
    base = datetime.datetime(2023, 1, 1, 12, 0, 0)
    art1 = _create_article("AAPL: Earnings Beat!", base, source="Bloomberg", url="http://example.com/colon")
    art2 = _create_article("AAPL - Earnings Beat", base + timedelta(minutes=1), source="CNBC", url="http://example.com/dash")

    result = deduplicate_articles([art1, art2])
    assert len(result) == 1
    assert result[0].url == "http://example.com/colon"


def test_two_word_overlap_does_not_collapse() -> None:
    """FR-003 boundary: fewer than 3 shared non-stop words must not collapse."""
    base = datetime.datetime(2023, 1, 1, 12, 0, 0)
    # Shared: AAPL, Earnings (only 2 non-stop words)
    art1 = _create_article("AAPL Earnings Rise", base, url="http://example.com/1")
    art2 = _create_article("AAPL Earnings Fall", base + timedelta(minutes=5), url="http://example.com/2")

    result = deduplicate_articles([art1, art2])
    assert len(result) == 2


def test_case_insensitive_title_matching() -> None:
    """FR-003: title word overlap is case-insensitive."""
    base = datetime.datetime(2023, 1, 1, 12, 0, 0)
    art1 = _create_article("aapl earnings beat", base, source="Reuters", url="http://example.com/lower")
    art2 = _create_article("AAPL EARNINGS BEAT", base + timedelta(minutes=2), source="CNBC", url="http://example.com/upper")

    result = deduplicate_articles([art1, art2])
    assert len(result) == 1
    assert result[0].url == "http://example.com/lower"


def test_clean_title_filters_stop_words() -> None:
    """Unit: _clean_title removes configured stop words and punctuation."""
    words = _clean_title("The AAPL is a Big Earnings Beat for Today!")
    assert "aapl" in words
    assert "earnings" in words
    assert "beat" in words
    assert "big" in words
    assert "today" in words
    for stop in ("the", "is", "a", "for"):
        assert stop not in words
    assert STOP_WORDS.issuperset({"the", "a", "and", "of", "in", "on", "for", "with", "to", "is"})


# ---------------------------------------------------------------------------
# 4-hour window grouping (FR-002)
# ---------------------------------------------------------------------------


def test_four_hour_window_grouping() -> None:
    """FR-002: articles spanning more than 4 hours belong to different windows."""
    base_time = datetime.datetime(2023, 1, 1, 12, 0, 0)

    art1 = _create_article("AAPL Earnings Beat", base_time, url="http://example.com/1")
    art2 = _create_article(
        "AAPL Earnings Beat",
        base_time + timedelta(hours=3, minutes=59),
        url="http://example.com/2",
    )
    art3 = _create_article(
        "AAPL Earnings Beat",
        base_time + timedelta(hours=4, minutes=1),
        url="http://example.com/3",
    )

    result = deduplicate_articles([art1, art2, art3])

    assert len(result) == 2
    urls = {a.url for a in result}
    assert "http://example.com/3" in urls


def test_exactly_four_hour_boundary_starts_new_window() -> None:
    """FR-002 boundary: offset of exactly 4 hours is outside the < 4h window."""
    base = datetime.datetime(2023, 1, 1, 12, 0, 0)
    art1 = _create_article("AAPL Earnings Beat", base, url="http://example.com/early")
    art2 = _create_article("AAPL Earnings Beat", base + timedelta(hours=4), url="http://example.com/exact4h")

    result = deduplicate_articles([art1, art2])
    assert len(result) == 2


def test_articles_just_inside_four_hour_window_collapse() -> None:
    """FR-002: 3h59m apart with 3+ word overlap collapse to one kept article."""
    base = datetime.datetime(2023, 1, 1, 12, 0, 0)
    art1 = _create_article("AAPL Earnings Beat", base, source="Other", url="http://example.com/a")
    art2 = _create_article(
        "AAPL Earnings Beat",
        base + timedelta(hours=3, minutes=59),
        source="Reuters",
        url="http://example.com/b",
    )

    result = deduplicate_articles([art1, art2])
    assert len(result) == 1
    assert result[0].url == "http://example.com/b"


# ---------------------------------------------------------------------------
# Source priority & tie-breakers (FR-004, FR-005)
# ---------------------------------------------------------------------------


def test_source_reliability_priority() -> None:
    """FR-004: Reuters/Bloomberg > CNBC/MarketWatch > other."""
    base_time = datetime.datetime(2023, 1, 1, 12, 0, 0)

    art_other = _create_article("AAPL Earnings Beat", base_time, source="Unknown blog", url="http://example.com/other")
    art_cnbc = _create_article(
        "AAPL Earnings Beat",
        base_time + timedelta(minutes=1),
        source="CNBC",
        url="http://example.com/cnbc",
    )
    art_reuters = _create_article(
        "AAPL Earnings Beat",
        base_time + timedelta(minutes=2),
        source="Reuters",
        url="http://example.com/reuters",
    )

    result = deduplicate_articles([art_other, art_cnbc, art_reuters])

    assert len(result) == 1
    assert result[0].url == "http://example.com/reuters"


def test_bloomberg_same_tier_as_reuters() -> None:
    """FR-004: Bloomberg is tier-3; earliest timestamp wins among tier-3 sources."""
    base = datetime.datetime(2023, 1, 1, 12, 0, 0)
    art_bb = _create_article("AAPL Earnings Beat", base, source="Bloomberg", url="http://example.com/bb")
    art_re = _create_article(
        "AAPL Earnings Beat",
        base + timedelta(minutes=10),
        source="Reuters",
        url="http://example.com/re",
    )
    result = deduplicate_articles([art_bb, art_re])
    assert len(result) == 1
    assert result[0].url == "http://example.com/bb"


def test_marketwatch_same_tier_as_cnbc_earliest_wins() -> None:
    """FR-005: CNBC and MarketWatch share medium reliability; earliest timestamp kept."""
    base_time = datetime.datetime(2023, 1, 1, 12, 0, 0)

    art1 = _create_article("AAPL Earnings Beat", base_time, source="CNBC", url="http://example.com/1")
    art2 = _create_article(
        "AAPL Earnings Beat",
        base_time + timedelta(minutes=30),
        source="MarketWatch",
        url="http://example.com/2",
    )

    result = deduplicate_articles([art1, art2])

    assert len(result) == 1
    assert result[0].url == "http://example.com/1"


def test_earliest_timestamp_tie_breaker() -> None:
    """FR-005: identical source priority keeps earliest published_at."""
    base_time = datetime.datetime(2023, 1, 1, 12, 0, 0)

    art1 = _create_article("AAPL Earnings Beat", base_time, source="CNBC", url="http://example.com/1")
    art2 = _create_article(
        "AAPL Earnings Beat",
        base_time + timedelta(minutes=30),
        source="MarketWatch",
        url="http://example.com/2",
    )

    result = deduplicate_articles([art1, art2])
    assert len(result) == 1
    assert result[0].url == "http://example.com/1"


def test_alphanumeric_url_tie_breaker() -> None:
    """Edge: same priority and timestamp → deterministic URL sort keeps lower URL."""
    base_time = datetime.datetime(2023, 1, 1, 12, 0, 0)

    art1 = _create_article("AAPL Earnings Beat", base_time, source="CNBC", url="http://example.com/b")
    art2 = _create_article("AAPL Earnings Beat", base_time, source="CNBC", url="http://example.com/a")

    result = deduplicate_articles([art1, art2])

    assert len(result) == 1
    assert result[0].url == "http://example.com/a"


def test_source_priority_helper_levels() -> None:
    """Unit: source priority mapping is case-insensitive and tiered correctly."""
    assert _get_source_priority("Reuters") == 3
    assert _get_source_priority("BLOOMBERG") == 3
    assert _get_source_priority(" cnbc ") == 2
    assert _get_source_priority("MarketWatch") == 2
    assert _get_source_priority("Random Blog") == 1
    assert _get_source_priority("") == 1


# ---------------------------------------------------------------------------
# Multi-group / multi-window scenarios (SC-001)
# ---------------------------------------------------------------------------


def test_multiple_independent_duplicate_groups() -> None:
    """SC-001: each near-duplicate group collapses independently within a window."""
    base = datetime.datetime(2023, 1, 1, 12, 0, 0)
    articles = [
        _create_article("AAPL Earnings Beat", base, source="CNBC", url="http://example.com/e1"),
        _create_article("AAPL Earnings Beat", base + timedelta(minutes=1), source="Reuters", url="http://example.com/e2"),
        _create_article("TSLA Product Launch", base, source="MarketWatch", url="http://example.com/t1"),
        _create_article("TSLA Product Launch", base + timedelta(minutes=2), source="Other", url="http://example.com/t2"),
        _create_article("MSFT Cloud Expansion News", base, source="Blog", url="http://example.com/m1"),
    ]

    result = deduplicate_articles(articles)
    urls = {a.url for a in result}

    assert len(result) == 3
    assert "http://example.com/e2" in urls  # Reuters wins earnings group
    assert "http://example.com/t1" in urls  # MarketWatch wins product group
    assert "http://example.com/m1" in urls  # unique kept


def test_five_near_duplicates_collapse_to_one() -> None:
    """US1 independent test: 5 near-duplicate titles within 4h → only 1 kept."""
    base = datetime.datetime(2023, 1, 1, 12, 0, 0)
    articles = [
        _create_article("AAPL Earnings Beat", base + timedelta(minutes=i), source=src, url=f"http://example.com/{i}")
        for i, src in enumerate(["Blog", "CNBC", "MarketWatch", "Other", "Reuters"])
    ]
    result = deduplicate_articles(articles)
    assert len(result) == 1
    assert result[0].source == "Reuters"


def test_result_sorted_chronologically() -> None:
    """Output is sorted ascending by published_at."""
    base = datetime.datetime(2023, 1, 1, 12, 0, 0)
    art_late = _create_article("Late Unique Story Alpha Beta", base + timedelta(hours=5), url="http://example.com/late")
    art_early = _create_article("Early Unique Story Gamma Delta", base, url="http://example.com/early")

    result = deduplicate_articles([art_late, art_early])
    assert [a.url for a in result] == ["http://example.com/early", "http://example.com/late"]


def test_unrelated_titles_all_kept() -> None:
    """No collapse when titles share fewer than 3 non-stop words."""
    base = datetime.datetime(2023, 1, 1, 12, 0, 0)
    articles = [
        _create_article("Oil Prices Surge Globally", base, url="http://example.com/1"),
        _create_article("Bank Rate Decision Tomorrow", base + timedelta(minutes=1), url="http://example.com/2"),
        _create_article("Chip Shortage Eases Supply", base + timedelta(minutes=2), url="http://example.com/3"),
    ]
    result = deduplicate_articles(articles)
    assert len(result) == 3


def test_mixed_naive_and_aware_timestamps_do_not_raise() -> None:
    """Window math normalizes naive/aware datetimes instead of raising TypeError."""
    naive = datetime.datetime(2023, 1, 1, 12, 0, 0)
    aware = datetime.datetime(2023, 1, 1, 12, 30, 0, tzinfo=datetime.timezone.utc)
    art1 = _create_article("AAPL Earnings Beat", naive, source="CNBC", url="http://example.com/n")
    art2 = _create_article("AAPL Earnings Beat", aware, source="Reuters", url="http://example.com/a")

    result = deduplicate_articles([art1, art2])
    assert len(result) == 1
    assert result[0].url == "http://example.com/a"
