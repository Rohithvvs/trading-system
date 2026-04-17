from __future__ import annotations

from ..schemas import ArticleItem
from ..services.news_service import NewsService
from ..services.sentiment_service import SentimentService


class NewsAnalysisAgent:
    def __init__(self) -> None:
        self.news_service = NewsService()
        self.sentiment_service = SentimentService()

    def run(self, symbol: str) -> tuple[list[ArticleItem], float, str, str]:
        articles = self.news_service.fetch_recent_news(symbol)
        score, label, summary = self.sentiment_service.summarize(symbol, articles)
        return articles, score, label, summary
