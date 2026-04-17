from __future__ import annotations

from statistics import mean

from ..schemas import (
    AnalysisMode,
    BacktestResult,
    FinalRecommendation,
    OHLCVPoint,
    RecommendationReasoning,
    TechnicalAnalysisResult,
    TradePlan,
)


class RecommendationService:
    def build(
        self,
        symbol: str,
        technical_results: list[TechnicalAnalysisResult],
        sentiment_score: float,
        backtests: list[BacktestResult],
        candles_by_mode: dict[AnalysisMode, list[OHLCVPoint]],
        llm_reasoning: dict[str, object],
    ) -> FinalRecommendation:
        technical_score = max(result.score for result in technical_results)
        backtest_return = max(item.total_return for item in backtests)
        sentiment_component = (sentiment_score + 1) * 20
        backtest_component = min(backtest_return * 2, 25)
        score = round((technical_score * 0.5) + sentiment_component + backtest_component, 2)
        confidence = round(min(0.95, max(0.35, score / 120)), 2)

        if score >= 78:
            action = "BUY"
        elif score >= 58:
            action = "WATCH"
        else:
            action = "REJECT"

        reasoning = RecommendationReasoning(
            bullets=list(llm_reasoning.get("bullets", [])),
            risk_factors=list(llm_reasoning.get("risk_factors", [])),
            invalidation_signals=list(llm_reasoning.get("invalidation_signals", [])),
        )
        trade_plans = self._build_trade_plans(technical_results, backtests, candles_by_mode)
        summary = str(
            llm_reasoning.get(
                "summary",
                f"{symbol} is rated {action} in the advisory engine with confidence {confidence}.",
            )
        )
        return FinalRecommendation(
            action=action,
            confidence=confidence,
            score=score,
            reasoning=reasoning,
            trade_plans=trade_plans,
            summary=summary,
        )

    def _build_trade_plans(
        self,
        technical_results: list[TechnicalAnalysisResult],
        backtests: list[BacktestResult],
        candles_by_mode: dict[AnalysisMode, list[OHLCVPoint]],
    ) -> list[TradePlan]:
        plans: list[TradePlan] = []
        backtests_by_mode = {item.mode: item for item in backtests}

        for technical in technical_results:
            candles = candles_by_mode.get(technical.mode, [])
            if len(candles) < 5:
                continue
            current_price = candles[-1].close
            recent_ranges = [candle.high - candle.low for candle in candles[-10:]]
            avg_range = mean(recent_ranges) if recent_ranges else current_price * 0.01
            direction = 1 if technical.signal == "bullish" else -1 if technical.signal == "bearish" else 0
            setup_type = self._setup_type(technical.mode, technical.signal)
            timeframe = "intraday execution" if technical.mode == AnalysisMode.intraday else "multi-session swing"

            if direction >= 0:
                entry_low = round(current_price - avg_range * 0.25, 2)
                entry_high = round(current_price + avg_range * 0.15, 2)
                stop_loss = round(entry_low - avg_range * 0.9, 2)
                target_1 = round(entry_high + avg_range * 1.2, 2)
                target_2 = round(entry_high + avg_range * 2.1, 2)
                target_3 = round(entry_high + avg_range * 3.0, 2)
                bias = "long"
            else:
                entry_low = round(current_price - avg_range * 0.15, 2)
                entry_high = round(current_price + avg_range * 0.25, 2)
                stop_loss = round(entry_high + avg_range * 0.9, 2)
                target_1 = round(entry_low - avg_range * 1.2, 2)
                target_2 = round(entry_low - avg_range * 2.1, 2)
                target_3 = round(entry_low - avg_range * 3.0, 2)
                bias = "short"

            if direction == 0:
                bias = "wait"
                stop_loss = round(current_price - avg_range if technical.mode == AnalysisMode.swing else current_price - (avg_range * 0.7), 2)

            risk = abs(((entry_low + entry_high) / 2) - stop_loss)
            reward = abs(target_1 - ((entry_low + entry_high) / 2))
            risk_reward_ratio = round(reward / risk, 2) if risk else 0.0
            backtest = backtests_by_mode.get(technical.mode)
            notes = (
                f"Use the {setup_type} setup with {technical.signal} bias. "
                f"Backtest verdict: {backtest.verdict if backtest else 'n/a'}."
            )

            plans.append(
                TradePlan(
                    mode=technical.mode,
                    strategy_name=backtest.strategy_name if backtest else setup_type,
                    setup_type=setup_type,
                    timeframe=timeframe,
                    bias=bias,
                    entry_low=entry_low,
                    entry_high=entry_high,
                    stop_loss=stop_loss,
                    target_1=target_1,
                    target_2=target_2,
                    target_3=target_3,
                    risk_reward_ratio=risk_reward_ratio,
                    notes=notes,
                )
            )

        return plans

    def _setup_type(self, mode: AnalysisMode, signal: str) -> str:
        if mode == AnalysisMode.intraday:
            return "VWAP continuation" if signal == "bullish" else "VWAP rejection"
        return "Trend pullback" if signal == "bullish" else "Breakdown retest"
