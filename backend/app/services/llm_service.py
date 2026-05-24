from __future__ import annotations

import json

import requests

from ..config import settings


class LLMService:
    def build_reasoning(self, symbol: str, prompt_context: dict[str, object]) -> dict[str, object]:
        if settings.llm_provider.lower() == "groq" and settings.llm_api_key:
            reasoning = self._build_with_groq(symbol, prompt_context)
            if reasoning:
                return reasoning
        return self._fallback_reasoning(symbol, prompt_context)

    def _build_with_groq(self, symbol: str, prompt_context: dict[str, object]) -> dict[str, object] | None:
        system_prompt = (
            "You are a trading analysis assistant. Respond with valid JSON only. "
            "Keep output advisory-only and never mention automated execution. "
            "Return keys: bullets, risk_factors, invalidation_signals, summary."
        )
        user_prompt = (
            f"Symbol: {symbol}\n"
            f"Context: {json.dumps(prompt_context, default=str)}\n"
            "Write 3 concise reasoning bullets, 2 risk factors, 2 invalidation signals, and a 1-2 sentence summary."
        )
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if all(key in parsed for key in ("bullets", "risk_factors", "invalidation_signals", "summary")):
                return parsed
        except Exception:
            return None
        return None

    def _fallback_reasoning(self, symbol: str, prompt_context: dict[str, object]) -> dict[str, object]:
        technical_signal = prompt_context.get("technical_signal", "neutral")
        news_label = prompt_context.get("news_label", "neutral")
        backtest_verdict = prompt_context.get("backtest_verdict", "mixed")
        current_price = prompt_context.get("current_price", "unknown")

        return {
            "bullets": [
                f"{symbol} technical posture is currently {technical_signal}.",
                f"News sentiment is {news_label} based on the latest fetched article set.",
                f"Backtest verdict is {backtest_verdict} while price is around {current_price}.",
            ],
            "risk_factors": [
                "Market conditions can reverse quickly during active sessions.",
                "Provider delays or fallback data can change signal quality.",
            ],
            "invalidation_signals": [
                "Loss of support with weak follow-through volume.",
                "Fresh negative news flow conflicting with the active setup.",
            ],
            "summary": (
                f"{symbol} has a {technical_signal} posture with {news_label} news and a {backtest_verdict} "
                "historical setup in the current advisory engine."
            ),
        }

    def analyze_sentiment(self, symbol: str, headlines: list[str]) -> float:
        if not headlines:
            return 0.0
        if settings.llm_provider.lower() == "groq" and settings.llm_api_key:
            system_prompt = (
                "You are a quantitative sentiment analyzer. Respond with valid JSON only. "
                "Evaluate the following headlines for the given stock symbol and return a clean, minified JSON object containing a numeric 'sentiment_score' "
                "strictly bounded between -1.0 (highly catastrophic/bearish) and 1.0 (highly disruptive/bullish)."
            )
            user_prompt = (
                f"Symbol: {symbol}\n"
                f"Headlines: {json.dumps(headlines)}\n"
            )
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.llm_model,
                        "temperature": 0.0,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                    timeout=10,
                )
                response.raise_for_status()
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                score = float(parsed.get("sentiment_score", 0.0))
                return max(-1.0, min(1.0, score))
            except Exception as e:
                from ..utils import get_logger
                get_logger("app.llm_service").error("Sentiment LLM failed for %s: %s", symbol, e)
                return 0.0
        return 0.0
