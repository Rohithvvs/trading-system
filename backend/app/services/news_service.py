from __future__ import annotations

from ..config import settings
from ..schemas import ArticleItem
import requests
from datetime import datetime


class NewsService:
    def fetch_recent_news(self, symbol: str) -> list[ArticleItem]:
        results: list[ArticleItem] = []
        # If a configured news API key / provider exists, call it (best-effort)
        if getattr(settings, "news_api_key", None) and getattr(settings, "news_api_url", None):
            try:
                resp = requests.get(f"{settings.news_api_url.rstrip('/')}/search", params={"q": f"{symbol} NSE news", "api_key": settings.news_api_key}, timeout=6)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("articles", [])[:10]:
                        results.append(ArticleItem(
                            title=item.get("title", ""),
                            description=item.get("description", ""),
                            source=item.get("source", {}).get("name", "unknown"),
                            url=item.get("url", ""),
                            published_at=datetime.fromisoformat(item.get("published_at")) if item.get("published_at") else datetime.utcnow(),
                            sentiment_score=0.0,
                        ))
                    return results
            except Exception:
                # best-effort; fall back to web search
                pass

        # Fallback: quick DuckDuckGo instant answer JSON for a best-effort list
        try:
            ddg = requests.get("https://api.duckduckgo.com/", params={"q": f"{symbol} NSE news", "format": "json", "no_html": 1, "skip_disambig": 1}, timeout=6)
            if ddg.status_code == 200:
                j = ddg.json()
                topics = j.get("RelatedTopics", [])
                for t in topics[:10]:
                    if isinstance(t, dict) and t.get("Text") and t.get("FirstURL"):
                        results.append(ArticleItem(
                            title=t.get("Text"),
                            description=t.get("Text"),
                            source="websearch",
                            url=t.get("FirstURL"),
                            published_at=datetime.utcnow(),
                            sentiment_score=0.0,
                        ))
                return results
        except Exception:
            pass

        return []
