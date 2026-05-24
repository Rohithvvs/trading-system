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
    FundamentalAnalysisResult,
)


class RecommendationService:
    def build(
        self,
        symbol: str,
        technical_results: list[TechnicalAnalysisResult],
        sentiment_score: float,
        fundamental_result: FundamentalAnalysisResult | None,
        backtests: list[BacktestResult],
        candles_by_mode: dict[AnalysisMode, list[OHLCVPoint]],
        llm_reasoning: dict[str, object],
    ) -> FinalRecommendation:
        technical_score = max((result.score for result in technical_results), default=0.0)
        best_backtest = max(backtests, key=lambda item: item.total_return) if backtests else None
        
        fundamental_score = fundamental_result.fundamental_score if fundamental_result else 0.0

        # Calculate volume catalyst trigger
        primary_technical = technical_results[0] if technical_results else None
        candles = candles_by_mode.get(primary_technical.mode, []) if primary_technical else []
        current_volume = candles[-1].volume if candles else 0
        avg_volume = mean([c.volume for c in candles[-20:]]) if len(candles) >= 20 else current_volume

        tech_wt, backtest_wt, news_wt, fund_wt = self.calculate_dynamic_weights(
            sentiment_score=sentiment_score,
            fundamental_score=fundamental_score,
            current_volume=current_volume,
            avg_volume=avg_volume
        )

        backtest_points = self._backtest_component(best_backtest) if best_backtest else 0.0
        
        # Max Possible:
        # Tech: 100 * tech_wt
        # Backtest: 100 * backtest_wt (Since backtest max component was 25 for 0.25 wt, we should scale it. Wait, previously max was 25 points out of 100. So we should treat raw component as out of 100 and multiply by weight.)
        
        # Actually, let's normalize raw scores to 100:
        raw_tech = technical_score # 0 to 100
        raw_backtest = min(max((best_backtest.total_return * 4) if best_backtest and best_backtest.trade_count >= 5 else 0.0, -20.0), 100.0) # -20 to 100
        raw_news = sentiment_score * 100 # -100 to 100
        raw_fund = fundamental_score * 100 # -100 to 100
        
        score = round(
            (raw_tech * tech_wt) + 
            (raw_backtest * backtest_wt) + 
            (raw_news * news_wt) + 
            (raw_fund * fund_wt), 2
        )
        score = max(0.0, min(100.0, score)) # Ensure bounds
        
        confidence = round(min(0.95, max(0.35, score / 100)), 2)
        trade_plans = self._build_trade_plans(technical_results, backtests, candles_by_mode)

        if score >= 72:
            action = "BUY"
        elif score >= 55:
            action = "WATCH"
        else:
            action = "REJECT"

        reasoning = RecommendationReasoning(
            bullets=list(llm_reasoning.get("bullets", [])),
            risk_factors=list(llm_reasoning.get("risk_factors", [])),
            invalidation_signals=list(llm_reasoning.get("invalidation_signals", [])),
        )
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

    def calculate_dynamic_weights(
        self,
        sentiment_score: float, 
        fundamental_score: float,
        current_volume: float,
        avg_volume: float
    ) -> tuple[float, float, float, float]:
        """
        Returns (tech_wt, backtest_wt, sentiment_wt, fundamental_wt) adding up to 1.0
        """
        # Standard Regime
        weights = {"tech": 0.50, "fundamental": 0.25, "backtest": 0.25, "news": 0.0}
        
        # Catalyst Conditions
        news_catalyst = abs(sentiment_score) >= 0.75
        volume_catalyst = avg_volume > 0 and current_volume > (avg_volume * 3.0)
        
        if news_catalyst or volume_catalyst:
            # Catalyst Regime
            weights["news"] = 0.30
            weights["fundamental"] = 0.30
            weights["tech"] = 0.20
            weights["backtest"] = 0.20
            
        return weights["tech"], weights["backtest"], weights["news"], weights["fundamental"]

    def _backtest_component(self, backtest: BacktestResult) -> float:
        if backtest.verdict == "insufficient" or backtest.trade_count < 5:
            return 0.0
        return round(min(max(backtest.total_return * 2, -5), 25), 2)

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
