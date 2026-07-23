"""Unit tests for the pure taxonomy classifier (FR-002, FR-003, FR-008).

Spec: specs/013-situation-taxonomy-backfill/spec.md
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.schemas.analysis import ArticleItem
from backend.app.services.taxonomy_classifier import determine_situation_tags


class MockMarketRegime:
    def __init__(self, market_state):
        self.market_state = market_state


def _article(title: str = "", description: str = "") -> ArticleItem:
    return ArticleItem(
        title=title,
        description=description,
        source="news",
        url="http://test",
        published_at=datetime.now(timezone.utc),
        sentiment_score=0.0,
    )


# ---------------------------------------------------------------------------
# FR-008 / Edge: missing or incomplete critical inputs → UNKNOWN
# ---------------------------------------------------------------------------

def test_unknown_when_missing_critical_fields():
    assert determine_situation_tags(None, "BUY", 0.7, [], None) == ["UNKNOWN"]
    assert determine_situation_tags("RELIANCE-EQ", None, 0.7, [], None) == ["UNKNOWN"]


def test_unknown_when_empty_string_symbol_or_recommendation():
    assert determine_situation_tags("", "BUY", 0.7, [], None) == ["UNKNOWN"]
    assert determine_situation_tags("RELIANCE-EQ", "", 0.7, [], None) == ["UNKNOWN"]


def test_unknown_when_both_critical_fields_missing():
    assert determine_situation_tags(None, None, None, None, None) == ["UNKNOWN"]


# ---------------------------------------------------------------------------
# FR-002: GOOD_NEWS_CATALYST
# ---------------------------------------------------------------------------

def test_good_news_catalyst():
    assert determine_situation_tags("RELIANCE-EQ", "BUY", 0.7, [], None) == ["GOOD_NEWS_CATALYST"]
    assert "GOOD_NEWS_CATALYST" not in determine_situation_tags("RELIANCE-EQ", "WATCH", 0.7, [], None)


def test_good_news_requires_buy_and_sentiment_strictly_above_0_6():
    # Boundary: sentiment == 0.6 must NOT trigger GOOD_NEWS_CATALYST
    assert "GOOD_NEWS_CATALYST" not in determine_situation_tags(
        "RELIANCE-EQ", "BUY", 0.6, [], None
    )
    # Just above threshold
    assert "GOOD_NEWS_CATALYST" in determine_situation_tags(
        "RELIANCE-EQ", "BUY", 0.6001, [], None
    )


def test_good_news_case_insensitive_recommendation():
    assert "GOOD_NEWS_CATALYST" in determine_situation_tags(
        "RELIANCE-EQ", "buy", 0.8, [], None
    )
    assert "GOOD_NEWS_CATALYST" in determine_situation_tags(
        "RELIANCE-EQ", "Buy", 0.8, [], None
    )


def test_good_news_not_applied_when_sentiment_is_none():
    tags = determine_situation_tags("RELIANCE-EQ", "BUY", None, [], None)
    assert "GOOD_NEWS_CATALYST" not in tags
    # FR-008: BUY with no matching rules → UNKNOWN (RANGE_BOUND is non-BUY only)
    assert tags == ["UNKNOWN"]


# ---------------------------------------------------------------------------
# FR-002: BAD_NEWS_CATALYST
# ---------------------------------------------------------------------------

def test_bad_news_catalyst():
    assert determine_situation_tags("RELIANCE-EQ", "WATCH", 0.3, [], None) == ["BAD_NEWS_CATALYST"]
    assert determine_situation_tags("RELIANCE-EQ", "SELL", 0.3, [], None) == ["BAD_NEWS_CATALYST"]
    assert "BAD_NEWS_CATALYST" not in determine_situation_tags("RELIANCE-EQ", "BUY", 0.3, [], None)


def test_bad_news_requires_sentiment_strictly_below_0_4():
    # Boundary: sentiment == 0.4 must NOT trigger BAD_NEWS_CATALYST → RANGE_BOUND for non-BUY
    assert "BAD_NEWS_CATALYST" not in determine_situation_tags(
        "RELIANCE-EQ", "SELL", 0.4, [], None
    )
    assert determine_situation_tags("RELIANCE-EQ", "SELL", 0.4, [], None) == ["RANGE_BOUND"]
    assert "BAD_NEWS_CATALYST" in determine_situation_tags(
        "RELIANCE-EQ", "SELL", 0.3999, [], None
    )


def test_bad_news_not_applied_when_sentiment_is_none():
    tags = determine_situation_tags("RELIANCE-EQ", "SELL", None, [], None)
    assert "BAD_NEWS_CATALYST" not in tags
    # Non-BUY without catalyst → RANGE_BOUND (research Decision 4)
    assert tags == ["RANGE_BOUND"]


# ---------------------------------------------------------------------------
# FR-002: EARNINGS_PLAY
# ---------------------------------------------------------------------------

def test_earnings_play():
    articles = [_article("Reliance Q1 Earnings beat expectations", "reliance profit is high")]
    tags = determine_situation_tags("RELIANCE-EQ", "BUY", 0.5, articles, None)
    assert "EARNINGS_PLAY" in tags


@pytest.mark.parametrize(
    "keyword",
    [
        "earnings",
        "q1",
        "q2",
        "q3",
        "q4",
        "quarter",
        "dividend",
        "results",
        "profit",
        "revenue",
    ],
)
def test_earnings_play_each_keyword_in_title(keyword: str):
    articles = [_article(f"Company reports {keyword} update", "neutral text")]
    tags = determine_situation_tags("RELIANCE-EQ", "BUY", 0.5, articles, None)
    assert "EARNINGS_PLAY" in tags


def test_earnings_play_keyword_in_description_only():
    articles = [_article("Market update", "strong quarterly revenue growth")]
    tags = determine_situation_tags("RELIANCE-EQ", "BUY", 0.5, articles, None)
    assert "EARNINGS_PLAY" in tags


def test_earnings_play_from_dict_articles():
    articles = [{"title": "Q2 results released", "description": "profit beat"}]
    tags = determine_situation_tags("RELIANCE-EQ", "BUY", 0.5, articles, None)
    assert "EARNINGS_PLAY" in tags


def test_no_earnings_play_without_keywords():
    articles = [_article("Stock gains on global cues", "broad market rally")]
    tags = determine_situation_tags("RELIANCE-EQ", "BUY", 0.5, articles, None)
    assert "EARNINGS_PLAY" not in tags


def test_articles_with_null_title_and_description_do_not_crash():
    class SparseArticle:
        title = None
        description = None

    tags = determine_situation_tags("RELIANCE-EQ", "BUY", 0.5, [SparseArticle()], None)
    assert "EARNINGS_PLAY" not in tags
    assert tags == ["UNKNOWN"]


def test_empty_articles_and_none_articles_are_safe():
    assert determine_situation_tags("RELIANCE-EQ", "BUY", 0.5, [], None) == ["UNKNOWN"]
    assert determine_situation_tags("RELIANCE-EQ", "BUY", 0.5, None, None) == ["UNKNOWN"]


# ---------------------------------------------------------------------------
# FR-002: MARKET_REGIME
# ---------------------------------------------------------------------------

def test_market_regime():
    regime = MockMarketRegime("BULLISH")
    tags = determine_situation_tags("RELIANCE-EQ", "BUY", 0.5, [], regime)
    assert "MARKET_REGIME" in tags


@pytest.mark.parametrize("state", ["BULLISH", "BEARISH", "RESTRICTIVE", "bullish", "Bearish"])
def test_market_regime_accepted_states(state: str):
    tags = determine_situation_tags(
        "RELIANCE-EQ", "BUY", 0.5, [], MockMarketRegime(state)
    )
    assert "MARKET_REGIME" in tags


def test_market_regime_from_dict():
    tags = determine_situation_tags(
        "RELIANCE-EQ", "BUY", 0.5, [], {"market_state": "BEARISH"}
    )
    assert "MARKET_REGIME" in tags


def test_market_regime_ignored_for_neutral_or_unknown_state():
    tags = determine_situation_tags(
        "RELIANCE-EQ", "BUY", 0.5, [], MockMarketRegime("NEUTRAL")
    )
    assert "MARKET_REGIME" not in tags
    assert tags == ["UNKNOWN"]


def test_market_regime_ignored_when_state_missing():
    tags = determine_situation_tags("RELIANCE-EQ", "BUY", 0.5, [], {"other": "x"})
    assert "MARKET_REGIME" not in tags


# ---------------------------------------------------------------------------
# FR-002 / FR-008: RANGE_BOUND (non-BUY, no catalyst) vs UNKNOWN (no rules)
# ---------------------------------------------------------------------------

def test_range_bound_for_non_buy_without_catalyst():
    assert determine_situation_tags("RELIANCE-EQ", "SELL", 0.5, [], None) == ["RANGE_BOUND"]
    assert determine_situation_tags("RELIANCE-EQ", "WATCH", 0.55, [], None) == ["RANGE_BOUND"]


def test_unknown_when_buy_matches_no_rules():
    """FR-008: BUY with mid sentiment and no earnings/regime → UNKNOWN."""
    assert determine_situation_tags("RELIANCE-EQ", "BUY", 0.5, [], None) == ["UNKNOWN"]


# ---------------------------------------------------------------------------
# Edge: multi-tag overlap (spec edge case)
# ---------------------------------------------------------------------------

def test_overlapping_tags():
    articles = [_article("Reliance dividend announced", "reliance q2 results")]
    regime = MockMarketRegime("BEARISH")
    tags = determine_situation_tags("RELIANCE-EQ", "BUY", 0.8, articles, regime)
    assert set(tags) == {"GOOD_NEWS_CATALYST", "EARNINGS_PLAY", "MARKET_REGIME"}


def test_overlapping_bad_news_and_earnings():
    articles = [_article("Weak revenue guidance", "earnings miss")]
    tags = determine_situation_tags("RELIANCE-EQ", "SELL", 0.2, articles, None)
    assert set(tags) == {"BAD_NEWS_CATALYST", "EARNINGS_PLAY"}


# ---------------------------------------------------------------------------
# FR-003: Determinism — identical inputs produce identical tags
# ---------------------------------------------------------------------------

def test_classifier_is_deterministic():
    articles = [_article("Q1 earnings", "profit beat")]
    regime = MockMarketRegime("BULLISH")
    kwargs = dict(
        symbol="RELIANCE-EQ",
        recommendation="BUY",
        sentiment_score=0.75,
        articles=articles,
        market_regime=regime,
    )
    first = determine_situation_tags(**kwargs)
    second = determine_situation_tags(**kwargs)
    assert first == second
    # Re-run with freshly constructed equivalent inputs
    third = determine_situation_tags(
        "RELIANCE-EQ",
        "BUY",
        0.75,
        [_article("Q1 earnings", "profit beat")],
        MockMarketRegime("BULLISH"),
    )
    assert third == first


def test_range_bound_not_applied_when_catalyst_present():
    """RANGE_BOUND is not added when BAD_NEWS (catalyst) already matched."""
    tags = determine_situation_tags("RELIANCE-EQ", "SELL", 0.2, [], None)
    assert tags == ["BAD_NEWS_CATALYST"]
    assert "RANGE_BOUND" not in tags


def test_range_bound_can_combine_with_market_regime():
    """Non-BUY without catalyst may still carry MARKET_REGIME + RANGE_BOUND."""
    tags = determine_situation_tags(
        "RELIANCE-EQ", "SELL", 0.5, [], MockMarketRegime("BEARISH")
    )
    assert set(tags) == {"RANGE_BOUND", "MARKET_REGIME"}


def test_range_bound_never_combined_with_good_news():
    tags = determine_situation_tags(
        "RELIANCE-EQ", "BUY", 0.9, [], MockMarketRegime("BULLISH")
    )
    assert "RANGE_BOUND" not in tags
    assert "GOOD_NEWS_CATALYST" in tags
    assert "MARKET_REGIME" in tags


def test_unknown_is_exclusive_when_returned():
    """UNKNOWN is the sole tag when critical fields are missing."""
    assert determine_situation_tags(None, "BUY", 0.9, [], MockMarketRegime("BULLISH")) == [
        "UNKNOWN"
    ]
