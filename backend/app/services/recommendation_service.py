from __future__ import annotations

import logging
import math
from statistics import mean
from typing import Any

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
from .feat004_regime_overlay import apply_feat004_regime_overlay

logger = logging.getLogger("app.recommendation_service")

# Pure score-based signal thresholds (production classification).
# Final recommendation is decided ONLY after all analysis modules complete.
BUY_SCORE_THRESHOLD = 70.0
WATCH_SCORE_THRESHOLD = 55.0
ANALYSIS_FAILED_REASON = "Analysis Failed"


def classify_signal_from_score(score: float) -> str:
    """Classify BUY / WATCH / REJECT from composite score only.

    Rules (applied only after mandatory analysis preconditions pass):
      score >= 70 → BUY
      55 <= score < 70 → WATCH
      score < 55 → REJECT
    """
    if math.isnan(score) or math.isinf(score):
        return "REJECT"
    if score >= BUY_SCORE_THRESHOLD:
        return "BUY"
    if score >= WATCH_SCORE_THRESHOLD:
        return "WATCH"
    return "REJECT"


def is_trade_plan_complete(plan: Any) -> bool:
    """True when entry, stop-loss, and target are present and usable."""
    if plan is None:
        return False
    try:
        entry_low = float(getattr(plan, "entry_low", 0) or 0)
        entry_high = float(getattr(plan, "entry_high", 0) or 0)
        stop_loss = float(getattr(plan, "stop_loss", 0) or 0)
        target_1 = float(getattr(plan, "target_1", 0) or 0)
    except (TypeError, ValueError):
        return False
    if entry_low <= 0 or entry_high <= 0 or stop_loss <= 0 or target_1 <= 0:
        return False
    # Entry band must be ordered; stop/target must be finite numbers.
    if entry_high < entry_low:
        return False
    return True


