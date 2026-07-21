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
        if not articles:
            return [], 0.5, "Neutral", "No recent news found for this symbol."
            
        # FEAT-014: Trigger shadow news deduplication background runner.
        # Gate with the shared shadow hook helper (master toggle AND stage != OFF).
        from ..config import settings
        if settings.is_shadow_hook_enabled():
            from ..services.shadow_executor import ShadowThreadPool, execute_shadow_news_dedup
            ShadowThreadPool.submit_task(execute_shadow_news_dedup, symbol, articles)

        score, label, summary = self.sentiment_service.summarize(symbol, articles)
        return articles, score, label, summary
