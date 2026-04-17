from __future__ import annotations

from ..config import settings
from ..schemas import ArticleItem
from ..utils.mock_data import generate_mock_articles


class NewsService:
    def fetch_recent_news(self, symbol: str) -> list[ArticleItem]:
        if settings.news_api_key:
            # Marketaux integration is added in a later phase.
            pass

        return [ArticleItem(**item) for item in generate_mock_articles(symbol)]
