from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from app.schemas.shadow_telemetry import (
    AblationMetrics,
    AttributionReport,
    InteractionAnalysis,
)


class AttributionValidationService:
    """Pure service for 4-way synthetic A/B ablation analysis and Pearson/Spearman

    feature interaction analysis.
    """

    MIN_SAMPLE_SIZE: int = 30

    @classmethod
    def calculate_correlation(
        cls, x_values: list[float], y_values: list[float]
    ) -> tuple[float, float]:
        """Calculates Pearson (r) and Spearman (r_s) correlation coefficients between two series."""
        n = len(x_values)
        if n < 2 or len(y_values) != n:
            return 0.0, 0.0

        mean_x = sum(x_values) / n
        mean_y = sum(y_values) / n

        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
        var_x = sum((x - mean_x) ** 2 for x in x_values)
        var_y = sum((y - mean_y) ** 2 for y in y_values)

        if var_x <= 1e-12 or var_y <= 1e-12:
            pearson_r = 0.0
        else:
            pearson_r = cov / (math.sqrt(var_x) * math.sqrt(var_y))

        # Spearman Rank Correlation
        def _rank(series: list[float]) -> list[float]:
            sorted_indices = sorted(range(n), key=lambda k: series[k])
            ranks = [0.0] * n
            for rank, idx in enumerate(sorted_indices, start=1):
                ranks[idx] = float(rank)
            return ranks

        rank_x = _rank(x_values)
        rank_y = _rank(y_values)

        d_sq_sum = sum((rx - ry) ** 2 for rx, ry in zip(rank_x, rank_y))
        spearman_rs = 1.0 - (6.0 * d_sq_sum) / (n * (n**2 - 1.0)) if n > 1 else 0.0

        return round(pearson_r, 4), round(spearman_rs, 4)

    @classmethod
    def analyze_interaction(
        cls,
        decay_deltas: list[float],
        breadth_contributions: list[float],
        decay_key: str = "sentiment_decay",
        breadth_key: str = "market_breadth",
    ) -> InteractionAnalysis:
        """Performs feature interaction check and returns correlation classification & Go / No-Go recommendations."""
        n = min(len(decay_deltas), len(breadth_contributions))
        # Spec edge case: insufficient data defaults to No-Go for both features.
        if n < cls.MIN_SAMPLE_SIZE:
            return InteractionAnalysis(
                decay_feature_key=decay_key,
                breadth_feature_key=breadth_key,
                pearson_correlation=0.0,
                spearman_correlation=0.0,
                redundancy_classification="COMPLEMENTARY",
                decay_promotion_recommendation="NO_GO",
                breadth_promotion_recommendation="NO_GO",
                rationale=(
                    f"Insufficient paired samples (n={n} < {cls.MIN_SAMPLE_SIZE}). "
                    "Defaulting to No-Go; keep features in Shadow Mode to accumulate data."
                ),
                evaluated_at=datetime.now(timezone.utc),
            )

        pearson_r, spearman_rs = cls.calculate_correlation(decay_deltas, breadth_contributions)

        if pearson_r < 0.70:
            classification = "COMPLEMENTARY"
            decay_rec = "GO"
            breadth_rec = "GO"
            rationale = (
                f"Low feature correlation (r={pearson_r:.2f} < 0.70). "
                "Both features provide independent, non-redundant alpha."
            )
        elif 0.70 <= pearson_r <= 0.85:
            classification = "MODERATE_OVERLAP"
            decay_rec = "GO"
            breadth_rec = "NO_GO"
            rationale = (
                f"Moderate feature correlation (r={pearson_r:.2f}). "
                "Promote primary feature (Sentiment Time-Decay) and defer secondary feature (Market Breadth)."
            )
        else:
            classification = "REDUNDANT"
            decay_rec = "GO"
            breadth_rec = "NO_GO"
            rationale = (
                f"High feature correlation (r={pearson_r:.2f} > 0.85). "
                "Features are redundant. Promote primary feature only."
            )

        return InteractionAnalysis(
            decay_feature_key=decay_key,
            breadth_feature_key=breadth_key,
            pearson_correlation=pearson_r,
            spearman_correlation=spearman_rs,
            redundancy_classification=classification,
            decay_promotion_recommendation=decay_rec,
            breadth_promotion_recommendation=breadth_rec,
            rationale=rationale,
            evaluated_at=datetime.now(timezone.utc),
        )

    @classmethod
    def verify_post_promotion_quality(
        cls,
        baseline_false_positive_rate: float,
        live_false_positive_rate: float,
        max_fpr_increase: float = 0.02,
    ) -> tuple[bool, str]:
        """FR-010 / plan rollback safeguard: live FPR must not rise by more than max_fpr_increase.

        Returns (passed, rationale). Callers may auto-kill when passed is False.
        """
        delta = float(live_false_positive_rate) - float(baseline_false_positive_rate)
        if delta > max_fpr_increase:
            return (
                False,
                f"Post-promotion FPR increased by {delta:.4f} "
                f"(limit {max_fpr_increase:.4f}); recommend kill-switch.",
            )
        return (
            True,
            f"Post-promotion FPR delta {delta:.4f} within {max_fpr_increase:.4f} tolerance.",
        )

    @classmethod
    def evaluate_ablation(
        cls, records: list[dict[str, Any]], days: int = 30
    ) -> AttributionReport:
        """Evaluates 4-way synthetic A/B ablation (Baseline, Decay-Only, Breadth-Only, Combined)."""
        sample_size = len(records)
        if sample_size < cls.MIN_SAMPLE_SIZE:
            empty_metrics = AblationMetrics(
                sample_size=sample_size,
                false_positive_rate=0.0,
                win_rate=0.0,
                precision=0.0,
                signal_accuracy=0.0,
                alpha_attribution_pct=0.0,
            )
            return AttributionReport(
                evaluation_window_days=days,
                total_samples=sample_size,
                baseline_metrics=empty_metrics,
                decay_only_metrics=empty_metrics,
                breadth_only_metrics=empty_metrics,
                combined_metrics=empty_metrics,
                situation_tag_breakdown={},
                evaluated_at=datetime.now(timezone.utc),
                status="INSUFFICIENT_DATA",
            )

        # Helper to compute metrics given a list of predicted decisions and actual outcomes
        def _compute_metrics(conf_key: str) -> AblationMetrics:
            tp, fp, tn, fn = 0, 0, 0, 0
            for r in records:
                outcome = r.get("actual_outcome", True)  # True = profitable trade
                score = r.get("scores", {}).get(conf_key, r.get("baseline_score", 60.0))
                predicted_buy = score >= 50.0

                if predicted_buy and outcome:
                    tp += 1
                elif predicted_buy and not outcome:
                    fp += 1
                elif not predicted_buy and not outcome:
                    tn += 1
                else:
                    fn += 1

            total_trades = tp + fp
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
            win_rate = tp / total_trades if total_trades > 0 else 0.0
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            signal_accuracy = (tp + tn) / sample_size if sample_size > 0 else 0.0

            # Alpha attribution % relative to baseline
            baseline_tp = sum(
                1 for r in records if r.get("scores", {}).get("baseline", 60.0) >= 50.0 and r.get("actual_outcome", True)
            )
            alpha_pct = ((tp - baseline_tp) / max(1, baseline_tp)) * 100.0 if conf_key != "baseline" else 0.0

            return AblationMetrics(
                sample_size=sample_size,
                false_positive_rate=round(fpr, 4),
                win_rate=round(win_rate, 4),
                precision=round(precision, 4),
                signal_accuracy=round(signal_accuracy, 4),
                alpha_attribution_pct=round(alpha_pct, 2),
            )

        baseline_m = _compute_metrics("baseline")
        decay_m = _compute_metrics("decay_only")
        breadth_m = _compute_metrics("breadth_only")
        combined_m = _compute_metrics("combined")

        # Breakdown by situation tag if present
        tag_breakdown: dict[str, dict[str, float]] = {}
        for r in records:
            tag = r.get("situation_tag", "GENERAL_MARKET")
            if tag not in tag_breakdown:
                tag_breakdown[tag] = {"count": 0.0, "win_rate": 0.0}
            tag_breakdown[tag]["count"] += 1.0
            if r.get("actual_outcome", True):
                tag_breakdown[tag]["win_rate"] += 1.0

        for tag in tag_breakdown:
            cnt = tag_breakdown[tag]["count"]
            tag_breakdown[tag]["win_rate"] = round(tag_breakdown[tag]["win_rate"] / cnt, 4) if cnt > 0 else 0.0

        return AttributionReport(
            evaluation_window_days=days,
            total_samples=sample_size,
            baseline_metrics=baseline_m,
            decay_only_metrics=decay_m,
            breadth_only_metrics=breadth_m,
            combined_metrics=combined_m,
            situation_tag_breakdown=tag_breakdown,
            evaluated_at=datetime.now(timezone.utc),
            status="VALID",
        )
