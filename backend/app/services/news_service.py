from __future__ import annotations

from ..config import settings
from ..schemas import ArticleItem


class NewsService:
    def fetch_recent_news(self, symbol: str) -> list[ArticleItem]:
        if settings.news_api_key:
            # Marketaux integration is added in a later phase.
            pass

        return []