def analysis_preconditions_ok(
    *,
    score: float,
    confidence: float | None,
    trade_plans: list[Any] | None,
    data_quality: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Mandatory preconditions before score-based signal assignment.

    Returns (ok, reason). reason is ANALYSIS_FAILED_REASON when not ok.

    Data is considered valid when:
      - not explicitly mock/empty, AND
      - minimum swing candles met (when data_quality supplied), AND
      - a complete trade plan (entry / SL / target) exists, AND
      - score + confidence are finite.

    Source labels such as "unknown" with a full candle series are accepted
    (prefetched shortlist path). Do not invent Score=100 on failure.
    """
    # Score calculated and finite
    try:
        score_f = float(score)
    except (TypeError, ValueError):
        return False, ANALYSIS_FAILED_REASON
    if math.isnan(score_f) or math.isinf(score_f):
        return False, ANALYSIS_FAILED_REASON

    # Confidence calculated and finite
    try:
        conf_f = float(confidence) if confidence is not None else float("nan")
    except (TypeError, ValueError):
        return False, ANALYSIS_FAILED_REASON
    if math.isnan(conf_f) or math.isinf(conf_f):
        return False, ANALYSIS_FAILED_REASON

    # Market / OHLC / price data valid when data_quality is provided
    if data_quality is not None:
        if bool(data_quality.get("mock_warning")):
            return False, ANALYSIS_FAILED_REASON
        if not bool(data_quality.get("minimum_swing_candles_met")):
            return False, ANALYSIS_FAILED_REASON
        # Accept production sources + prefetched/unknown series that already
        # cleared mock_warning and candle-count checks above.
        source = str(data_quality.get("source") or "")
        if source in {"MOCK_FALLBACK", "NO_DATA", "NONE"}:
            return False, ANALYSIS_FAILED_REASON

    # Trade plan with entry, stop loss, and target
    plans = trade_plans or []
    if not plans:
        return False, ANALYSIS_FAILED_REASON
    if not any(is_trade_plan_complete(p) for p in plans):
        return False, ANALYSIS_FAILED_REASON

    return True, ""


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
        # FEAT-004 optional kwargs; callers that do not supply them get safe defaults
        feat004_config: dict[str, Any] | None = None,
        benchmark_ohlcv: Any = None,
        benchmark_failure_reason: str | None = None,
        benchmark_symbol: str | None = None,
        sector_mapping: dict[str, str] | None = None,
        sector_ohlcv_cache: dict[str, Any] | None = None,
        # FEAT-007 optional kwargs; Batch 1 accepts and stores only — no logic
        feat007_config: dict[str, Any] | None = None,
        sector_rs_value: float | None = None,
        sector_index_symbol: str | None = None,
        sector_roc20: float | None = None,
        benchmark_roc20: float | None = None,
        feat007_abstained_reason: str | None = None,
        # Stage 2: optional soft contribution injected by orchestrator when rule is production
        market_breadth_soft_score: float | None = None,
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

        # Stage 2 Market Breadth gate (fail-open to baseline on any governance error)
        breadth_active = False
        try:
            from ..governance.rule_manager import RuleManager

            breadth_active = RuleManager().is_active_in_production("market_breadth")
        except Exception as e:
            logger.warning(
                "governance_fail_open | symbol=%s | rule=market_breadth | error=%s | action=baseline_scoring",
                symbol,
                e,
            )
            breadth_active = False

        raw_tech = technical_score  # 0 to 100
        raw_backtest = min(
            max(
                (best_backtest.total_return * 4)
                if best_backtest and best_backtest.trade_count >= 5
                else 0.0,
                -20.0,
            ),
            100.0,
        )
        if math.isnan(raw_backtest) or math.isinf(raw_backtest):
            raw_backtest = 0.0
        # sentiment_score is in [-1.0, 1.0] (0.0 = neutral) from SentimentService.
        # Map to 0–100 so neutral contributes 50 (not 0), matching fundamental mapping.
        # Prior bug: `sentiment_score * 100` treated neutral as 0 and crushed catalyst-regime scores.
        raw_news = max(0.0, min(100.0, (float(sentiment_score) + 1.0) / 2.0 * 100.0))
        # fundamental_score is in [-1.0, 1.0] range where 0.0 is neutral
        # Prior bug: `fundamental_score * 100` mapped neutral/missing 0.0 → 0 points with 25% weight
        # (~12.5pt composite drag), so strong technicals often never reached the BUY threshold of 68.
        raw_fund = max(0.0, min(100.0, (float(fundamental_score) + 1.0) / 2.0 * 100.0))

        if breadth_active:
            # Stage 2: rebalanced 100-point matrix + live soft contribution
            from .scoring_matrix_service import ScoringMatrixService

            matrix_config = ScoringMatrixService.get_matrix_config(market_breadth_promoted=True)
            soft = market_breadth_soft_score
            if soft is None or (isinstance(soft, float) and (math.isnan(soft) or math.isinf(soft))):
                soft = 0.0
                logger.warning(
                    "breadth_soft_missing | symbol=%s | action=soft_score_0",
                    symbol,
                )
            # Map soft contribution [-15, +15] → factor score [0, 100] centered at 50
            soft_f = max(-15.0, min(15.0, float(soft)))
            breadth_factor = max(0.0, min(100.0, 50.0 + (soft_f / 15.0) * 50.0))
            raw_vol = min(
                100.0,
                max(0.0, (current_volume / max(1.0, float(avg_volume))) * 50.0),
            )
            score = round(
                ScoringMatrixService.compute_composite_score(
                    technical_score=raw_tech,
                    sentiment_score=raw_news,
                    fundamental_score=raw_fund,
                    volume_score=raw_vol,
                    market_breadth_score=breadth_factor,
                    matrix_config=matrix_config,
                ),
                2,
            )
        else:
            # Baseline production path (pre-Stage-2) — preserve dynamic weights + backtest
            score = round(
                (raw_tech * tech_wt)
                + (raw_backtest * backtest_wt)
                + (raw_news * news_wt)
                + (raw_fund * fund_wt),
                2,
            )

        if math.isnan(score) or math.isinf(score):
            logger.error("composite_score_non_finite | symbol=%s | score=%s | fail_open=0", symbol, score)
            score = 0.0
        score = max(0.0, min(100.0, score))  # Ensure bounds
        
        confidence = round(min(0.95, max(0.35, score / 100)), 2)
        trade_plans = self._build_trade_plans(technical_results, backtests, candles_by_mode)

        # ------------------------------------------------------------------
        # Final recommendation is ONLY score-based, AFTER all analysis:
        # technical / sentiment / fundamental / backtest / trade plans /
        # AI reasoning have already run above.
        #
        # BUY  >= 70 | WATCH 55–69.99 | REJECT < 55
        # Overlays (FEAT-004 / FEAT-007) may still run for telemetry, but
        # MUST NOT change the production score or action.
        # ------------------------------------------------------------------
        raw_technical_score: float = technical_score  # retained for diagnostics
        _ = raw_technical_score

        final_confidence = round(min(0.95, max(0.35, score / 100)), 2)

        # Soft precheck (service-level): score, confidence, trade plan fields.
        # Orchestrator re-validates with data_quality after full analysis path.
        preconditions_ok, _pre_reason = analysis_preconditions_ok(
            score=score,
            confidence=final_confidence,
            trade_plans=trade_plans,
            data_quality=None,
        )
        if not preconditions_ok:
            action = "REJECT"
            logger.info(
                "ANALYSIS_FAILED | symbol=%s | stage=recommendation_service | score=%.2f | plans=%s | reason=%s",
                symbol,
                score,
                len(trade_plans),
                ANALYSIS_FAILED_REASON,
            )
        else:
            action = classify_signal_from_score(score)

        # ------------------------------------------------------------------
        # [FEAT-004] Market Regime Overlay — SHADOW telemetry only.
        # Score / label adjustments are ignored for production signals.
        # ------------------------------------------------------------------
        _cfg = feat004_config or {"enabled": False}
        feat004_score, feat004_action, feat004_log = apply_feat004_regime_overlay(
            composite_score=score,
            current_label=action,
            symbol=symbol,
            benchmark_ohlcv=benchmark_ohlcv,
            benchmark_failure_reason=benchmark_failure_reason,
            benchmark_symbol=benchmark_symbol,
            sector_mapping=sector_mapping,
            sector_ohlcv_cache=sector_ohlcv_cache,
            feat004_config=_cfg,
        )

        # ------------------------------------------------------------------
        # [FEAT-007] Sector Relative Strength Overlay — SHADOW telemetry only.
        # ------------------------------------------------------------------
        feat007_log = self._apply_feat007_overlay(
            composite_score=score,
            current_label=action,
            symbol=symbol,
            sector_rs_value=sector_rs_value,
            sector_index_symbol=sector_index_symbol,
            sector_roc20=sector_roc20,
            benchmark_roc20=benchmark_roc20,
            feat007_abstained_reason=feat007_abstained_reason,
            feat007_config=feat007_config,
        )

        # Production output is always pure composite score + score thresholds
        # (or REJECT + Analysis Failed when preconditions fail).
        final_score = score
        final_action = action

        logger.debug(
            "[%s] composite=%.2f action=%s | feat004_telemetry: score=%.2f action=%s stage=%s regime=%s | overlays_do_not_override_signal=true",
            symbol,
            score,
            action,
            feat004_score,
            feat004_action,
            feat004_log.get("feat004_stage"),
            feat004_log.get("market_regime_state"),
        )

        reasoning = RecommendationReasoning(
            bullets=list(llm_reasoning.get("bullets", [])),
            risk_factors=list(llm_reasoning.get("risk_factors", [])),
            invalidation_signals=list(llm_reasoning.get("invalidation_signals", [])),
        )
        summary = str(
            llm_reasoning.get(
                "summary",
                f"{symbol} is rated {final_action} in the advisory engine with confidence {final_confidence}.",
            )
        )
        recommendation = FinalRecommendation(
            action=final_action,
            confidence=final_confidence,
            score=final_score,
            reasoning=reasoning,
            trade_plans=trade_plans,
            summary=summary,
            # Component scores for multi-condition Strict BUY Gate (0–100 scale).
            technical_score=round(float(raw_tech), 2),
            backtest_score=round(float(raw_backtest), 2),
            fundamental_score=round(float(raw_fund), 2),
        )
        # Attach FEAT-004 metadata to the recommendation object.
        # feat004 is a declared Optional schema field, so direct assignment
        # ensures the metadata survives model_dump() and JSON serialization.
        recommendation.feat004 = feat004_log

        # Populate FEAT-007 schema fields when the overlay ran
        if feat007_log is not None:
            recommendation.feat007_enabled = feat007_log["feat007_enabled"]
            recommendation.feat007_stage = feat007_log["feat007_stage"]
            recommendation.sector_regime_state = feat007_log["sector_regime_state"]
            recommendation.sector_rs_value = feat007_log["sector_rs_value"]
            recommendation.sector_index_symbol = feat007_log["sector_index_symbol"]
            recommendation.sector_roc20 = feat007_log["sector_roc20"]
            recommendation.benchmark_roc20 = feat007_log["benchmark_roc20"]
            recommendation.feat007_score_adjustment = feat007_log["feat007_score_adjustment"]
            recommendation.feat007_pre_adjustment_score = feat007_log["feat007_pre_adjustment_score"]
            recommendation.feat007_post_adjustment_score = feat007_log["feat007_post_adjustment_score"]
            recommendation.feat007_watch_downgrade_applied = feat007_log["feat007_watch_downgrade_applied"]
            recommendation.feat007_abstained_reason = feat007_log["feat007_abstained_reason"]
            recommendation.feat007_explanation = feat007_log["feat007_explanation"]

        return recommendation

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

            recent_lows = [c.low for c in candles[-10:]]
            recent_highs = [c.high for c in candles[-20:]]
            lowest_low = min(recent_lows) if recent_lows else current_price - avg_range
            highest_high = max(recent_highs) if recent_highs else current_price + avg_range

            if direction >= 0:
                entry_low = round(current_price - avg_range * 0.2, 2)
                entry_high = round(current_price + avg_range * 0.1, 2)
                stop_loss = round(min(entry_low - avg_range * 0.6, lowest_low - avg_range * 0.1), 2)
                target_1 = round(max(entry_high + avg_range * 1.6, highest_high + avg_range * 0.2), 2)
                target_2 = round(entry_high + (entry_high - stop_loss) * 2.0, 2)
                target_3 = round(entry_high + (entry_high - stop_loss) * 3.0, 2)
                bias = "long"
            else:
                entry_low = round(current_price - avg_range * 0.1, 2)
                entry_high = round(current_price + avg_range * 0.2, 2)
                stop_loss = round(max(entry_high + avg_range * 0.6, highest_high + avg_range * 0.1), 2)
                target_1 = round(min(entry_low - avg_range * 1.6, lowest_low - avg_range * 0.2), 2)
                target_2 = round(entry_low - (stop_loss - entry_low) * 2.0, 2)
                target_3 = round(entry_low - (stop_loss - entry_low) * 3.0, 2)
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

    def _apply_feat007_overlay(
        self,
        composite_score: float,
        current_label: str,
        symbol: str,
        sector_rs_value: float | None,
        feat007_config: dict[str, Any] | None,
        sector_index_symbol: str | None = None,
        sector_roc20: float | None = None,
        benchmark_roc20: float | None = None,
        feat007_abstained_reason: str | None = None,
    ) -> dict[str, Any] | None:
        """FEAT-007 Sector Relative Strength Overlay.

        Uses the difference-formula sector_rs_value (from SR-003).
        Returns a log dict with all FEAT-007 fields populated, or None
        when the overlay is completely inactive (feat007 disabled).

        Per FEAT-007 v1.1 spec:
          - STRENGTH: sector_rs_value >= 0, delta = +score_delta_strength
          - WEAK:     sector_rs_value < 0,  delta = +score_delta_weak
          - SHADOW:   calculate and log, do NOT modify score/action
          - ACTIVE:   apply score adjustments and downgrade logic
          - REJECT immutability: never modify a REJECT label
          - STRENGTH cap: prevent WATCH from becoming BUY
        """
        if feat007_config is None:
            return None

        enabled = bool(feat007_config.get("enabled", False))
        if not enabled:
            return None

        # stage is read before the try so the except clause can reference it
        # (mirrors FEAT-004's pre-try config read at feat004_regime_overlay.py:574).
        stage = str(feat007_config.get("stage", "SHADOW")).upper()

        try:
            delta_strength = float(feat007_config.get("score_delta_strength", 1.5))
            delta_weak = float(feat007_config.get("score_delta_weak", -3.0))
            downgrade_threshold = float(feat007_config.get("buy_downgrade_threshold", 74.0))
            buy_threshold = float(feat007_config.get("buy_threshold", 68.0))
            strength_cap_enabled = bool(feat007_config.get("strength_cap_enabled", True))

            # Safe degradation: no sector RS data
            # Preserve the specific upstream abstention reason from SR-003
            # (no_sector_mapping, sector_index_unavailable,
            # insufficient_sector_history, sector_rs_computation_failed).
            # Fall back to the spec §12 catch-all when no specific reason
            # was threaded (e.g. direct overlay callers that omit the kwarg).
            if sector_rs_value is None:
                return {
                    "feat007_enabled": True,
                    "feat007_stage": stage,
                    "sector_regime_state": "UNKNOWN",
                    "sector_rs_value": None,
                    "sector_index_symbol": None,
                    "sector_roc20": None,
                    "benchmark_roc20": None,
                    "feat007_score_adjustment": 0.0,
                    "feat007_pre_adjustment_score": composite_score,
                    "feat007_post_adjustment_score": composite_score,
                    "feat007_watch_downgrade_applied": False,
                    "feat007_abstained_reason": feat007_abstained_reason or "upstream_sector_rs_unavailable",
                    "feat007_explanation": f"Sector: UNKNOWN (no sector mapping for {symbol}). No adjustment applied.",
                    "feat007_adjusted_label": current_label,
                }

            # Classify using the difference formula (per ADR-003 / FEAT-007 v1.1)
            if sector_rs_value < 0:
                sector_state = "WEAK"
                score_delta = delta_weak
            else:
                sector_state = "STRENGTH"
                score_delta = delta_strength

            pre_score = composite_score
            adjusted_score = pre_score
            adjusted_label = current_label
            downgrade_applied = False
            abstained_reason: str | None = None

            # REJECT immutability — never modify a REJECT
            if current_label == "REJECT":
                score_delta = 0.0
                adjusted_score = pre_score
                adjusted_label = "REJECT"
            elif stage == "SHADOW":
                # SHADOW: calculate everything but do NOT modify score or label
                adjusted_score = pre_score
                adjusted_label = current_label
            elif stage == "ACTIVE":
                # Apply the score delta
                adjusted_score = round(pre_score + score_delta, 2)
                adjusted_score = max(0.0, min(100.0, adjusted_score))

                # STRENGTH cap: prevent WATCH from becoming BUY
                if (
                    strength_cap_enabled
                    and sector_state == "STRENGTH"
                    and current_label != "BUY"
                    and adjusted_score >= buy_threshold
                ):
                    adjusted_score = min(adjusted_score, buy_threshold - 0.01)
                    score_delta = round(adjusted_score - pre_score, 2)

                # WEAK BUY downgrade
                if (
                    sector_state == "WEAK"
                    and current_label == "BUY"
                    and adjusted_score < downgrade_threshold
                ):
                    adjusted_label = "WATCH"
                    downgrade_applied = True
                elif sector_state == "STRENGTH" and current_label != "BUY":
                    # STRENGTH cap already enforced above; label stays as-is
                    adjusted_label = current_label
                else:
                    # Re-derive label from adjusted score
                    if adjusted_score >= buy_threshold:
                        adjusted_label = "BUY"
                    elif adjusted_score >= 55:
                        adjusted_label = "WATCH"
                    else:
                        adjusted_label = "REJECT"

            # Build explanation string per FEAT-007 spec §11.3
            sector_name = sector_index_symbol or "n/a"
            sector_roc20_fmt = f"{sector_roc20:+.1f}" if sector_roc20 is not None else "n/a"
            benchmark_roc20_fmt = f"{benchmark_roc20:+.1f}" if benchmark_roc20 is not None else "n/a"

            if sector_state == "STRENGTH":
                explanation = (
                    f"Sector: {sector_name} — STRENGTH vs Nifty 500 "
                    f"(RS {sector_rs_value:+.1f} pp, "
                    f"sector ROC20 {sector_roc20_fmt}% vs benchmark {benchmark_roc20_fmt}%). "
                    f"Score adjusted by {score_delta:+.1f} ({pre_score:.1f} → {adjusted_score:.1f})."
                )
            elif sector_state == "WEAK":
                explanation = (
                    f"Sector: {sector_name} — WEAK vs Nifty 500 "
                    f"(RS {sector_rs_value:+.1f} pp, "
                    f"sector ROC20 {sector_roc20_fmt}% vs benchmark {benchmark_roc20_fmt}%). "
                    f"Score adjusted by {score_delta:+.1f} ({pre_score:.1f} → {adjusted_score:.1f})."
                )
                if downgrade_applied:
                    explanation += " BUY downgraded to WATCH."
            else:
                explanation = f"Sector: UNKNOWN (no sector mapping for {symbol}). No adjustment applied."

            logger.info(
                "FEAT-007 | symbol=%s | stage=%s | state=%s | rs_value=%.2f | "
                "delta=%.2f | pre=%.2f | post=%.2f | label=%s→%s | downgrade=%s",
                symbol, stage, sector_state, sector_rs_value,
                score_delta, pre_score, adjusted_score,
                current_label, adjusted_label, downgrade_applied,
            )

            return {
                "feat007_enabled": True,
                "feat007_stage": stage,
                "sector_regime_state": sector_state,
                "sector_rs_value": sector_rs_value,
                "sector_index_symbol": sector_index_symbol,
                "sector_roc20": sector_roc20,
                "benchmark_roc20": benchmark_roc20,
                "feat007_score_adjustment": score_delta,
                "feat007_pre_adjustment_score": pre_score,
                "feat007_post_adjustment_score": adjusted_score,
                "feat007_watch_downgrade_applied": downgrade_applied,
                "feat007_abstained_reason": abstained_reason,
                "feat007_explanation": explanation,
                "feat007_adjusted_label": adjusted_label,
            }

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "FEAT-007: _apply_feat007_overlay unhandled exception for %s: %s",
                symbol,
                exc,
                exc_info=True,
            )
            return {
                "feat007_enabled": True,
                "feat007_stage": stage,
                "sector_regime_state": "UNKNOWN",
                "sector_rs_value": None,
                "sector_index_symbol": None,
                "sector_roc20": None,
                "benchmark_roc20": None,
                "feat007_score_adjustment": 0.0,
                "feat007_pre_adjustment_score": composite_score,
                "feat007_post_adjustment_score": composite_score,
                "feat007_watch_downgrade_applied": False,
                "feat007_abstained_reason": f"exception:{type(exc).__name__}",
                "feat007_explanation": f"FEAT-007 abstained: exception:{type(exc).__name__} for {symbol}. No adjustment applied.",
                "feat007_adjusted_label": current_label,
            }
