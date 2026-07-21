from typing import Any

# Catalyst tags (news/signal driven). RANGE_BOUND applies only when not BUY and none of these match.
_CATALYST_TAGS = frozenset({"GOOD_NEWS_CATALYST", "BAD_NEWS_CATALYST", "EARNINGS_PLAY"})


def determine_situation_tags(
    symbol: str | None,
    recommendation: str | None,
    sentiment_score: float | None,
    articles: list[Any] | None,
    market_regime: Any | None
) -> list[str]:
    """Pure function to classify trade recommendations into situation taxonomy tags.

    Heuristics (spec FR-002 / FR-008 + research Decision 4):
    - GOOD_NEWS_CATALYST: recommendation is BUY and sentiment_score > 0.6.
    - BAD_NEWS_CATALYST: recommendation is not BUY and sentiment_score < 0.4.
    - EARNINGS_PLAY: news articles contain earnings keywords.
    - MARKET_REGIME: broad market state is bullish, bearish, or restrictive.
    - RANGE_BOUND: recommendation is not BUY and no catalyst tags matched (research).
    - UNKNOWN: critical fields missing, or no situational rule matched (FR-008).
    """
    # FR-008 / missing critical inputs
    if not symbol or not recommendation:
        return ["UNKNOWN"]

    tags: list[str] = []
    rec = recommendation.upper()

    # 1. GOOD_NEWS_CATALYST
    if rec == "BUY" and sentiment_score is not None and sentiment_score > 0.6:
        tags.append("GOOD_NEWS_CATALYST")

    # 2. BAD_NEWS_CATALYST
    if rec != "BUY" and sentiment_score is not None and sentiment_score < 0.4:
        tags.append("BAD_NEWS_CATALYST")

    # 3. EARNINGS_PLAY
    earnings_keywords = [
        "earnings", "q1", "q2", "q3", "q4", "quarter", "dividend",
        "results", "profit", "revenue",
    ]
    has_earnings = False
    if articles:
        for article in articles:
            title = ""
            desc = ""
            if hasattr(article, "title"):
                title = getattr(article, "title") or ""
            elif isinstance(article, dict):
                title = article.get("title") or ""

            if hasattr(article, "description"):
                desc = getattr(article, "description") or ""
            elif isinstance(article, dict):
                desc = article.get("description") or ""

            text = f"{title} {desc}".lower()
            if any(kw in text for kw in earnings_keywords):
                has_earnings = True
                break

    if has_earnings:
        tags.append("EARNINGS_PLAY")

    # 4. MARKET_REGIME
    if market_regime:
        market_state = None
        if hasattr(market_regime, "market_state"):
            market_state = getattr(market_regime, "market_state")
        elif isinstance(market_regime, dict):
            market_state = market_regime.get("market_state")

        if market_state and str(market_state).upper() in ["BULLISH", "BEARISH", "RESTRICTIVE"]:
            tags.append("MARKET_REGIME")

    # 5. RANGE_BOUND — explicit rule (research): non-BUY without catalyst tags
    has_catalyst = bool(_CATALYST_TAGS.intersection(tags))
    if rec != "BUY" and not has_catalyst:
        tags.append("RANGE_BOUND")

    # 6. FR-008: no situational rule matched → UNKNOWN
    if not tags:
        tags.append("UNKNOWN")

    return tags
