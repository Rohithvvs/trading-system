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

    def build_research_summary(self, symbol: str, facts: dict) -> dict:
        """AI research summary grounded only in provided facts. Never invent numbers."""
        if settings.llm_provider.lower() == "groq" and settings.llm_api_key:
            result = self._research_summary_groq(symbol, facts)
            if result:
                return result
        return self._fallback_research_summary(symbol, facts)

    def build_ai_confidence_explanation(self, symbol: str, facts: dict, conf_label: str) -> dict:
        if settings.llm_provider.lower() == "groq" and settings.llm_api_key:
            result = self._ai_confidence_groq(symbol, facts, conf_label)
            if result:
                return result
        return self._fallback_ai_confidence(symbol, facts, conf_label)

    def build_research_insights(self, symbol: str, facts: dict) -> dict:
        if settings.llm_provider.lower() == "groq" and settings.llm_api_key:
            result = self._research_insights_groq(symbol, facts)
            if result:
                return result
        return self._fallback_research_insights(symbol, facts)

    def _research_summary_groq(self, symbol: str, facts: dict) -> dict | None:
        system_prompt = (
            "You are an institutional equity research assistant for swing traders. "
            "Respond with valid JSON only. Use ONLY the facts provided. "
            "Never invent or estimate numbers that are not in the facts. "
            "If a field is missing or says 'Data not available.', write exactly 'Data not available.' "
            "Do not recommend automated execution. Advisory only. "
            "Return keys: company_does, business_model, industry, sector, competitive_advantage, "
            "current_market_position, growth_opportunities, risks, short_term_outlook, "
            "medium_term_outlook, long_term_outlook, stance (Bullish|Neutral|Bearish), "
            "stance_confidence (High|Medium|Low), narrative."
        )
        user_prompt = (
            f"Symbol: {symbol}\n"
            f"Verified facts (JSON): {json.dumps(facts, default=str)}\n"
            "Write a professional research summary using only these facts."
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
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=25,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "narrative" in parsed:
                return parsed
        except Exception:
            return None
        return None

    def _ai_confidence_groq(self, symbol: str, facts: dict, conf_label: str) -> dict | None:
        system_prompt = (
            "You explain swing trade recommendations using only provided facts. "
            "JSON only. Never invent numbers. Keys: reasons (array of short strings), "
            "conclusion (string), confidence_label (High|Medium|Low)."
        )
        user_prompt = (
            f"Symbol: {symbol}\nComputed confidence: {conf_label}\n"
            f"Facts: {json.dumps(facts, default=str)}\n"
            "Explain why this recommendation was generated in bullet reasons."
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
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=20,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "reasons" in parsed:
                parsed["confidence_label"] = parsed.get("confidence_label") or conf_label
                return parsed
        except Exception:
            return None
        return None

    def _research_insights_groq(self, symbol: str, facts: dict) -> dict | None:
        system_prompt = (
            "You write professional swing-trading research notes from verified facts only. "
            "JSON keys: bullets (array), risks (array), bottom_line (string). "
            "Never invent numbers. Say 'Data not available.' for missing items."
        )
        user_prompt = f"Symbol: {symbol}\nFacts: {json.dumps(facts, default=str)}"
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=20,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
        return None

    def _fallback_research_summary(self, symbol: str, facts: dict) -> dict:
        desc = facts.get("company_description") or "Data not available."
        sector = facts.get("sector") or "Data not available."
        industry = facts.get("industry") or "Data not available."
        trend = facts.get("current_trend") or "Data not available."
        score = facts.get("swing_score")
        stance = "Neutral"
        if isinstance(score, (int, float)):
            if score >= 72:
                stance = "Bullish"
            elif score < 45:
                stance = "Bearish"
        conf = "High" if (facts.get("score_breakdown") or {}).get("ai_confidence", 0) >= 70 else (
            "Medium" if (facts.get("score_breakdown") or {}).get("ai_confidence", 0) >= 50 else "Low"
        )
        return {
            "company_does": desc if desc != "Data not available." else f"{symbol} business description is not available from current data feeds.",
            "business_model": "Data not available." if desc == "Data not available." else "Inferred only from available company description; detailed model not separately provided.",
            "industry": industry,
            "sector": sector,
            "competitive_advantage": "Data not available.",
            "current_market_position": f"Technical trend currently classified as {trend}.",
            "growth_opportunities": "Data not available." if facts.get("fundamental_score") in (None, "Data not available.") else "See fundamental score and growth fields when present.",
            "risks": [
                "Market structure can reverse quickly.",
                "Missing institutional or fundamental fields reduce confidence.",
            ],
            "short_term_outlook": f"Near-term bias follows {trend} with momentum {facts.get('momentum_direction')}.",
            "medium_term_outlook": f"Swing score is {score if score is not None else 'Data not available.'} / 100 based on computed components.",
            "long_term_outlook": "Data not available." if facts.get("fundamental_score") in (None, "Data not available.") else f"Fundamental score component: {facts.get('fundamental_score')}.",
            "stance": stance,
            "stance_confidence": conf,
            "narrative": (
                f"{symbol}: trend={trend}, momentum={facts.get('momentum_direction')}, "
                f"volume_breakout={facts.get('volume_breakout')}, swing_score={score}. "
                "All figures are from the research engine facts payload."
            ),
        }

    def _fallback_ai_confidence(self, symbol: str, facts: dict, conf_label: str) -> dict:
        reasons = []
        reasons.append(f"Trend is {facts.get('current_trend', 'unknown')}.")
        reasons.append(f"Momentum is {facts.get('momentum_direction', 'unknown')} ({facts.get('momentum_strength', 'n/a')}).")
        if facts.get("volume_breakout"):
            reasons.append("Volume breakout detected versus 20-day average.")
        else:
            reasons.append(f"Volume trend is {facts.get('volume_trend', 'unknown')}.")
        rsi = facts.get("rsi")
        if rsi not in (None, "Data not available."):
            reasons.append(f"RSI is {rsi}.")
        if facts.get("flow_label") == "accumulation":
            reasons.append("Volume/OBV flow labelled accumulation.")
        elif facts.get("flow_label") == "distribution":
            reasons.append("Volume/OBV flow labelled distribution.")
        rr = facts.get("risk_reward")
        if rr not in (None, "Data not available."):
            reasons.append(f"Risk/reward ratio is {rr}.")
        conclusion = (
            f"Computed AI confidence is {conf_label}. "
            "Probability of continuation depends on trend, momentum, and volume confluence above — not a guarantee."
        )
        return {"reasons": reasons, "conclusion": conclusion, "confidence_label": conf_label}

    def _fallback_research_insights(self, symbol: str, facts: dict) -> dict:
        return {
            "bullets": [
                f"{symbol} swing score: {facts.get('swing_score', 'Data not available.')}",
                f"Trend: {facts.get('current_trend', 'Data not available.')}; Momentum: {facts.get('momentum_direction', 'Data not available.')}",
                f"Suggested entry/stop/t1: {facts.get('entry')} / {facts.get('stop')} / {facts.get('target_1')}",
            ],
            "risks": [
                "Stop-loss breach invalidates the setup.",
                "News and missing institutional data can alter odds quickly.",
            ],
            "bottom_line": facts.get("recommendation_summary")
            or f"Advisory research for {symbol} based only on available market data.",
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
