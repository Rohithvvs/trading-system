from __future__ import annotations

from ..schemas import ArticleItem
from .llm_service import LLMService
from ..utils import get_logger


class SentimentService:
    def __init__(self) -> None:
        self.llm_service = LLMService()
        self.logger = get_logger("app.sentiment")

    def summarize(self, symbol: str, articles: list[ArticleItem]) -> tuple[float, str, str]:
        if not articles:
            return 0.0, "neutral", f"No recent news found for {symbol}."

        headlines = [a.title for a in articles if a.title]
        try:
            score = self.llm_service.analyze_sentiment(symbol, headlines)
        except Exception as e:
            self.logger.error("LLM sentiment analysis failed for %s: %s", symbol, e)
            score = 0.0

        score = round(score, 2)

        if score >= 0.2:
            label = "positive"
        elif score <= -0.2:
            label = "negative"
        else:
            label = "neutral"

        summary = f"{symbol} news flow is {label} in the phase 1 engine based on recent article headlines."
        return score, label, summary
