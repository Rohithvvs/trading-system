from __future__ import annotations

import logging

from ..schemas import ArticleItem
from ..services.news_service import NewsService
from ..services.sentiment_service import SentimentService

logger = logging.getLogger("app.agents.news_analysis")


class NewsAnalysisAgent:
    def __init__(self) -> None:
        self.news_service = NewsService()
        self.sentiment_service = SentimentService()

    def _resolve_news_dedup_state(self) -> str:
        """Return news_dedup lifecycle state; fail-safe to disabled on any error.

        Spec assumption: any error querying rule state falls back to baseline
        (undeduplicated articles) so live recommendations never crash.
        """
        try:
            from ..governance.rule_manager import RuleManager

            return RuleManager().get_rule_state("news_dedup")
        except Exception as e:
            logger.error(
                "CRITICAL: Failed to resolve news_dedup rule state (%s). "
                "Fail-safe baseline path (disabled).",
                e,
            )
            return "disabled"

    def _apply_production_dedup(
        self, symbol: str, articles: list[ArticleItem]
    ) -> list[ArticleItem]:
        """Deduplicate in-line for production; fall back to originals on failure."""
        try:
            from ..services.news_deduplication import deduplicate_articles

            return deduplicate_articles(articles)
        except Exception as e:
            logger.error(
                "CRITICAL: Production news_dedup failed for %s (%s). "
                "Falling back to undeduplicated articles.",
                symbol,
                e,
            )
            return articles

    def _submit_shadow_dedup(self, symbol: str, articles: list[ArticleItem]) -> None:
        """Best-effort shadow execution; never impacts the production path."""
        try:
            from ..config import settings

            if not settings.is_shadow_hook_enabled():
                return
            from ..services.shadow_executor import ShadowThreadPool, execute_shadow_news_dedup

            ShadowThreadPool.submit_task(execute_shadow_news_dedup, symbol, articles)
        except Exception as e:
            logger.warning(
                "Shadow news_dedup submit failed for %s (production path unaffected): %s",
                symbol,
                e,
            )

    def run(self, symbol: str) -> tuple[list[ArticleItem], float, str, str]:
        articles = self.news_service.fetch_recent_news(symbol)
        if not articles:
            return [], 0.5, "Neutral", "No recent news found for this symbol."

        # FEAT-012/FEAT-013: Conditional execution based on news_dedup rule state
        rule_state = self._resolve_news_dedup_state()

        if rule_state == "production":
            # In production, deduplicate in-line and bypass shadow thread pool
            input_articles = self._apply_production_dedup(symbol, articles)
        else:
            input_articles = articles
            # Run shadow runner in background only if state is 'shadow'
            if rule_state == "shadow":
                self._submit_shadow_dedup(symbol, articles)

        score, label, summary = self.sentiment_service.summarize(symbol, input_articles)
        return input_articles, score, label, summary
