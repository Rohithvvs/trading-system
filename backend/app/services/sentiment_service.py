from __future__ import annotations

from statistics import mean

from ..schemas import ArticleItem


class SentimentService:
    def summarize(self, symbol: str, articles: list[ArticleItem]) -> tuple[float, str, str]:
        score = round(mean(article.sentiment_score for article in articles), 2) if articles else 0.0

        if score >= 0.2:
            label = "positive"
        elif score <= -0.2:
            label = "negative"
        else:
            label = "neutral"

        summary = f"{symbol} news flow is {label} in the phase 1 engine based on recent article headlines."
        return score, label, summary
