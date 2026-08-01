from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.schemas.analysis import ArticleItem

# 24 common English stop words
STOP_WORDS = {
    "the", "a", "and", "of", "in", "on", "for", "with", "to", "is", "at",
    "by", "from", "an", "as", "it", "that", "this", "or", "are", "be",
    "was", "were", "but",
}


def _clean_title(title: str) -> set[str]:
    """Lowercase, strip punctuation, split into words, and filter out stop words."""
    cleaned = re.sub(r"[^\w\s]", " ", title.lower())
    words = cleaned.split()
    return {w for w in words if w not in STOP_WORDS}


def _get_source_priority(source: str) -> int:
    """Return priority level: 3 (Reuters/Bloomberg) > 2 (CNBC/MarketWatch) > 1 (other)."""
    src_clean = source.strip().lower()
    if src_clean in ("reuters", "bloomberg"):
        return 3
    if src_clean in ("cnbc", "marketwatch"):
        return 2
    return 1


# Missing publication times sort as oldest so incomplete rows are not preferred.
_MISSING_TS = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _as_utc(value: datetime | None) -> datetime:
    """Normalize timestamps for window math; never raise on None/naive values.

    ``None`` is treated as epoch (oldest) so production dedup remains safe after
    ``ArticleItem.published_at`` became optional (014 residual M1).
    """
    if value is None:
        return _MISSING_TS
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def deduplicate_articles(articles: list[ArticleItem]) -> list[ArticleItem]:
    """Pure deduplication engine (FEAT-014).

    1. Cap input at 50 most recent.
    2. Group into 4h windows.
    3. Collapse near-duplicates within each window.
    """
    if not articles:
        return []
    if len(articles) == 1:
        return list(articles)

    # 1. Cap at 50 most recent (sort by timestamp descending, take 50, then sort ascending)
    sorted_by_recency = sorted(articles, key=lambda x: _as_utc(x.published_at), reverse=True)
    capped_articles = sorted_by_recency[:50]

    # Sort chronologically (ascending) for windowing
    chronological_articles = sorted(capped_articles, key=lambda x: _as_utc(x.published_at))

    # 2. Group into 4h windows starting from the earliest article's timestamp
    windows: list[list[ArticleItem]] = []
    current_window: list[ArticleItem] = []

    for art in chronological_articles:
        if not current_window:
            current_window.append(art)
            continue

        window_start = _as_utc(current_window[0].published_at)
        if _as_utc(art.published_at) - window_start < timedelta(hours=4):
            current_window.append(art)
        else:
            windows.append(current_window)
            current_window = [art]

    if current_window:
        windows.append(current_window)

    # 3. Process each window
    kept_articles: list[ArticleItem] = []

    for window in windows:
        # Cache cleaned titles once per article in this window
        cleaned: dict[int, set[str]] = {
            id(art): _clean_title(art.title) for art in window
        }
        groups: list[list[ArticleItem]] = []

        for art in window:
            art_words = cleaned[id(art)]
            matched_group = None

            for group in groups:
                if any(
                    len(art_words.intersection(cleaned[id(member)])) >= 3
                    for member in group
                ):
                    matched_group = group
                    break

            if matched_group is not None:
                matched_group.append(art)
            else:
                groups.append([art])

        for group in groups:
            if len(group) == 1:
                kept_articles.append(group[0])
                continue

            # Tie breaker: highest source priority -> earliest timestamp -> URL/title
            def resolve_key(item: ArticleItem) -> tuple[int, datetime, str]:
                priority = _get_source_priority(item.source)
                return (-priority, _as_utc(item.published_at), item.url or item.title)

            best_article = min(group, key=resolve_key)
            kept_articles.append(best_article)

    return sorted(kept_articles, key=lambda x: _as_utc(x.published_at))
